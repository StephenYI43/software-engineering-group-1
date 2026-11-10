"""真实 PostgreSQL 成长报告快照集成测试（#65 C 批第一批验收断言）。

覆盖：幂等同键同参返回同一 Job、同键换参冲突、个人/班级快照
duration_seconds 求和与 unknown、metrics schemaVersion CHECK、
report_jobs 终态约束（succeeded 必有 report_id 等）、隔离区列表与
replay 置 retry_ready、越权 student 读他人报告 404。
全部为**合成数据**；契约形状见
``packages/contracts/analytics/report-api.md``。

运行前提：``TEST_DATABASE_URL`` 指向显式可丢弃的临时测试库；
未设置时整组 skip（CI 由 #75 底座提供容器）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.domains.analytics.errors import InvalidQueryError
from app.domains.analytics.pg_models import (
    AnalyticsConsumer,
    AnalyticsReportSnapshot,
    ReportJob,
)
from app.domains.analytics.report_service import (
    QuarantinedEventNotFoundError,
    ReportActor,
    ReportForbiddenError,
    ReportIdempotencyConflictError,
    ReportJobNotFoundError,
    ReportNotFoundError,
    ReportPgService,
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
STUDENT_A = "user_" + "a" * 32
STUDENT_B = "user_" + "b" * 32
TEACHER = "user_" + "t" * 32
ADMIN = "user_" + "d" * 32
BASE = datetime(2026, 11, 2, 2, 0, tzinfo=UTC)  # 上海本地 11-02 10:00
DAY2 = BASE + timedelta(days=1)  # 上海本地 11-03 10:00

# 报告周期：上海 11-02 00:00 → 11-09 00:00（半开，覆盖 11-02..11-08 七个本地日）
PERIOD_START = datetime(2026, 11, 1, 16, 0, tzinfo=UTC)
PERIOD_END = datetime(2026, 11, 8, 16, 0, tzinfo=UTC)
# 与数据无交集的周期（上海 12-01..12-08）：验证 unknown 不是 0
EMPTY_START = datetime(2026, 11, 30, 16, 0, tzinfo=UTC)
EMPTY_END = datetime(2026, 12, 7, 16, 0, tzinfo=UTC)

TZ = "Asia/Shanghai"
KEY = "idem-key-1"

KNOWN_DURATION_A = {"state": "known", "value": 120, "algorithm": "session_inference_v1"}
UNKNOWN_DURATION = {"state": "unknown", "reason": "no_events_in_period"}


def _service(engine: Engine) -> ReportPgService:
    return ReportPgService(sessionmaker(engine, expire_on_commit=False))


def _student_actor(user_id: str = STUDENT_A) -> ReportActor:
    return ReportActor(user_id=user_id, role="student")


def _teacher_actor() -> ReportActor:
    return ReportActor(user_id=TEACHER, role="teacher")


def _admin_actor() -> ReportActor:
    return ReportActor(user_id=ADMIN, role="admin")


def _seed(engine: Engine, *, with_events: bool) -> None:
    """合成身份 + （可选）三个本地日的已知事件，并由 worker 消费成日统计。"""
    seed_identity(
        engine,
        course_id=COURSE,
        class_id=CLASS_A,
        students=[STUDENT_A, STUDENT_B, TEACHER, ADMIN],
    )
    if not with_events:
        return
    insert_event(
        engine,
        event_id="event_" + "1" * 32,
        event_type="chapter_viewed",
        user_id=STUDENT_A,
        course_id=COURSE,
        class_id=CLASS_A,
        occurred_at=BASE,
        payload={"chapterId": "chapter_1"},
    )  # 学生 A 11-02：单事件会话，60 秒
    insert_event(
        engine,
        event_id="event_" + "2" * 32,
        event_type="chapter_viewed",
        user_id=STUDENT_A,
        course_id=COURSE,
        class_id=CLASS_A,
        occurred_at=DAY2,
        payload={"chapterId": "chapter_1"},
    )  # 学生 A 11-03：60 秒
    insert_event(
        engine,
        event_id="event_" + "3" * 32,
        event_type="chapter_viewed",
        user_id=STUDENT_B,
        course_id=COURSE,
        class_id=CLASS_A,
        occurred_at=BASE,
        payload={"chapterId": "chapter_1"},
    )  # 学生 B 11-02：60 秒
    worker, _ = make_worker(engine)
    result = worker.poll_once("teacher-overview", "v1")
    assert result.applied == 3 and result.quarantined == 0


def _create_personal(
    engine: Engine,
    *,
    actor: ReportActor,
    student_user_id: str,
    period_start: datetime = PERIOD_START,
    period_end: datetime = PERIOD_END,
    key: str = KEY,
) -> Any:
    return _service(engine).create_job(
        actor=actor,
        student_user_id=student_user_id,
        class_id=None,
        period_start=period_start,
        period_end=period_end,
        timezone=TZ,
        idempotency_key=key,
    )


def _create_class(
    engine: Engine,
    *,
    actor: ReportActor,
    class_id: str,
    period_start: datetime = PERIOD_START,
    period_end: datetime = PERIOD_END,
    key: str = KEY,
) -> Any:
    return _service(engine).create_job(
        actor=actor,
        student_user_id=None,
        class_id=class_id,
        period_start=period_start,
        period_end=period_end,
        timezone=TZ,
        idempotency_key=key,
    )


def _job_view_assertions(outcome: Any) -> None:
    """成功路径的 Job 公开形状：succeeded + report_id，不伪造 started_at。"""
    assert outcome.job.status == "succeeded"
    assert outcome.job.is_mock is False
    assert outcome.job.result_id == outcome.report.report_id
    assert outcome.job.error_code is None
    assert outcome.job.started_at is None
    assert outcome.job.finished_at is not None
    assert outcome.job.created_at is not None


def test_personal_report_known_sum(pg_engine: Engine) -> None:
    """个人报告：窗口内 known 行 study_seconds 求和，unknown 不用 0 冒充。"""
    _seed(pg_engine, with_events=True)
    outcome = _create_personal(pg_engine, actor=_student_actor(), student_user_id=STUDENT_A)
    _job_view_assertions(outcome)
    assert outcome.report.duration_seconds == KNOWN_DURATION_A  # 60 + 60
    assert outcome.report.data_through == DAY2  # 纳入数据的最新事件发生时间
    assert outcome.report.knowledge_points == []  # 受控词表未定义，本批恒空
    assert outcome.report.suggestions == []
    assert outcome.report.student_user_id == STUDENT_A and outcome.report.class_id is None
    with Session(pg_engine) as s, s.begin():
        snap = s.execute(select(AnalyticsReportSnapshot)).scalars().one()
        assert snap.sample_count == 1  # 个人报告固定 1
        assert snap.metrics == {
            "schemaVersion": "1.0",
            "durationSeconds": KNOWN_DURATION_A,
            "knowledgePoints": [],
            "suggestions": [],
        }
        job = s.execute(select(ReportJob)).scalars().one()
        assert job.status == "succeeded"
        assert job.report_id == snap.id  # succeeded 必有 report_id（CHECK 语义）
        assert job.finished_at is not None and job.error_code is None
        assert job.idempotency_key == KEY


def test_class_report_sum_and_sample_count(pg_engine: Engine) -> None:
    """班级报告：仅纳入 class_id 匹配的 known 行；sample_count=有数据去重学生数。"""
    _seed(pg_engine, with_events=True)
    outcome = _create_class(pg_engine, actor=_teacher_actor(), class_id=CLASS_A)
    _job_view_assertions(outcome)
    assert outcome.report.duration_seconds == {
        "state": "known",
        "value": 180,  # A 两天 120 + B 一天 60
        "algorithm": "session_inference_v1",
    }
    assert outcome.report.data_through == DAY2
    assert outcome.report.class_id == CLASS_A and outcome.report.student_user_id is None
    with Session(pg_engine) as s, s.begin():
        snap = s.execute(select(AnalyticsReportSnapshot)).scalars().one()
        assert snap.sample_count == 2  # A 与 B 有数据；无数据学生不虚计样本


def test_report_unknown_when_no_data(pg_engine: Engine) -> None:
    """窗口内无任何数据：duration unknown(no_events_in_period)，不是 0。"""
    _seed(pg_engine, with_events=False)
    personal = _create_personal(
        pg_engine,
        actor=_student_actor(),
        student_user_id=STUDENT_A,
        period_start=EMPTY_START,
        period_end=EMPTY_END,
    )
    assert personal.report.duration_seconds == UNKNOWN_DURATION
    assert personal.report.data_through is None
    cls = _create_class(
        pg_engine,
        actor=_teacher_actor(),
        class_id=CLASS_A,
        period_start=EMPTY_START,
        period_end=EMPTY_END,
        key="idem-key-2",
    )
    assert cls.report.duration_seconds == UNKNOWN_DURATION
    assert cls.report.data_through is None
    with Session(pg_engine) as s, s.begin():
        snaps = s.execute(select(AnalyticsReportSnapshot)).scalars().all()
        counts = sorted(snap.sample_count for snap in snaps)
        assert counts == [0, 1]  # 班级 0 名学生有数据；个人固定 1


def test_idempotent_same_key_same_params_returns_same_job(pg_engine: Engine) -> None:
    """同 actor 同键同参：返回既有 Job，不重复写业务。"""
    _seed(pg_engine, with_events=False)
    first = _create_personal(pg_engine, actor=_student_actor(), student_user_id=STUDENT_A)
    second = _create_personal(pg_engine, actor=_student_actor(), student_user_id=STUDENT_A)
    assert second.job.job_id == first.job.job_id
    assert second.report is not None and first.report is not None
    assert second.report.report_id == first.report.report_id
    with Session(pg_engine) as s, s.begin():
        assert s.execute(select(func.count()).select_from(ReportJob)).scalar_one() == 1


def test_idempotency_key_conflict_on_changed_params(pg_engine: Engine) -> None:
    """同键换参：换周期或换目标都抛冲突（路由映射 409），且不落新任务。"""
    _seed(pg_engine, with_events=False)
    _create_personal(pg_engine, actor=_student_actor(), student_user_id=STUDENT_A)
    with pytest.raises(ReportIdempotencyConflictError):  # 同键换周期
        _create_personal(
            pg_engine,
            actor=_student_actor(),
            student_user_id=STUDENT_A,
            period_start=EMPTY_START,
            period_end=EMPTY_END,
        )
    _create_class(pg_engine, actor=_teacher_actor(), class_id=CLASS_A, key="k-t1")
    with pytest.raises(ReportIdempotencyConflictError):  # 同键换目标（同 actor）
        _create_personal(pg_engine, actor=_teacher_actor(), student_user_id=STUDENT_A, key="k-t1")
    with Session(pg_engine) as s, s.begin():
        assert s.execute(select(func.count()).select_from(ReportJob)).scalar_one() == 2


def test_snapshot_reused_across_jobs(pg_engine: Engine) -> None:
    """同目标同周期跨幂等键复用快照：快照不可变，只链接不重生成。"""
    _seed(pg_engine, with_events=True)
    first = _create_personal(
        pg_engine, actor=_teacher_actor(), student_user_id=STUDENT_A, key="k-1"
    )
    second = _create_personal(
        pg_engine, actor=_teacher_actor(), student_user_id=STUDENT_A, key="k-2"
    )
    assert second.report is not None and first.report is not None
    assert second.report.report_id == first.report.report_id
    with Session(pg_engine) as s, s.begin():
        assert (
            s.execute(select(func.count()).select_from(AnalyticsReportSnapshot)).scalar_one() == 1
        )
        assert s.execute(select(func.count()).select_from(ReportJob)).scalar_one() == 2


def test_table_constraints_enforced_by_ddl(pg_engine: Engine) -> None:
    """#79 DDL 的 CHECK 约束在真实 PG 生效：违规插入一律 IntegrityError。"""
    _seed(pg_engine, with_events=False)
    _create_personal(pg_engine, actor=_student_actor(), student_user_id=STUDENT_A)
    with Session(pg_engine) as s:
        consumer_id = s.execute(select(AnalyticsConsumer.id)).scalar_one()

    snapshot_sql = text(
        "INSERT INTO analytics_report_snapshots"
        " (id, consumer_id, student_user_id, class_id, period_start, period_end,"
        "  metrics, sample_count)"
        " VALUES (:id, :cid, :sid, :cls, :ps, :pe, CAST(:m AS jsonb), 1)"
    )
    bad_metrics = '{"schemaVersion":"2.0","durationSeconds":{"state":"unknown",'
    bad_metrics += '"reason":"no_events_in_period"},"knowledgePoints":[],"suggestions":[]}'
    base_snapshot_params: dict[str, Any] = {
        "id": "report_raw_a",
        "cid": consumer_id,
        "ps": PERIOD_START,
        "pe": PERIOD_END,
    }
    with pytest.raises(IntegrityError):  # metrics CHECK：schemaVersion 必须 "1.0"
        with pg_engine.begin() as conn:
            conn.execute(
                snapshot_sql,
                base_snapshot_params | {"sid": STUDENT_A, "cls": None, "m": bad_metrics},
            )
    with pytest.raises(IntegrityError):  # 恰好一个目标
        with pg_engine.begin() as conn:
            conn.execute(
                snapshot_sql,
                base_snapshot_params
                | {
                    "sid": None,
                    "cls": None,
                    "m": '{"schemaVersion":"1.0","durationSeconds":null,'
                    '"knowledgePoints":[],"suggestions":[]}',
                },
            )

    job_sql = text(
        "INSERT INTO report_jobs"
        " (id, requested_by_user_id, student_user_id, class_id, consumer_id,"
        "  period_start, period_end, status, idempotency_key, error_code, report_id,"
        "  created_at, finished_at)"
        " VALUES (:id, :rid, :sid, :cls, :cid, :ps, :pe, :status, :key, NULL, :rep,"
        "  :created, :fin)"
    )
    now = datetime.now(UTC)
    base_job_params: dict[str, Any] = {
        "rid": STUDENT_A,
        "sid": STUDENT_A,
        "cls": None,
        "cid": consumer_id,
        "ps": PERIOD_START,
        "pe": PERIOD_END,
        "created": now,
    }
    with pytest.raises(IntegrityError):  # succeeded 必有 report_id
        with pg_engine.begin() as conn:
            conn.execute(
                job_sql,
                base_job_params
                | {
                    "id": "job_raw_c",
                    "status": "succeeded",
                    "key": "raw-c",
                    "rep": None,
                    "fin": now,
                },
            )
    with pytest.raises(IntegrityError):  # 终态才有 finished_at：queued 不得有
        with pg_engine.begin() as conn:
            conn.execute(
                job_sql,
                base_job_params
                | {"id": "job_raw_d", "status": "queued", "key": "raw-d", "rep": None, "fin": now},
            )
    with pytest.raises(IntegrityError):  # 状态枚举
        with pg_engine.begin() as conn:
            conn.execute(
                job_sql,
                base_job_params
                | {"id": "job_raw_e", "status": "bogus", "key": "raw-e", "rep": None, "fin": None},
            )


