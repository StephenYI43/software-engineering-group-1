"""真实 PG 集成测试的共享夹具：平台 schema + analytics 测试表 + 合成种子。

仅当 ``TEST_DATABASE_URL`` 指向**显式可丢弃的临时 PostgreSQL 测试库**时启用；
未设置则整模块 skip（CI 由容器夹具提供该变量；本地未实测须如实标注）。

schema 生命周期（#84 合入后与 tests/db 平台测试共用同一测试库）：

- 平台表（users 等）由 Alembic 迁移链统一建表，本夹具只升级到 head、
  不 DROP 平台表，种子用户按平台权威模型（含 id/username CHECK）插入；
- M5 尚未接管的源表（``learning_events``/``courses``/``classes`` 最小列）与
  analytics 四表仍由本夹具以 ``AnalyticsBase.metadata`` 重建，使 ORM 外键可解析、
  约束在测试库真实生效；
- teardown 还原为纯迁移 schema（只删本夹具建的表），保证同进程内
  ``tests/db`` 的迁移圆整断言（DB 表集合 == 共享 metadata + alembic_version）成立。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import (
    Column,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    insert,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.db.models import User
from app.domains.analytics.pg_consumer import AnalyticsPgWorker
from app.domains.analytics.pg_models import AnalyticsBase, learning_events

ROOT = Path(__file__).resolve().parents[2]

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")

_TEST_TABLES = (
    "analytics_quarantined_events",
    "analytics_daily_metrics",
    "analytics_processed_events",
    "analytics_consumers",
    "learning_events",
    "classes",
    "courses",
)

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


def _drop_test_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        for name in _TEST_TABLES:
            conn.execute(text(f'DROP TABLE IF EXISTS "{name}" CASCADE'))


def create_schema(engine: Engine) -> None:
    """升级平台迁移链后重建 analytics 测试 schema；平台表只清数据不重建。

    DATABASE_URL 仅在 alembic 升级期间设置并立即还原，避免泄漏到其他测试
    （auth/external_login 按该变量选择 database 模式）。
    """
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    try:
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
    _drop_test_tables(engine)
    with engine.begin() as conn:
        # 平台 users 表保留迁移权威 schema（含 id/username CHECK），只清空旧种子。
        conn.execute(text("DELETE FROM users"))
    AnalyticsBase.metadata.create_all(engine)


def seed_identity(engine: Engine, *, course_id: str, class_id: str, students: list[str]) -> None:
    """合成身份/课程/班级种子（单课单班；幂等由整库重建保证）。

    用户行按平台权威 ``users`` 模型插入：id 须满足 ``^user_[0-9a-f]{32}$``，
    username/username_key/password_hash 为迁移 NOT NULL 列。
    """
    with engine.begin() as conn:
        conn.execute(
            insert(User.__table__),
            [
                {
                    "id": user_id,
                    "username": user_id,
                    "username_key": user_id,
                    "password_hash": "test-only",
                    "status": "active",
                }
                for user_id in students
            ],
        )
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
    """每个测试一个干净的 analytics schema；未配置 TEST_DATABASE_URL 时跳过。"""
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL 未设置")
    engine = create_engine(TEST_DATABASE_URL)
    create_schema(engine)
    try:
        yield engine
    finally:
        _drop_test_tables(engine)
        engine.dispose()
