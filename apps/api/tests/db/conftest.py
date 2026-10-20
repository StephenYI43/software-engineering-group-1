"""Only operate on an explicitly named disposable local *_test database."""

import os
import secrets
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.core.db.metadata import Base
from app.core.db.session import Database, load_database_url

ROOT = Path(__file__).resolve().parents[2]
IMAGE = (
    "postgres:17.11-bookworm@sha256:"
    "3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826"
)


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """CI owns an ephemeral container; local runs require an explicit test URL.

    No workflow edit or third-party testcontainers dependency is required. CI
    cannot skip these checks: missing Docker/startup failure makes the job fail.
    """
    configured = os.getenv("TEST_DATABASE_URL", "")
    if configured:
        yield configured
        return
    if os.getenv("GITHUB_ACTIONS") != "true":
        pytest.skip("TEST_DATABASE_URL not set; no PostgreSQL test was run")
    name = "m1-platform-test-" + uuid.uuid4().hex
    password = secrets.token_hex(24)
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "--detach",
                "--rm",
                "--name",
                name,
                "--env",
                "POSTGRES_USER=ci",
                "--env",
                "POSTGRES_DB=platform_ci_test",
                "--env",
                f"POSTGRES_PASSWORD={password}",
                "--publish",
                "127.0.0.1::5432",
                IMAGE,
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        port = (
            subprocess.run(
                ["docker", "port", name, "5432/tcp"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            .stdout.strip()
            .rsplit(":", 1)[-1]
        )
        if not port.isdigit():
            raise RuntimeError("Unexpected local PostgreSQL port")
        url = f"postgresql+psycopg://ci:{password}@127.0.0.1:{port}/platform_ci_test"
        for attempt in range(40):
            try:
                with psycopg.connect(
                    host="127.0.0.1",
                    port=int(port),
                    user="ci",
                    password=password,
                    dbname="platform_ci_test",
                    connect_timeout=2,
                ):
                    break
            except psycopg.OperationalError:
                if attempt == 39:
                    raise RuntimeError("CI PostgreSQL did not become ready") from None
                time.sleep(0.5)
        yield url
    finally:
        # Exact generated name; no user databases, volumes or containers touched.
        subprocess.run(
            ["docker", "stop", "--time", "5", name],
            check=False,
            capture_output=True,
            timeout=20,
        )


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch, postgres_url: str) -> Iterator[Database]:
    raw = postgres_url
    url = load_database_url(raw)
    assert url is not None
    if url.host not in ("127.0.0.1", "localhost") or not (url.database or "").endswith("_test"):
        pytest.fail("Refusing DB tests: require local disposable *_test database")
    monkeypatch.setenv("DATABASE_URL", raw)
    config = Config(str(ROOT / "alembic.ini"))
    command.upgrade(config, "head")
    db = Database(url)
    with db.engine.begin() as connection:
        # Table names originate only from the registered platform metadata.
        names = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
        connection.execute(text(f"TRUNCATE {names} CASCADE"))
    try:
        yield db
    finally:
        db.close()