def test_quarantined_list_and_replay(pg_engine: Engine) -> None:
    """隔离区：admin 列表与 status 筛选；replay 置 retry_ready（不改源事件）。"""
    _seed(pg_engine, with_events=False)
    insert_event(
        pg_engine,
        event_id="event_" + "4" * 32,
        event_type="chapter_viewed",
        user_id=STUDENT_A,
        course_id=COURSE,
        class_id=CLASS_A,
        occurred_at=BASE,
        payload={"chapterId": "chapter_1"},
    )
    insert_event(
        pg_engine,
        event_id="bad_event",  # eventId 不满足 event_+32hex：契约外毒事件
        event_type="chapter_viewed",
        user_id=STUDENT_A,
        course_id=COURSE,
        class_id=CLASS_A,
        occurred_at=BASE,
        payload={"chapterId": "chapter_1"},
    )
    worker, _ = make_worker(pg_engine)
    result = worker.poll_once("teacher-overview", "v1")
    assert result.applied == 1 and result.quarantined == 1

    service = _service(pg_engine)
    listed = service.list_quarantined(actor=_admin_actor())
    assert listed.total == 1
    row = listed.items[0]
    assert row.status == "open" and row.error_code == "schema_violation" and row.attempts == 1
    assert service.list_quarantined(actor=_admin_actor(), status="open").total == 1
    assert service.list_quarantined(actor=_admin_actor(), status="resolved").total == 0
    with pytest.raises(InvalidQueryError):
        service.list_quarantined(actor=_admin_actor(), status="bogus")

    replayed = service.replay_quarantined(
        quarantine_id=row.quarantine_id,
        reason="上游修复后受控重放",
        actor=_admin_actor(),
        idempotency_key="replay-1",
    )
    assert replayed.status == "retry_ready"
    assert service.list_quarantined(actor=_admin_actor(), status="retry_ready").total == 1
    # 重复重放幂等：仍为 retry_ready，不重复登记
    assert (
        service.replay_quarantined(
            quarantine_id=row.quarantine_id,
            reason="重复调用",
            actor=_admin_actor(),
            idempotency_key="replay-2",
        ).status
        == "retry_ready"
    )
    with pytest.raises(QuarantinedEventNotFoundError):
        service.replay_quarantined(
            quarantine_id="quarantine_" + "f" * 32,
            reason="不存在的隔离行",
            actor=_admin_actor(),
            idempotency_key="replay-3",
        )
    with pytest.raises(InvalidQueryError):  # reason 长度 1—300
        service.replay_quarantined(
            quarantine_id=row.quarantine_id,
            reason="",
            actor=_admin_actor(),
            idempotency_key="replay-4",
        )
    with pytest.raises(InvalidQueryError):
        service.replay_quarantined(
            quarantine_id=row.quarantine_id,
            reason="r" * 301,
            actor=_admin_actor(),
            idempotency_key="replay-5",
        )
    # 非 admin 访问隔离区：403
    with pytest.raises(ReportForbiddenError):
        service.list_quarantined(actor=_student_actor())
    with pytest.raises(ReportForbiddenError):
        service.replay_quarantined(
            quarantine_id=row.quarantine_id,
            reason="学生无权重放",
            actor=_teacher_actor(),
            idempotency_key="replay-6",
        )
    with Session(pg_engine) as raw:  # 源事件未被改动
        event_type = raw.execute(
            text("SELECT event_type FROM learning_events WHERE id = 'bad_event'")
        ).scalar_one()
        assert event_type == "chapter_viewed"


