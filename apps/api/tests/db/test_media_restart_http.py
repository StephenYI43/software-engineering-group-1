"""Subprocess HTTP and PostgreSQL restart checks using synthetic accounts only."""

import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from decimal import Decimal

import httpx
import psycopg
import pytest

from app.core.db.seed import seed
from app.core.db.session import Database
from app.domains.media.seed import seed_default_avatar

pytestmark = pytest.mark.postgres
STUDENT_A = "user_" + "1" * 32
STUDENT_B = "user_" + "2" * 32


@contextmanager
def running_test_api(database_url: str):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["AUTH_SESSION_SECRET"] = "integration-test-only-secret-key-" + "x" * 32
    env.pop("AUTH_SYNTHETIC_ACCOUNTS", None)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "tests.db.media_test_app:create_test_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError("Test API process exited before becoming ready")
            try:
                if httpx.get(url + "/api/v1/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Test API process did not become ready")
        yield url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def test_http_owner_and_api_process_restart(database: Database, postgres_url: str) -> None:
    seed(database)
    with database.sessions.begin() as session:
        seed_default_avatar(session)
    with running_test_api(postgres_url) as url:
        a = httpx.post(
            url + "/api/v1/auth/login", json={"username": "student1", "password": "demo-student-1"}
        ).json()["token"]
        b = httpx.post(
            url + "/api/v1/auth/login", json={"username": "student2", "password": "demo-student-2"}
        ).json()["token"]
        a_header = {"Authorization": f"Bearer {a}"}
        b_header = {"Authorization": f"Bearer {b}"}
        assert httpx.get(url + f"/test/media/{STUDENT_A}").status_code == 401
        assert (
            httpx.put(
                url + f"/test/media/{STUDENT_A}", headers=a_header, json={"volume": "0.42"}
            ).status_code
            == 200
        )
        assert httpx.get(url + f"/test/media/{STUDENT_A}", headers=b_header).status_code == 404
        assert (
            httpx.put(
                url + f"/test/media/{STUDENT_A}", headers=b_header, json={"volume": "0.99"}
            ).status_code
            == 404
        )
        assert Decimal(
            httpx.get(url + f"/test/media/{STUDENT_B}", headers=b_header).json()["volume"]
        ) == Decimal("1")
    with running_test_api(postgres_url) as url:
        result = httpx.get(url + f"/test/media/{STUDENT_A}", headers=a_header)
        assert result.status_code == 200
        assert Decimal(result.json()["volume"]) == Decimal("0.42")


def test_managed_postgres_process_restart(
    database: Database, postgres_instance: tuple[str, str | None]
) -> None:
    url, container_name = postgres_instance
    if container_name is None:
        pytest.skip("Database restart only allowed for the test-managed disposable CI container")
    seed(database)
    with database.sessions.begin() as session:
        seed_default_avatar(session)
        from app.domains.media.preferences import MediaPreferences
        from app.domains.media.repository import MediaRepository

        MediaRepository(session).save_preferences(
            STUDENT_A, MediaPreferences(volume=Decimal("0.37"))
        )
    database.engine.dispose()
    subprocess.run(
        ["docker", "restart", "--time", "5", container_name],
        check=True,
        capture_output=True,
        timeout=40,
    )
    for attempt in range(40):
        try:
            with psycopg.connect(
                url.replace("postgresql+psycopg://", "postgresql://"), connect_timeout=2
            ):
                break
        except psycopg.OperationalError:
            if attempt == 39:
                raise
            time.sleep(0.5)
    from app.domains.media.repository import MediaRepository

    with database.sessions() as session:
        assert MediaRepository(session).get_preferences(STUDENT_A).volume == Decimal("0.37")
