"""PostgreSQL constraints and seeds for tutoring sessions and turns."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.core.db.repository import new_id
from app.core.db.seed import seed
from app.core.db.session import Database
from app.domains.tutoring.models import (
    ModelConfigVersion,
    PromptVersion,
    TutoringSession,
    TutoringTurn,
)
from app.domains.tutoring.seed import (
    MODEL_SEED_ID,
    PROMPT_SEED_ID,
    prompt_content_sha256,
)

pytestmark = pytest.mark.postgres
STUDENT = "user_11111111111111111111111111111111"
REQUEST_ID = "req_" + "1" * 32
EMPTY_FOLLOW_UPS = {"schemaVersion": "1.0", "items": []}


def _turn_kwargs(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "id": new_id("turn"),
        "seq": 1,
        "request_id": REQUEST_ID,
        "student_content": "什么是极限？",
        "stage": "thought",
        "status": "active",
        "is_complete": False,
        "is_mock": True,
        "prompt_version_id": PROMPT_SEED_ID,
        "model_config_version_id": MODEL_SEED_ID,
    }
    values.update(overrides)
    return values


def test_migration_creates_tutoring_tables(database: Database) -> None:
    names = set(inspect(database.engine).get_table_names())
    assert {
        "prompt_versions",
        "model_config_versions",
        "tutoring_sessions",
        "tutoring_turns",
    }.issubset(names)
    # The courses table is intentionally absent; course_id has no foreign key yet.
    assert "courses" not in names


def test_seed_registers_prompt_and_mock_config(database: Database) -> None:
    seed(database)
    seed(database)
    with database.sessions() as session:
        prompt = session.get(PromptVersion, PROMPT_SEED_ID)
        model = session.get(ModelConfigVersion, MODEL_SEED_ID)
        assert prompt is not None
        assert prompt.version_label == "guided-tutoring.v1"
        assert prompt.template_path == "ai/prompts/guided-tutoring.v1.md"
        assert prompt.status == "active"
        assert prompt.content_sha256 == prompt_content_sha256()
        assert model is not None
        assert model.config_key == "tutoring_default"
        assert model.provider == "mock"
        assert model.is_mock is True
        assert session.scalar(select(PromptVersion.id)) == PROMPT_SEED_ID
        assert session.scalar(select(ModelConfigVersion.id)) == MODEL_SEED_ID


def _prepare(database: Database) -> None:
    seed(database)


def test_session_accepts_short_sample_id_and_nullable_course(database: Database) -> None:
    _prepare(database)
    with database.sessions.begin() as session:
        session.add(
            TutoringSession(
                id="sess_4b8d1e02",
                student_user_id=STUDENT,
                course_id="course_not_yet_persisted",
            )
        )
    with database.sessions() as session:
        row = session.get(TutoringSession, "sess_4b8d1e02")
        assert row is not None
        assert row.course_id == "course_not_yet_persisted"
        assert row.current_stage == "thought"


def test_one_active_turn_per_session(database: Database) -> None:
    _prepare(database)
    with database.sessions.begin() as session:
        session.add(TutoringSession(id="sess_active_one", student_user_id=STUDENT))
    with database.sessions.begin() as session:
        session.add(TutoringTurn(session_id="sess_active_one", **_turn_kwargs()))
    with pytest.raises(IntegrityError) as failed, database.sessions.begin() as session:
        session.add(
            TutoringTurn(session_id="sess_active_one", **_turn_kwargs(id=new_id("turn"), seq=2))
        )
    assert failed.value.orig.diag.constraint_name == "uq_tutoring_turns_active_session"


def test_completed_turn_requires_payload_and_rejects_errored_status(
    database: Database,
) -> None:
    _prepare(database)
    with database.sessions.begin() as session:
        session.add(TutoringSession(id="sess_complete", student_user_id=STUDENT))
    now = datetime.now(UTC)
    with pytest.raises(IntegrityError) as missing, database.sessions.begin() as session:
        session.add(
            TutoringTurn(
                session_id="sess_complete",
                **_turn_kwargs(
                    status="completed",
                    is_complete=True,
                    settled_at=now,
                ),
            )
        )
    assert missing.value.orig.diag.constraint_name == "ck_tutoring_turns_completed_payload"
    with pytest.raises(IntegrityError) as errored, database.sessions.begin() as session:
        session.add(
            TutoringTurn(
                session_id="sess_complete",
                **_turn_kwargs(id=new_id("turn"), status="errored", is_complete=False),
            )
        )
    assert errored.value.orig.diag.constraint_name == "ck_tutoring_turns_status"
    with database.sessions.begin() as session:
        session.add(
            TutoringTurn(
                session_id="sess_complete",
                **_turn_kwargs(
                    id=new_id("turn"),
                    status="completed",
                    is_complete=True,
                    assistant_content="我们先不急着写出定义。",
                    emotion="thinking",
                    action="idle",
                    settled_at=now,
                ),
            )
        )


def test_abort_mapping_matches_dictionary(database: Database) -> None:
    _prepare(database)
    with database.sessions.begin() as session:
        session.add(TutoringSession(id="sess_abort", student_user_id=STUDENT))
    now = datetime.now(UTC)
    with database.sessions.begin() as session:
        session.add(
            TutoringTurn(
                session_id="sess_abort",
                **_turn_kwargs(
                    status="aborted",
                    is_complete=False,
                    abort_reason="client_stop",
                    assistant_content="半截正文",
                    settled_at=now,
                ),
            )
        )
    with pytest.raises(IntegrityError) as model_missing, database.sessions.begin() as session:
        session.add(
            TutoringTurn(
                session_id="sess_abort",
                **_turn_kwargs(
                    id=new_id("turn"),
                    seq=2,
                    status="aborted",
                    is_complete=False,
                    abort_reason="model_error",
                    settled_at=now,
                ),
            )
        )
    assert model_missing.value.orig.diag.constraint_name == "ck_tutoring_turns_failure_error_code"
    with database.sessions.begin() as session:
        session.add(
            TutoringTurn(
                session_id="sess_abort",
                **_turn_kwargs(
                    id=new_id("turn"),
                    seq=2,
                    status="aborted",
                    is_complete=False,
                    abort_reason="model_error",
                    error_code="MODEL_TIMEOUT",
                    error_reason="upstream_timeout",
                    settled_at=now + timedelta(seconds=1),
                ),
            )
        )
    with pytest.raises(IntegrityError) as completed_error, database.sessions.begin() as session:
        session.add(
            TutoringTurn(
                session_id="sess_abort",
                **_turn_kwargs(
                    id=new_id("turn"),
                    seq=3,
                    status="completed",
                    is_complete=True,
                    assistant_content="完整回答",
                    emotion="neutral",
                    action="nod",
                    error_code="MODEL_TIMEOUT",
                    settled_at=now,
                ),
            )
        )
    assert completed_error.value.orig.diag.constraint_name == "ck_tutoring_turns_error_code_state"


def test_follow_ups_must_be_schema_object(database: Database) -> None:
    _prepare(database)
    with database.sessions.begin() as session:
        session.add(TutoringSession(id="sess_follow", student_user_id=STUDENT))
    with pytest.raises(IntegrityError) as failed, database.sessions.begin() as session:
        session.add(
            TutoringTurn(
                session_id="sess_follow",
                **_turn_kwargs(follow_ups={"schemaVersion": "2.0", "items": []}),
            )
        )
    assert failed.value.orig.diag.constraint_name == "ck_tutoring_turns_follow_ups_schema"
    with database.sessions.begin() as session:
        session.add(
            TutoringTurn(session_id="sess_follow", **_turn_kwargs(id=new_id("turn"), follow_ups=EMPTY_FOLLOW_UPS))
        )