def test_student_cannot_read_others_report(pg_engine: Engine) -> None:
    """越权：student 读他人报告/任务 404（统一防枚举）；请求他人目标 403。"""
    _seed(pg_engine, with_events=False)
    outcome = _create_personal(pg_engine, actor=_teacher_actor(), student_user_id=STUDENT_B)
    service = _service(pg_engine)
    with pytest.raises(ReportNotFoundError):  # 越权与不存在统一 404
        service.get_report(report_id=outcome.report.report_id, actor=_student_actor())
    owned = service.get_report(report_id=outcome.report.report_id, actor=_student_actor(STUDENT_B))
    assert owned.report_id == outcome.report.report_id
    assert (
        service.get_report(report_id=outcome.report.report_id, actor=_teacher_actor()).report_id
        == outcome.report.report_id
    )
    with pytest.raises(ReportNotFoundError):
        service.get_report(report_id="report_" + "e" * 32, actor=_teacher_actor())
    with pytest.raises(ReportJobNotFoundError):
        service.get_job(job_id="job_" + "e" * 32, actor=_teacher_actor())
    with pytest.raises(ReportJobNotFoundError):  # 他人任务
        service.get_job(job_id=outcome.job.job_id, actor=_student_actor())
    assert (
        service.get_job(job_id=outcome.job.job_id, actor=_student_actor(STUDENT_B)).job_id
        == outcome.job.job_id
    )
    with pytest.raises(ReportForbiddenError):  # 学生只能请求本人报告
        _create_personal(pg_engine, actor=_student_actor(), student_user_id=STUDENT_B)
    with pytest.raises(ReportForbiddenError):  # 学生不能请求班级报告
        _create_class(pg_engine, actor=_student_actor(), class_id=CLASS_A)


