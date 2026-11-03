"""Two-phase local integration probe across API and PostgreSQL process restarts.

The state file contains a synthetic token: keep it outside Git, never print it.
Only use a disposable local *_test DB. This tool does not restart services itself.
"""

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy import select

from app.core.auth.settings import load_auth_settings
from app.core.auth.tokens import SessionAuthority
from app.core.db.models import AdminAuditLog, AuthSession, SystemConfigVersion, User
from app.core.db.repository import DatabaseSessionStore
from app.core.db.seed import seed
from app.core.db.session import Database, load_database_url
from app.core.request_id import create_request_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["write", "read"], required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--api-url", default="http://127.0.0.1:58048")
    args = parser.parse_args()
    url = load_database_url()
    if (
        url is None
        or url.host not in ("127.0.0.1", "localhost")
        or not (url.database or "").endswith("_test")
    ):
        raise SystemExit("Probe requires a disposable local *_test database")
    if urlparse(args.api_url).hostname not in ("127.0.0.1", "localhost"):
        raise SystemExit("Probe only calls a local API")
    database = Database(url)
    try:
        if args.phase == "write":
            seed(database)
            seed(database)
            with httpx.Client(base_url=args.api_url, timeout=10, trust_env=False) as client:
                response = client.post(
                    "/api/v1/auth/login",
                    json={
                        "username": "student1",
                        "password": "demo-student-1",
                    },
                )
                response.raise_for_status()
                token = response.json()["token"]
                client.post(
                    "/api/v1/auth/logout",
                    headers={
                        "Authorization": f"Bearer {token}",
                    },
                ).raise_for_status()
            with database.sessions() as session:
                snapshot = {
                    "user_ids": sorted(session.scalars(select(User.id))),
                    "config_ids": sorted(session.scalars(select(SystemConfigVersion.id))),
                    "session_ids": sorted(session.scalars(select(AuthSession.id))),
                    "audit_ids": sorted(session.scalars(select(AdminAuditLog.id))),
                    "token": token,
                }
            args.state.write_text(json.dumps(snapshot), encoding="utf-8")
            print(
                "WRITE: 4 synthetic users, configs, session and audit committed; token not logged."
            )
        else:
            snapshot = json.loads(args.state.read_text(encoding="utf-8"))
            with database.sessions.begin() as session:
                for key, model in (
                    ("user_ids", User),
                    ("config_ids", SystemConfigVersion),
                    ("session_ids", AuthSession),
                    ("audit_ids", AdminAuditLog),
                ):
                    assert sorted(session.scalars(select(model.id))) == snapshot[key], key
                authority = SessionAuthority(
                    load_auth_settings().session_secret,
                    86400,
                    DatabaseSessionStore(session, create_request_id()),
                )
                assert authority.parse(snapshot["token"]) is None, "revoked token revived"
            with httpx.Client(base_url=args.api_url, timeout=10, trust_env=False) as client:
                assert client.get("/api/v1/health").status_code == 200
                assert (
                    client.post(
                        "/api/v1/auth/login",
                        json={
                            "username": "student1",
                            "password": "wrong",
                        },
                    ).status_code
                    == 401
                )
            print("READ: same IDs/records after restart; revoked token rejected; bad password 401.")
    finally:
        database.close()


if __name__ == "__main__":
    main()
