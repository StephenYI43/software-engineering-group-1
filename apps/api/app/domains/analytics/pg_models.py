"""analytics 域 B 批先落地四张表的 ORM 映射（只读 feed + 三张管理表 + 日统计）。

形状来源：``docs/database-design/schema.sql``（PR #79，head 8061f4b）与
《第一组 数据库设计.docx》表 5-35/36/37/40；摄取协议见同文档 §4.3 与
``docs/database-design/decisions.md``「不漏迟到提交的账本协议」。

边界说明（如实记录）：

- 权威模型归 M1 的 ``app.core.db``（PR #75 底座）。#75 尚未合入 main，
  本模块暂用**本域私有 Base**（命名约定与 #75 的 ``Base`` 完全一致）；
  #75 合入后切换 import 并由 M1 登记 metadata，不保留第二套 Base。
- ``learning_events`` 是 M5 的表，本模块只定义**只读 Core 表**用于消费查询，
  不写该表、不生成它的迁移。
- 迁移：本批不提交 Alembic revision（单链由 M5 协调登记）；
  测试用 ``create_all`` 建表，仅限显式可丢弃的临时测试库。
- 报告快照与任务表（schema.sql 表 5-38/39）按 M1 2026-10-24 指令后排，
  本批不建模型。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    MetaData,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

_NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class AnalyticsBase(DeclarativeBase):
    """本域私有 Base；#75 合入后由 app.core.db.Base 替换（命名约定一致，可直接迁移）。"""

    metadata = MetaData(naming_convention=_NAMING)


class AnalyticsConsumer(AnalyticsBase):
    """消费者与算法发布状态（表 5-35）。每轮轮询锁本行串行化同消费者。"""

    __tablename__ = "analytics_consumers"
    __table_args__ = (
        UniqueConstraint("consumer_key", "algorithm_version"),
        CheckConstraint("status IN ('active','paused','retired')", name="status_enum"),
        CheckConstraint("processed_count >= 0", name="processed_count_nonneg"),
        CheckConstraint("updated_at >= created_at", name="updated_not_before_created"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    consumer_key: Mapped[str] = mapped_column(String(64))
    algorithm_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="paused", server_default="paused")
    last_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp()
    )


class AnalyticsProcessedEvent(AnalyticsBase):
    """已处理事件账本（表 5-36）。(consumer, event) 唯一；与聚合同事务写入。"""

    __tablename__ = "analytics_processed_events"
    __table_args__ = (CheckConstraint("source_hash ~ '^[0-9a-f]{64}$'", name="source_hash_hex"),)

    consumer_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("analytics_consumers.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("learning_events.id", ondelete="RESTRICT"), primary_key=True
    )
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp()
    )
    source_hash: Mapped[str] = mapped_column(String(64))


class AnalyticsDailyMetric(AnalyticsBase):
    """学生班级日统计（表 5-37）。行只在有已处理事件时存在（unknown 不落库，读侧合成）。"""

    __tablename__ = "analytics_daily_metrics"
    __table_args__ = (
        UniqueConstraint(
            "consumer_id",
            "student_user_id",
            "course_id",
            "class_id",
            "metric_date",
            "timezone",
            postgresql_nulls_not_distinct=True,
        ),
        ForeignKeyConstraint(
            ["class_id", "course_id"],
            ["classes.id", "classes.course_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("class_id IS NULL OR course_id IS NOT NULL", name="class_requires_course"),
        CheckConstraint(
            "data_state <> 'unknown' OR study_seconds IS NULL", name="unknown_has_no_seconds"
        ),
        CheckConstraint("study_seconds IS NULL OR study_seconds >= 0", name="study_seconds_nonneg"),
        CheckConstraint("data_state IN ('unknown','partial','known')", name="data_state_enum"),
        CheckConstraint("updated_at >= created_at", name="updated_not_before_created"),
        Index("ix_daily_class_date", "consumer_id", "class_id", "metric_date"),
        Index("ix_daily_student_date", "consumer_id", "student_user_id", "metric_date"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    consumer_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("analytics_consumers.id", ondelete="RESTRICT"),
    )
    student_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT")
    )
    course_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("courses.id", ondelete="RESTRICT")
    )
    class_id: Mapped[str | None] = mapped_column(String(64))
    metric_date: Mapped[Any] = mapped_column(Date)
    timezone: Mapped[str] = mapped_column(
        String(64), default="Asia/Shanghai", server_default="Asia/Shanghai"
    )
    study_seconds: Mapped[int | None] = mapped_column()
    submission_count: Mapped[int] = mapped_column(default=0, server_default="0")
    wrong_count: Mapped[int] = mapped_column(default=0, server_default="0")
    sample_count: Mapped[int] = mapped_column(default=0, server_default="0")
    data_state: Mapped[str] = mapped_column(String(32), default="known", server_default="known")
    data_through: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp()
    )


class AnalyticsQuarantinedEvent(AnalyticsBase):
    """毒事件隔离与审计重放（表 5-40）。open 显式告警，不静默跳过。"""

    __tablename__ = "analytics_quarantined_events"
    __table_args__ = (
        UniqueConstraint("consumer_id", "event_id"),
        CheckConstraint("status IN ('open','retry_ready','resolved')", name="status_enum"),
        CheckConstraint("attempts >= 1", name="attempts_at_least_one"),
        CheckConstraint("last_failed_at >= first_failed_at", name="failed_order"),
        CheckConstraint(
            "(status = 'resolved') = (resolved_at IS NOT NULL)", name="resolved_iff_resolved_at"
        ),
        CheckConstraint(
            "status <> 'resolved' OR resolved_by_user_id IS NOT NULL",
            name="resolved_has_resolver",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    consumer_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("analytics_consumers.id", ondelete="RESTRICT"),
    )
    event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("learning_events.id", ondelete="RESTRICT")
    )
    error_code: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="open", server_default="open")
    attempts: Mapped[int] = mapped_column(default=1, server_default="1")
    resolved_by_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL")
    )
    first_failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp()
    )
    last_failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def learning_events_table() -> Any:
    """M5 ``learning_events`` 的只读 Core 表（消费查询用；权威 DDL 见 schema.sql 400-428 行）。

    返回 ``Table`` 而非 ORM 模型：analytics 只 ``SELECT`` 该表，写入归 M5。
    """
    from sqlalchemy import Column, Table, text

    return Table(
        "learning_events",
        AnalyticsBase.metadata,
        Column("id", String(64), primary_key=True),
        Column("event_type", String(32), nullable=False),
        Column("user_id", String(64), nullable=False),
        Column("course_id", String(64)),
        Column("class_id", String(64)),
        Column("occurred_at", DateTime(timezone=True), nullable=False),
        Column("recorded_at", DateTime(timezone=True), server_default=func.current_timestamp()),
        Column("trace_id", String(36), nullable=False),
        Column("schema_version", String(16), nullable=False, server_default=text("'1.0'")),
        Column("payload", JSONB, nullable=False),
        Column("idempotency_key", String(128)),
        Column("request_hash", String(64)),
        CheckConstraint("class_id IS NULL OR course_id IS NOT NULL", name="class_requires_course"),
    )