def test_list_reports_filters_by_role_and_paginates(pg_engine: Engine) -> None:
    """列表：学生仅本人，teacher 全量（本批最小授权）；分页与 sort 白名单。"""
    _seed(pg_engine, with_events=False)
    service = _service(pg_engine)
    _create_personal(pg_engine, actor=_teacher_actor(), student_user_id=STUDENT_A, key="k-a1")
    _create_personal(
        pg_engine,
        actor=_teacher_actor(),
        student_user_id=STUDENT_A,
        period_start=EMPTY_START,
        period_end=EMPTY_END,
        key="k-a2",
    )
    _create_personal(pg_engine, actor=_teacher_actor(), student_user_id=STUDENT_B, key="k-b1")
    mine = service.list_reports(actor=_student_actor())
    assert mine.total == 2
    assert {item.student_user_id for item in mine.items} == {STUDENT_A}
    theirs = service.list_reports(actor=_student_actor(STUDENT_B))
    assert theirs.total == 1
    everything = service.list_reports(actor=_teacher_actor())
    assert everything.total == 3
    generated = [item.generated_at for item in everything.items]
    assert all(a >= b for a, b in zip(generated, generated[1:], strict=False))  # 默认 -created_at
    ascending = service.list_reports(actor=_teacher_actor(), sort="created_at")
    assert [item.generated_at for item in ascending.items] == list(reversed(generated))
    paged = service.list_reports(actor=_teacher_actor(), page=2, page_size=1)
    assert paged.total == 3 and len(paged.items) == 1 and paged.page == 2
    with pytest.raises(InvalidQueryError):
        service.list_reports(actor=_teacher_actor(), page=0)
    with pytest.raises(InvalidQueryError):
        service.list_reports(actor=_teacher_actor(), page_size=0)
    with pytest.raises(InvalidQueryError):
        service.list_reports(actor=_teacher_actor(), sort="bogus")


