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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.domains.analytics.pg_consumer import AnalyticsPgWorker, ConsumerBusy, SourceFactChanged
from app.domains.analytics.pg_models import (
    AnalyticsConsumer,
    AnalyticsDailyMetric,
    AnalyticsProcessedEvent,
    AnalyticsQuarantinedEvent,
)
from tests.analytics.pg_test_support import (  # noqa: F401
    insert_event,
    make_worker,
    requires_pg,
    seed_identity,
)

pytestmark = [requires_pg]

COURSE = "course_" + "1" * 32
CLASS_A = "class_" + "a" * 32
CLASS_B = "class_" + "b" * 32
STUDENT = "user_" + "a" * 32
RESOLVER = "user_" + "e" * 32
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
    seed_identity(pg_engine, course_id=COURSE, class_id=CLASS_A, students=[STUDENT, RESOLVER])
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
    # 人工审计置 retry_ready（操作者持久化到隔离行）；重放仍失败则 attempts 递增且回到 open
    assert worker.retry_quarantined("teacher-overview", "v1", "bad_event", RESOLVER)
    retry_fail = worker.poll_once("teacher-overview", "v1")
    assert retry_fail.quarantined == 1
    with Session(pg_engine) as s, s.begin():
        q = s.execute(select(AnalyticsQuarantinedEvent)).scalar_one()
        assert q.status == "open" and q.attempts == 2
        # 回到 open 后保留最近一次授权操作者（行内审计事实），resolved_at 仍为空
        assert q.resolved_by_user_id == RESOLVER
        assert q.resolved_at is None


def test_poison_event_resolved_on_success_replay(pg_engine: Engine) -> None:
    """重放成功路径：retry_ready 后事件可校验，ledger+聚合+resolved 同事务。

    源事件在生产不可变；重放成功的现实路径是消费侧算法修复或上游受控重放。
    测试以「上游修复事件类型」为合成替身（事件 id 保持不变）。
    """
    seed_identity(pg_engine, course_id=COURSE, class_id=CLASS_A, students=[STUDENT, RESOLVER])
    bad_id = "event_" + "c" * 32
    insert_event(
        pg_engine,
        event_id=bad_id,
        event_type="bogus_type",
        user_id=STUDENT,
        course_id=COURSE,
        class_id=CLASS_A,
        occurred_at=BASE,
        payload={"chapterId": "c1"},
    )  # 未知事件类型：契约外毒事件
    worker = _worker(pg_engine)
    assert worker.poll_once("teacher-overview", "v1").quarantined == 1
    with Session(pg_engine) as s, s.begin():
        q = s.execute(select(AnalyticsQuarantinedEvent)).scalar_one()
        assert q.status == "open" and q.event_id == bad_id
    with pg_engine.begin() as conn:  # 受控重放前的上游修复（合成替身；id 不变）
        conn.execute(
            text("UPDATE learning_events SET event_type = 'chapter_viewed' WHERE id = :i"),
            {"i": bad_id},
        )
    assert worker.retry_quarantined("teacher-overview", "v1", bad_id, RESOLVER)
    result = worker.poll_once("teacher-overview", "v1")
    assert result.applied == 1 and result.quarantined == 0
    with Session(pg_engine) as s, s.begin():
        q = s.execute(select(AnalyticsQuarantinedEvent)).scalar_one()
        assert q.status == "resolved" and q.resolved_at is not None
        assert q.resolved_by_user_id == RESOLVER
        ledger = s.execute(
            select(AnalyticsProcessedEvent.event_id).where(
                AnalyticsProcessedEvent.consumer_id == _consumer_id(s)
            )
        ).scalar_one()
        assert ledger == bad_id  # 账本与 resolved 同事务落库


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
    outer = None
    try:
        outer = blocker.connect()
        outer.begin()
        outer.execute(text("SELECT id FROM analytics_consumers FOR UPDATE NOWAIT"))
        with pytest.raises(ConsumerBusy):
            worker.poll_once("teacher-overview", "v1")
    finally:
        if outer is not None:
            outer.rollback()  # 无条件释放行锁，避免泄漏阻塞后续测试
            outer.close()
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


