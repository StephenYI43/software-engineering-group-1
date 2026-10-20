"""Pure configuration/hash tests; deliberately no SQLite substitute."""

import pytest
from fastapi.testclient import TestClient

from app.core.db.passwords import hash_password, verify_password
from app.core.db.session import load_database_url
from app.main import create_app


def test_database_url_validation_and_no_credential_leak(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert load_database_url() is None
    for raw in ("bad", "sqlite:///fake.db", "postgresql://missing_db"):
        with pytest.raises(ValueError):
            load_database_url(raw)
    assert (
        load_database_url("postgresql://u:secret@localhost/db").drivername == "postgresql+psycopg"
    )


def test_password_hash_and_corrupt_or_unbounded_parameters() -> None:
    stored = hash_password("correct")
    assert stored != "correct" and verify_password("correct", stored)
    assert not verify_password("wrong", stored)
    for bad in (
        "bad",
        stored.replace("$32768$", "$999999999999$"),
        stored[:-2],
        "scrypt$32768$8$1$" + "z" * 32 + "$" + "a" * 128,
    ):
        assert not verify_password("correct", bad)


def test_configured_database_never_falls_back_to_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:secret@127.0.0.1:1/db")
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/health").status_code == 200
        response = client.post(
            "/api/v1/auth/login",
            json={
                "username": "student1",
                "password": "demo-student-1",
            },
        )
    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_UNAVAILABLE"
    assert "secret" not in response.text and "password" not in response.text
