"""真实 PG 集成测试的共享夹具：建表 + 合成种子。

仅当 ``TEST_DATABASE_URL`` 指向**显式可丢弃的临时 PostgreSQL 测试库**时启用；
未设置则整模块 skip（CI 由 #75 的容器夹具提供该变量；本地未实测须如实标注）。

users / courses / classes 的权威模型归 M1/M5（#75 底座）。此处仅注册**测试所需
最小列**到测试进程的 ``AnalyticsBase.metadata``（使 ORM 外键可解析、约束在测试库
真实生效），不写入任何应用模块、不生成迁移。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest
from sqlalchemy import Column, String, Table, UniqueConstraint, create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.domains.analytics.pg_consumer import AnalyticsPgWorker
from app.domains.analytics.pg_models import AnalyticsBase, learning_events

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")

users_table = Table(
    "users",
    AnalyticsBase.metadata,
    Column("id", String(64), primary_key=True),
    extend_existing=True,
)
courses_table = Table(
    "courses",
    AnalyticsBase.metadata,
    Column("id", String(64), primary_key=True),
    extend_existing=True,
)
classes_table = Table(
    "classes",
    AnalyticsBase.metadata,
    Column("id", String(64), primary_key=True),
    Column("course_id", String(64), nullable=False),
    UniqueConstraint("id", "course_id"),  # schema.sql:170——复合 FK(class_id,course_id) 的引用目标
    extend_existing=True,
)


def create_schema(engine: Engine) -> None:
    """在临时测试库建最小 schema（先删后建，保证测试独立）。"""
    with engine.begin() as conn:
        for ddl in (
            "DROP TABLE IF EXISTS report_jobs CASCADE",
            "DROP TABLE IF EXISTS analytics_report_snapshots CASCADE",
            "DROP TABLE IF EXISTS analytics_quarantined_events CASCADE",
            "DROP TABLE IF EXISTS analytics_daily_metrics CASCADE",
            "DROP TABLE IF EXISTS analytics_processed_events CASCADE",
            "DROP TABLE IF EXISTS analytics_consumers CASCADE",
            "DROP TABLE IF EXISTS learning_events CASCADE",
            "DROP TABLE IF EXISTS classes CASCADE",
            "DROP TABLE IF EXISTS courses CASCADE",
            "DROP TABLE IF EXISTS users CASCADE",
        ):
            conn.execute(text(ddl))
    AnalyticsBase.metadata.create_all(engine)


def seed_identity(engine: Engine, *, course_id: str, class_id: str, students: list[str]) -> None:
    """合成身份/课程/班级种子（学生 A/B、单课单班；幂等由整库重建保证）。"""
    with engine.begin() as conn:
        conn.execute(users_table.insert(), [{"id": user_id} for user_id in students])
        conn.execute(courses_table.insert(), {"id": course_id})
        conn.execute(classes_table.insert(), {"id": class_id, "course_id": course_id})


def insert_event(
    engine: Engine,
    *,
    event_id: str,
    event_type: str,
    user_id: str,
    course_id: str | None,
    class_id: str | None,
    occurred_at: datetime,
    payload: dict[str, Any],
) -> None:
    """向 M5 只读 feed 表插入一条合成事件（trace_id 满足 req_+32hex CHECK）。"""
    with engine.begin() as conn:
        conn.execute(
            learning_events.insert(),
            {
                "id": event_id,
                "event_type": event_type,
                "user_id": user_id,
                "course_id": course_id,
                "class_id": class_id,
                "occurred_at": occurred_at,
                "trace_id": f"req_{event_id[-32:]}",
                "schema_version": "1.0",
                "payload": payload,
            },
        )


def make_worker(engine: Engine) -> tuple[AnalyticsPgWorker, sessionmaker[Session]]:
    """构造独立 engine 的 worker（重启测试用两个 engine 模拟进程重启）。"""
    factory: sessionmaker[Session] = sessionmaker(engine, expire_on_commit=False)
    return AnalyticsPgWorker(factory), factory


requires_pg = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL 未设置：真实 PG 验证仅在 CI/本地临时库执行",
)


@pytest.fixture
def pg_engine() -> Iterator[Engine]:
    """每个测试一个干净的临时 schema；未配置 TEST_DATABASE_URL 时跳过。"""
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL 未设置")
    engine = create_engine(TEST_DATABASE_URL)
    create_schema(engine)
    yield engine
    engine.dispose()
