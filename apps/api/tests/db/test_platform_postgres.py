"""Real PostgreSQL migrations, auth persistence, constraints and atomicity."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.core.auth.tokens import SessionAuthority
from app.core.db.metadata import Base
from app.core.db.models import (
    AdminAuditLog,
    AuthSession,
    SystemConfigVersion,
    User,
    UserRole,
)
from app.core.db.repository import DatabaseSessionStore, PlatformRepository, new_id
from app.core.db.seed import seed
from app.core.db.session import Database, get_session
from app.main import create_app

from .conftest import ROOT

pytestmark = pytest.mark.postgres
STUDENT = "user_11111111111111111111111111111111"
REQUEST_ID = "req_" + "1" * 32


def test_migration_single_head_and_round_trip(database: Database) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    assert ScriptDirectory.from_config(config).get_heads() == ["0001_platform"]
    command.check(config)
    assert set(inspect(database.engine).get_table_names()) == {
        *Base.metadata.tables,
        "alembic_version",
    }
    command.downgrade(config, "base")
    assert inspect(database.engine).get_table_names() == ["alembic_version"]
    command.upgrade(config, "head")
    command.check(config)


def test_seed_is_idempotent_and_hashes_passwords(database: Database) -> None:
    seed(database)
    with database.sessions() as session:
        before = session.scalars(select(User).order_by(User.id)).all()
        snapshot = [(u.id, u.password_hash) for u in before]
    seed(database)
    with database.sessions() as session:
        assert [
            (u.id, u.password_hash) for u in session.scalars(select(User).order_by(User.id))
        ] == snapshot
        assert len(snapshot) == 4
        assert all("demo-" not in value for _, value in snapshot)
        assert session.scalar(select(func.count()).select_from(AdminAuditLog)) == 4
        assert session.scalar(select(func.count()).select_from(SystemConfigVersion)) == 2
        repo = PlatformRepository(session)
        assert repo.authenticate("STUDENT1", "demo-student-1").user_id == STUDENT
        assert repo.authenticate("student1", "wrong") is None
        assert repo.authenticate("missing", "wrong") is None


def test_auth_logout_survives_new_app_and_engine(database: Database) -> None:
    seed(database)
    with TestClient(create_app()) as client:
        data = client.post(
            "/api/v1/auth/login",
            json={
                "username": "student1",
                "password": "demo-student-1",
            },
        ).json()
    token = data["token"]
    with TestClient(create_app()) as client:
        assert client.post(
            "/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"}
        ).json() == {"revoked": True}
        assert (
            client.post(
                "/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"}
            ).status_code
            == 200
        )
    from app.core.auth.settings import load_auth_settings

    with database.sessions.begin() as session:
        authority = SessionAuthority(
            load_auth_settings().session_secret,
            86400,
            DatabaseSessionStore(session, REQUEST_ID),
        )
        assert authority.parse(token) is None
        stored = session.scalar(select(AuthSession))
        assert stored.revoked_at is not None
        assert stored.jti_digest != jwt.decode(token, options={"verify_signature": False})["jti"]
        assert token not in stored.jti_digest
        assert (
            session.scalar(
                select(func.count())
                .select_from(AdminAuditLog)
                .where(AdminAuditLog.action == "session_revoked")
            )
            == 1
        )


def test_active_session_rechecks_role_and_disabled_user(database: Database) -> None:
    seed(database)
    with database.sessions.begin() as session:
        repo = PlatformRepository(session)
        user = repo.authenticate("student1", "demo-student-1")
        authority = SessionAuthority("x" * 64, 86400, DatabaseSessionStore(session, REQUEST_ID))
        token = authority.issue(user).token
    with database.sessions.begin() as session:
        authority = SessionAuthority("x" * 64, 86400, DatabaseSessionStore(session, REQUEST_ID))
        assert authority.parse(token).user_id == STUDENT
        session.get(User, STUDENT).status = "disabled"
        session.flush()
        assert authority.parse(token) is None
    with database.sessions.begin() as session:
        session.get(User, STUDENT).status = "active"
        role = session.get(UserRole, (STUDENT, "student"))
        role.is_primary = False
        role.revoked_at = datetime.now(UTC)
        session.flush()
        assert PlatformRepository(session).authenticate("student1", "demo-student-1") is None
        assert (
            SessionAuthority("x" * 64, 86400, DatabaseSessionStore(session, REQUEST_ID)).parse(
                token
            )
            is None
        )


def test_unknown_signed_session_not_accepted(database: Database) -> None:
    seed(database)
    now = int(datetime.now(UTC).timestamp())
    token = jwt.encode(
        {
            "sub": STUDENT,
            "role": "student",
            "name": "学生甲",
            "jti": "f" * 32,
            "iat": now,
            "exp": now + 60,
        },
        "x" * 64,
        algorithm="HS256",
    )
    with database.sessions() as session:
        assert (
            SessionAuthority("x" * 64, 86400, DatabaseSessionStore(session, REQUEST_ID)).parse(
                token
            )
            is None
        )


def test_atomic_business_and_audit_rollback(database: Database) -> None:
    seed(database)
    with pytest.raises(IntegrityError), database.sessions.begin() as session:
        session.get(User, STUDENT).status = "disabled"
        session.flush()
        PlatformRepository(session).audit(
            actor_user_id="user_" + "f" * 32,
            action="user_disabled",
            target_type="users",
            target_id=STUDENT,
            request_id=REQUEST_ID,
        )
    with database.sessions() as session:
        assert session.get(User, STUDENT).status == "active"
        assert session.scalar(select(func.count()).select_from(AdminAuditLog)) == 4


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO roles(code,name) VALUES('root','invalid')",
        "INSERT INTO user_roles(user_id,role_code) VALUES('user_missing','student')",
        "UPDATE users SET username='STUDENT1', username_key='student1' WHERE username='student2'",
        f"INSERT INTO user_roles(user_id,role_code,is_primary) VALUES('{STUDENT}','teacher',true)",
        "UPDATE user_roles SET revoked_at=now() WHERE is_primary=true",
        "UPDATE system_config_versions SET value='{}'::jsonb",
        "UPDATE system_config_versions SET version=0",
    ],
)
def test_database_constraints_reject_invalid_data(database: Database, statement: str) -> None:
    seed(database)
    with pytest.raises(IntegrityError), database.engine.begin() as connection:
        connection.execute(text(statement))


def test_config_partial_unique_and_session_checks(database: Database) -> None:
    seed(database)
    now = datetime.now(UTC)
    with database.sessions.begin() as session:
        config = session.scalar(
            select(SystemConfigVersion).where(SystemConfigVersion.config_key == "upload_limits")
        )
        config.status, config.activated_at = "active", now
    with pytest.raises(IntegrityError), database.sessions.begin() as session:
        session.add(
            SystemConfigVersion(
                id=new_id("syscfg"),
                config_key="upload_limits",
                version=2,
                status="active",
                activated_at=now,
                value={"schemaVersion": "1.0"},
            )
        )
    with pytest.raises(IntegrityError), database.sessions.begin() as session:
        session.add(
            AuthSession(
                id=new_id("authsess"),
                user_id=STUDENT,
                role_code="student",
                jti_digest="a" * 64,
                issued_at=now,
                expires_at=now - timedelta(seconds=1),
                request_id=REQUEST_ID,
            )
        )
    with pytest.raises(IntegrityError), database.sessions.begin() as session:
        session.add(
            AuthSession(
                id=new_id("authsess"),
                user_id=STUDENT,
                role_code="student",
                jti_digest="a" * 64,
                issued_at=now,
                expires_at=now + timedelta(seconds=30),
                request_id=REQUEST_ID,
                revoked_at=now,
            )
        )


def test_repository_does_not_commit_and_dependency_rolls_back(database: Database) -> None:
    app = FastAPI()
    app.state.database = database
    dependency = get_session(Request({"type": "http", "app": app}))
    session = next(dependency)
    PlatformRepository(session).audit(
        actor_user_id=None,
        action="test",
        target_type="test",
        target_id=None,
        request_id=REQUEST_ID,
    )
    dependency.close()
    with database.sessions() as another:
        assert another.scalar(select(func.count()).select_from(AdminAuditLog)) == 0
    app.state.database = None
    with pytest.raises(HTTPException, match="Database is not configured"):
        next(get_session(Request({"type": "http", "app": app})))


@pytest.mark.parametrize(
    "details",
    [
        {"token": "must-not-log"},
        {"schemaVersion": "2.0"},
        {"schemaVersion": "1.0", "changedFields": "password"},
        {"schemaVersion": "1.0", "reasonCode": "x" * 65},
    ],
)
def test_audit_rejects_unapproved_details(database: Database, details: dict) -> None:
    with pytest.raises(ValueError), database.sessions.begin() as session:
        PlatformRepository(session).audit(
            actor_user_id=None,
            action="test",
            target_type="test",
            target_id=None,
            request_id=REQUEST_ID,
            details=details,
        )
