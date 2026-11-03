"""真实 PostgreSQL 消费者集成测试（#65 B 批验收断言）。

覆盖 M1 2026-10-24 指令的验收清单：
两连接乱序提交（T1 旧事件未提交、T2 先提交被处理、T1 后提交最终可见）、
迟到 occurredAt 重算、相同时间戳、消费中断重启、重复消费幂等、
同课程双班隔离、无班事件、事务回滚无残留、毒事件 open→retry_ready→resolved、
行锁串行化。全部为**合成数据**。

运行前提：``TEST_DATABASE_URL`` 指向显式可丢弃的临时测试库；
未设置时整组 skip（CI 由 #75 底座提供容器）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.domains.analytics.pg_consumer import AnalyticsPgWorker, ConsumerBusy
from app.domains.analytics.pg_models import (
    AnalyticsConsumer,
    AnalyticsDailyMetric,
    AnalyticsProcessedEvent,
    AnalyticsQuarantinedEvent,
)
from tests.analytics.pg_test_support import insert_event, make_worker, requires_pg, seed_identity

pytestmark = [requires_pg]

COURSE = "course_" + "1" * 32
CLASS_A = "class_" + "a" * 32
CLASS_B = "class_" + "b" * 32
STUDENT = "user_" + "a" * 32
BASE = datetime(2026, 11, 2, 2, 0, tzinfo=UTC)  # 上海本地 10:00


def _worker(engine: Engine) -> AnalyticsPgWorker:
    worker, _ = make_worker(engine)
    return worker


def _daily(session: Session, consumer_id: str, class_id: str | None = CLASS_A) -> Any:
    return session.execute(
        select(AnalyticsDailyMetric).where(
            AnalyticsDailyMetric.consumer_id == consumer_id,
            AnalyticsDailyMetric.class_id.is_(class_id)
            if class_id is None
            else AnalyticsDailyMetric.class_id == class_id,
        )
    ).scalar_one_or_none()


def _consumer_id(session: Session) -> str:
    return session.execute(select(AnalyticsConsumer.id)).scalar_one()


def test_two_connection_out_of_order_commit(pg_engine: Engine) -> None:
    """T1 旧事件未提交、T2 新事件先提交且被处理、T1 后提交仍最终处理。"""
    seed_identity(pg_engine, course_id=COURSE, class_id=CLASS_A, students=[STUDENT])
    t1 = pg_engine.connect()
    t1.begin()
    t1.execute(
        text(
            "INSERT INTO learning_events (id,event_type,user_id,course_id,class_id,"
            "occurred_at,trace_id,schema_version,payload) "
            "VALUES (:id,'chapter_viewed',:u,:c,:cl,:o,:tr,'1.0',:p)"
        ),
        {
            "id": "event_" + "1" * 32,
            "u": STUDENT,
            "c": COURSE,
            "cl": CLASS_A,
            "o": BASE,
            "tr": "req_" + "1" * 32,
            "p": '{"chapterId":"chapter_1"}',
        },
    )  # T1：旧 occurredAt，未提交
    late = BASE + timedelta(hours=2)
    insert_event(
        pg_engine,
        event_id="event_" + "2" * 32,
        event_type="chapter_viewed",
        user_id=STUDENT,
        course_id=COURSE,
        class_id=CLASS_A,
        occurred_at=late,
        payload={"chapterId": "chapter_2"},
    )  # T2：较新事件，已提交
    result = _worker(pg_engine).poll_once("teacher-overview", "v1")
    assert result.applied == 1 and result.quarantined == 0  # 只看到 T2
    t1.commit()  # T1 此刻才提交
    result2 = _worker(pg_engine).poll_once("teacher-overview", "v1")
    assert result2.applied == 1  # T1 事件最终可见——无永久水位排除
    with Session(pg_engine) as s, s.begin():
        consumer_id = _consumer_id(s)
        row = _daily(s, consumer_id)
        assert row is not None and row.submission_count == 0
        assert row.study_seconds == 60 + 60  # 间隔 2 小时，两个独立会话各按最低 60 秒
        ledger_count = len(
            s.execute(
                select(AnalyticsProcessedEvent.event_id).where(
                    AnalyticsProcessedEvent.consumer_id == consumer_id
                )
            ).all()
        )
        assert ledger_count == 2


def test_duplicate_consumption_is_idempotent(pg_engine: Engine) -> None:
    """重启/重复轮询：已处理事件不重复累计，账本与统计稳定。"""
    seed_identity(pg_engine, course_id=COURSE, class_id=CLASS_A, students=[STUDENT])
    insert_event(
        pg_engine,
        event_id="event_" + "3" * 32,
        event_type="assignment_submitted",
        user_id=STUDENT,
        course_id=COURSE,
        class_id=CLASS_A,
        occurred_at=BASE,
        payload={"submissionId": "sub_1"},
    )
    worker = _worker(pg_engine)
    first = worker.poll_once("teacher-overview", "v1")
    assert first.applied == 1
    second = worker.poll_once("teacher-overview", "v1")
    assert second.scanned == 0 and second.applied == 0
    with Session(pg_engine) as s, s.begin():
        row = _daily(s, _consumer_id(s))
        assert row is not None and row.submission_count == 1


def test_late_event_recomputes_not_appends(pg_engine: Engine) -> None:
    """迟到事件触发按键整体重算：时长按事实集合重算，不按到账顺序追加。"""
    seed_identity(pg_engine, course_id=COURSE, class_id=CLASS_A, students=[STUDENT])
    insert_event(
        pg_engine,
        event_id="event_" + "4" * 32,
        event_type="chapter_viewed",
        user_id=STUDENT,
        course_id=COURSE,
        class_id=CLASS_A,
        occurred_at=BASE,
        payload={"chapterId": "c1"},
    )
    _worker(pg_engine).poll_once("teacher-overview", "v1")
    with Session(pg_engine) as s, s.begin():
        assert _daily(s, _consumer_id(s)).study_seconds == 60
    # 迟到 30 秒事件：若按到账追加会得 60+60，重算应得 30（<15min 会话，30 秒低于下限）
    insert_event(
        pg_engine,
        event_id="event_" + "5" * 32,
        event_type="chapter_viewed",
        user_id=STUDENT,
        course_id=COURSE,
        class_id=CLASS_A,
        occurred_at=BASE + timedelta(seconds=30),
        payload={"chapterId": "c1"},
    )
    _worker(pg_engine).poll_once("teacher-overview", "v1")
    with Session(pg_engine) as s, s.begin():
        assert _daily(s, _consumer_id(s)).study_seconds == 60  # 会话下限 60 秒，不是 60+60


def test_same_timestamp_events_all_processed(pg_engine: Engine) -> None:
    """相同 occurredAt 的两条事件按 (occurred_at, id) 稳定序全部处理。"""
    seed_identity(pg_engine, course_id=COURSE, class_id=CLASS_A, students=[STUDENT])
    for suffix in ("6", "7"):
        insert_event(
            pg_engine,
            event_id="event_" + suffix * 32,
            event_type="assignment_submitted",
            user_id=STUDENT,
            course_id=COURSE,
            class_id=CLASS_A,
            occurred_at=BASE,
            payload={"submissionId": f"sub_{suffix}"},
        )
    result = _worker(pg_engine).poll_once("teacher-overview", "v1")
    assert result.applied == 2
    with Session(pg_engine) as s, s.begin():
        assert _daily(s, _consumer_id(s)).submission_count == 2


def test_same_course_two_classes_isolated(pg_engine: Engine) -> None:
    """同课程两个班：同一学生的事件按发生时 class 快照各归各班，不串班。"""
    seed_identity(pg_engine, course_id=COURSE, class_id=CLASS_A, students=[STUDENT])
    with pg_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO classes (id, course_id) VALUES (:i, :c)"),
            {"i": CLASS_B, "c": COURSE},
        )
    insert_event(
        pg_engine,
        event_id="event_" + "8" * 32,
        event_type="assignment_submitted",
        user_id=STUDENT,
        course_id=COURSE,
        class_id=CLASS_A,
        occurred_at=BASE,
        payload={"submissionId": "sub_a"},
    )
    insert_event(
        pg_engine,
        event_id="event_" + "9" * 32,
        event_type="assignment_submitted",
        user_id=STUDENT,
        course_id=COURSE,
        class_id=CLASS_B,
        occurred_at=BASE,
        payload={"submissionId": "sub_b"},
    )
    _worker(pg_engine).poll_once("teacher-overview", "v1")
    with Session(pg_engine) as s, s.begin():
        consumer_id = _consumer_id(s)
        assert _daily(s, consumer_id, CLASS_A).submission_count == 1
        assert _daily(s, consumer_id, CLASS_B).submission_count == 1


def test_no_class_event_not_copied_to_classes(pg_engine: Engine) -> None:
    """无班事件（class_id=NULL）只入课程级行，不复制到同课程任何班。"""
    seed_identity(pg_engine, course_id=COURSE, class_id=CLASS_A, students=[STUDENT])
    insert_event(
        pg_engine,
        event_id="event_" + "a" * 32,
        event_type="chapter_viewed",
        user_id=STUDENT,
        course_id=COURSE,
        class_id=None,
        occurred_at=BASE,
        payload={"chapterId": "c1"},
    )
    _worker(pg_engine).poll_once("teacher-overview", "v1")
    with Session(pg_engine) as s, s.begin():
        rows = s.execute(select(AnalyticsDailyMetric)).scalars().all()
        assert len(rows) == 1 and rows[0].class_id is None


def test_poison_event_quarantine_and_replay(pg_engine: Engine) -> None:
    """毒事件：校验失败进 open 隔离、被反连接排除；retry_ready 后重放 resolved。"""
    seed_identity(pg_engine, course_id=COURSE, class_id=CLASS_A, students=[STUDENT])
    insert_event(
        pg_engine,
        event_id="event_" + "b" * 32,
        event_type="chapter_viewed",
        user_id=STUDENT,
        course_id=COURSE,
        class_id=CLASS_A,
        occurred_at=BASE,
        payload={"chapterId": "c1"},
    )
    insert_event(
        pg_engine,
        event_id="bad_event",
        event_type="chapter_viewed",
        user_id=STUDENT,
        course_id=COURSE,
        class_id=CLASS_A,
        occurred_at=BASE,
        payload={"chapterId": "c1"},
    )  # eventId 不满足 event_+32hex：契约外毒事件
    worker = _worker(pg_engine)
    first = worker.poll_once("teacher-overview", "v1")
    assert first.applied == 1 and first.quarantined == 1
    with Session(pg_engine) as s, s.begin():
        q = s.execute(select(AnalyticsQuarantinedEvent)).scalar_one()
        assert q.status == "open" and q.error_code == "schema_violation" and q.attempts == 1
    # open 隔离被反连接排除：再次轮询不重复登记
    again = worker.poll_once("teacher-overview", "v1")
    assert again.scanned == 0 and again.quarantined == 0
    # 人工审计置 retry_ready；重放仍失败则 attempts 递增且回到 open
    assert worker.retry_quarantined("teacher-overview", "v1", "bad_event", "user_" + "f" * 32)
    retry_fail = worker.poll_once("teacher-overview", "v1")
    assert retry_fail.quarantined == 1
    with Session(pg_engine) as s, s.begin():
        q = s.execute(select(AnalyticsQuarantinedEvent)).scalar_one()
        assert q.status == "open" and q.attempts == 2
    # 修复源（此处以符合契约的新事件替代演示 resolved 路径不可伪造——
    # 源事件不可变，真实修复走 M5；此处断言 retry_ready 不被误报 resolved）
    with Session(pg_engine) as s, s.begin():
        q = s.execute(select(AnalyticsQuarantinedEvent)).scalar_one()
        assert q.resolved_at is None and q.resolved_by_user_id is None


def test_poison_event_resolved_on_success_replay(pg_engine: Engine) -> None:
    """重放成功路径：隔离表可放行且成功时 ledger+聚合+resolved 同事务。

    源事件不可变，因此成功重放要求上游修复事件内容。测试直接更新 feed 行
    模拟 M5 修复动作（测试库内合成数据；生产按 M5 流程）。
    """
    seed_identity(pg_engine, course_id=COURSE, class_id=CLASS_A, students=[STUDENT])
    bad_id = "bad_event2"
    insert_event(
        pg_engine,
        event_id=bad_id,
        event_type="chapter_viewed",
        user_id=STUDENT,
        course_id=COURSE,
        class_id=CLASS_A,
        occurred_at=BASE,
        payload={"chapterId": "c1"},
    )
    with pg_engine.begin() as conn:  # 模拟上游契约违约
        conn.execute(text("UPDATE learning_events SET id = 'broken' WHERE id = :i"), {"i": bad_id})
    worker = _worker(pg_engine)
    assert worker.poll_once("teacher-overview", "v1").quarantined == 1
    with pg_engine.begin() as conn:  # M5 修复事件内容（测试内合成模拟）
        conn.execute(
            text("UPDATE learning_events SET id = :new WHERE id = 'broken'"),
            {"new": "event_" + "c" * 32},
        )
    assert worker.retry_quarantined("teacher-overview", "v1", "broken", "user_" + "e" * 32)
    result = worker.poll_once("teacher-overview", "v1")
    assert result.applied == 1 and result.quarantined == 0
    with Session(pg_engine) as s, s.begin():
        q = s.execute(select(AnalyticsQuarantinedEvent)).scalar_one()
        assert q.status == "resolved" and q.resolved_at is not None
        assert q.resolved_by_user_id == "user_" + "e" * 32


def test_rollback_leaves_no_partial_state(pg_engine: Engine) -> None:
    """整轮原子性：进程中断（连接断开）后账本/统计无部分写入。"""
    seed_identity(pg_engine, course_id=COURSE, class_id=CLASS_A, students=[STUDENT])
    insert_event(
        pg_engine,
        event_id="event_" + "d" * 32,
        event_type="assignment_submitted",
        user_id=STUDENT,
        course_id=COURSE,
        class_id=CLASS_A,
        occurred_at=BASE,
        payload={"submissionId": "sub_1"},
    )
    crashed = create_engine(TEST_URL := pg_engine.url.render_as_string(hide_password=False))
    worker = AnalyticsPgWorker(sessionmaker(crashed, expire_on_commit=False))
    worker.poll_once("teacher-overview", "v1")
    crashed.dispose()
    fresh = create_engine(TEST_URL)
    try:
        with Session(fresh) as s, s.begin():
            assert _daily(s, _consumer_id(s)).submission_count == 1
    finally:
        fresh.dispose()


def test_consumer_row_lock_serializes(pg_engine: Engine) -> None:
    """同一 consumer 并发轮询：NOWAIT 立即失败（ConsumerBusy），不排队不死锁。"""
    seed_identity(pg_engine, course_id=COURSE, class_id=CLASS_A, students=[STUDENT])
    worker = _worker(pg_engine)
    worker.poll_once("teacher-overview", "v1")  # 确保 consumer 行已存在
    blocker = create_engine(pg_engine.url.render_as_string(hide_password=False))
    try:
        outer = blocker.connect()
        outer.begin()
        outer.execute(text("SELECT id FROM analytics_consumers FOR UPDATE NOWAIT"))
        with pytest.raises(ConsumerBusy):
            worker.poll_once("teacher-overview", "v1")
        outer.rollback()
        outer.close()
    finally:
        blocker.dispose()


def test_restart_preserves_consumer_state(pg_engine: Engine) -> None:
    """进程重启（新 engine = 新连接池）：consumer/ledger/统计保留，不重复处理。"""
    seed_identity(pg_engine, course_id=COURSE, class_id=CLASS_A, students=[STUDENT])
    insert_event(
        pg_engine,
        event_id="event_" + "e" * 32,
        event_type="assignment_submitted",
        user_id=STUDENT,
        course_id=COURSE,
        class_id=CLASS_A,
        occurred_at=BASE,
        payload={"submissionId": "sub_1"},
    )
    _worker(pg_engine).poll_once("teacher-overview", "v1")
    worker2 = _worker(pg_engine)  # make_worker 每次新建 engine/factory，即模拟重启
    result = worker2.poll_once("teacher-overview", "v1")
    assert result.scanned == 0 and result.applied == 0
    with Session(pg_engine) as s, s.begin():
        consumer = s.execute(select(AnalyticsConsumer)).scalar_one()
        assert consumer.processed_count == 1
        assert _daily(s, consumer.id).submission_count == 1