def test_retry_ready_requires_persisted_resolver(pg_engine: Engine) -> None:
    """约束层：retry_ready/resolved 必须持久记录授权操作者（authorized_status_has_resolver）。

    行先以合法 open 状态落库（FK 均满足），再 UPDATE 置 retry_ready——
    此刻只有 CHECK 约束可失败，证明约束真实存在。
    """
    seed_identity(pg_engine, course_id=COURSE, class_id=CLASS_A, students=[STUDENT])
    event_id = "event_" + "1" * 32
    insert_event(
        pg_engine,
        event_id=event_id,
        event_type="chapter_viewed",
        user_id=STUDENT,
        course_id=COURSE,
        class_id=CLASS_A,
        occurred_at=BASE,
        payload={"chapterId": "c1"},
    )
    _worker(pg_engine).poll_once("teacher-overview", "v1")  # 创建 consumer 行
    with pg_engine.begin() as conn:  # 合成 open 隔离行（FK 全部满足）
        conn.execute(
            text(
                "INSERT INTO analytics_quarantined_events "
                "(id, consumer_id, event_id, error_code, status, attempts) "
                "SELECT 'quarantine_x', c.id, :e, 'schema_violation', 'open', 1 "
                "FROM analytics_consumers AS c LIMIT 1"
            ),
            {"e": event_id},
        )
    with pytest.raises(IntegrityError):
        with pg_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE analytics_quarantined_events SET status = 'retry_ready' "
                    "WHERE id = 'quarantine_x'"
                )
            )


def test_replay_operator_survives_worker_restart(pg_engine: Engine) -> None:
    """重启重放：retry_ready 由 worker A 授权，重启后的 worker 重放成功仍读取行内操作者。"""
    seed_identity(pg_engine, course_id=COURSE, class_id=CLASS_A, students=[STUDENT, RESOLVER])
    bad_id = "event_" + "c" * 32
    insert_event(
        pg_engine,
        event_id=bad_id,
        event_type="bogus_type",
        user_id=STUDENT,
        course_id=COURSE,
        class_id=CLASS_A,
        occurred_at=BASE,
        payload={"chapterId": "c1"},
    )
    worker_a = _worker(pg_engine)
    assert worker_a.poll_once("teacher-overview", "v1").quarantined == 1
    assert worker_a.retry_quarantined("teacher-overview", "v1", bad_id, RESOLVER)
    with Session(pg_engine) as s, s.begin():  # retry_ready 阶段操作者已持久化
        q = s.execute(select(AnalyticsQuarantinedEvent)).scalar_one()
        assert q.status == "retry_ready" and q.resolved_by_user_id == RESOLVER
        assert q.resolved_at is None
    with pg_engine.begin() as conn:  # 受控重放前的上游修复（合成替身；id 不变）
        conn.execute(
            text("UPDATE learning_events SET event_type = 'chapter_viewed' WHERE id = :i"),
            {"i": bad_id},
        )
    worker_b = _worker(pg_engine)  # 全新 worker 实例（模拟重启，无任何进程内身份）
    result = worker_b.poll_once("teacher-overview", "v1")
    assert result.applied == 1
    with Session(pg_engine) as s, s.begin():
        q = s.execute(select(AnalyticsQuarantinedEvent)).scalar_one()
        assert q.status == "resolved" and q.resolved_by_user_id == RESOLVER
        assert q.resolved_at is not None


def test_two_operators_replay_identity_not_mixed(pg_engine: Engine) -> None:
    """两个 worker/两个请求并行授权：resolved 操作者各读各的隔离行，不串用。"""
    op_a = "user_" + "e" * 32  # RESOLVER
    op_b = "user_" + "f" * 32
    seed_identity(pg_engine, course_id=COURSE, class_id=CLASS_A, students=[STUDENT, op_a, op_b])
    bad1 = "event_" + "c" * 32
    bad2 = "event_" + "d" * 32
    for bad_id in (bad1, bad2):
        insert_event(
            pg_engine,
            event_id=bad_id,
            event_type="bogus_type",
            user_id=STUDENT,
            course_id=COURSE,
            class_id=CLASS_A,
            occurred_at=BASE,
            payload={"chapterId": "c1"},
        )
    worker_a = _worker(pg_engine)
    worker_b = _worker(pg_engine)
    assert worker_a.poll_once("teacher-overview", "v1").quarantined == 2
    assert worker_a.retry_quarantined("teacher-overview", "v1", bad1, op_a)
    assert worker_b.retry_quarantined("teacher-overview", "v1", bad2, op_b)
    with pg_engine.begin() as conn:  # 上游修复两个事件（合成替身；id 不变）
        conn.execute(
            text("UPDATE learning_events SET event_type = 'chapter_viewed'"),
        )
    result = _worker(pg_engine).poll_once("teacher-overview", "v1")
    assert result.applied == 2
    with Session(pg_engine) as s, s.begin():
        rows = {
            q.event_id: q.resolved_by_user_id
            for q in s.execute(select(AnalyticsQuarantinedEvent)).scalars().all()
        }
        assert rows[bad1] == op_a and rows[bad2] == op_b  # 身份按行落位，无串用