def test_create_job_validation_errors(pg_engine: Engine) -> None:
    """422 校验：目标恰好一个、周期、时区白名单、幂等键格式；失败不落任何行。"""
    _seed(pg_engine, with_events=False)
    service = _service(pg_engine)

    def expect_invalid(**kwargs: Any) -> None:
        params: dict[str, Any] = {
            "actor": _student_actor(),
            "student_user_id": None,
            "class_id": None,
            "period_start": PERIOD_START,
            "period_end": PERIOD_END,
            "timezone": TZ,
            "idempotency_key": KEY,
        }
        params.update(kwargs)
        with pytest.raises(InvalidQueryError):
            service.create_job(**params)

    expect_invalid(student_user_id=STUDENT_A, class_id=CLASS_A)  # 双目标
    expect_invalid(student_user_id=None, class_id=None)  # 无目标
    expect_invalid(period_end=PERIOD_START)  # end <= start
    expect_invalid(period_start=BASE.replace(tzinfo=None))  # naive datetime
    expect_invalid(timezone="UTC")  # 本批仅接受 Asia/Shanghai
    expect_invalid(timezone="Mars/Olympus_Mons")  # 非法 IANA 时区
    expect_invalid(idempotency_key="bad key with space")
    with Session(pg_engine) as s, s.begin():  # 校验失败不落任何行
        assert s.execute(select(func.count()).select_from(ReportJob)).scalar_one() == 0
        assert (
            s.execute(select(func.count()).select_from(AnalyticsReportSnapshot)).scalar_one() == 0
        )