def test_resolver_fk_restrict_protects_resolved_rows(pg_engine: Engine) -> None:
    """操作者外键 RESTRICT：resolved 行的操作者不可被删（不靠 SET NULL 破坏结算）。"""
    seed_identity(pg_engine, course_id=COURSE, class_id=CLASS_A, students=[STUDENT, RESOLVER])
    bad_id = "event_" + "c" * 32
    insert_event(
        pg_engine,
        event_id=bad_id,
        event_type="bogus_type",
        user_id=STUDENT,
        course_id=COURSE,
        class_id=CLASS_A,
        occurred_at=BASE,
        payload={"chapterId": "c1"},
    )
    worker = _worker(pg_engine)
    assert worker.poll_once("teacher-overview", "v1").quarantined == 1
    with pg_engine.begin() as conn:
        conn.execute(
            text("UPDATE learning_events SET event_type = 'chapter_viewed' WHERE id = :i"),
            {"i": bad_id},
        )
    assert worker.retry_quarantined("teacher-overview", "v1", bad_id, RESOLVER)
    assert worker.poll_once("teacher-overview", "v1").applied == 1
    with pytest.raises(IntegrityError), pg_engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id = :i"), {"i": RESOLVER})


def test_source_fact_change_rolls_back_round(pg_engine: Engine) -> None:
    """源事实漂移：重算复核 learning-feed-sha256-v1 摘要不符 → SOURCE_FACT_CHANGED 回滚本轮。

    不覆盖旧账本摘要、不重复计数；恢复源事实后同事件正常重算。
    """
    seed_identity(pg_engine, course_id=COURSE, class_id=CLASS_A, students=[STUDENT])
    event_id = "event_" + "1" * 32
    insert_event(
        pg_engine,
        event_id=event_id,
        event_type="assignment_submitted",
        user_id=STUDENT,
        course_id=COURSE,
        class_id=CLASS_A,
        occurred_at=BASE,
        payload={"submissionId": "sub_1"},
    )
    _worker(pg_engine).poll_once("teacher-overview", "v1")
    with Session(pg_engine) as s, s.begin():
        original_hash = s.execute(select(AnalyticsProcessedEvent.source_hash)).scalar_one()
    with pg_engine.begin() as conn:  # 模拟源事实被篡改（生产中应报警核查）
        conn.execute(
            text("UPDATE learning_events SET payload = :p WHERE id = :i"),
            {"i": event_id, "p": '{"submissionId":"sub_2"}'},
        )
    insert_event(  # 同键新事件触发重算，复核旧事件摘要
        pg_engine,
        event_id="event_" + "2" * 32,
        event_type="assignment_submitted",
        user_id=STUDENT,
        course_id=COURSE,
        class_id=CLASS_A,
        occurred_at=BASE + timedelta(minutes=10),
        payload={"submissionId": "sub_3"},
    )
    with pytest.raises(SourceFactChanged) as excinfo:
        _worker(pg_engine).poll_once("teacher-overview", "v1")
    assert excinfo.value.event_id == event_id
    with Session(pg_engine) as s, s.begin():  # 本轮已回滚：新事件未入账本、旧摘要未覆盖
        hashes = s.execute(select(AnalyticsProcessedEvent.source_hash)).scalars().all()
        assert len(hashes) == 1 and hashes[0] == original_hash
        assert _daily(s, _consumer_id(s)).submission_count == 1
    with pg_engine.begin() as conn:  # 恢复源事实后重算通过
        conn.execute(
            text("UPDATE learning_events SET payload = :p WHERE id = :i"),
            {"i": event_id, "p": '{"submissionId":"sub_1"}'},
        )
    result = _worker(pg_engine).poll_once("teacher-overview", "v1")
    assert result.applied == 1
    with Session(pg_engine) as s, s.begin():
        rows = s.execute(select(AnalyticsProcessedEvent)).scalars().all()
        assert len(rows) == 2
        assert {r.source_hash for r in rows} >= {original_hash}  # 旧摘要保持不变
        assert _daily(s, _consumer_id(s)).submission_count == 2
