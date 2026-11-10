"""Explicit synthetic avatar configuration seed."""

import argparse
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db.repository import new_id
from app.core.db.session import Database, load_database_url
from app.domains.media.models import AvatarConfigVersion
from app.domains.media.repository import DEFAULT_CONFIG_KEY


def seed_default_avatar(session: Session) -> None:
    """Add the demonstration configuration if no version exists; never overwrite."""
    from sqlalchemy import text

    session.execute(text("SELECT pg_advisory_xact_lock(720001)"))
    existing = session.scalar(
        select(AvatarConfigVersion.id).where(AvatarConfigVersion.config_key == DEFAULT_CONFIG_KEY)
    )
    if existing is None:
        session.add(
            AvatarConfigVersion(
                id=new_id("avatarcfg"),
                config_key=DEFAULT_CONFIG_KEY,
                version=1,
                name="演示默认数字人",
                status="active",
                config={
                    "schemaVersion": "1.0",
                    "avatarAssetKey": "demo/avatar/default",
                    "subjectStyle": "other",
                    "tone": "neutral",
                    "defaultEmotion": "neutral",
                    "defaultAction": "idle",
                },
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-development", action="store_true", required=True)
    parser.parse_args()
    if os.getenv("APP_ENV", "development") != "development":
        raise SystemExit("Synthetic seed is restricted to APP_ENV=development")
    url = load_database_url()
    if url is None:
        raise SystemExit("DATABASE_URL is required")
    database = Database(url)
    try:
        with database.sessions.begin() as session:
            seed_default_avatar(session)
    finally:
        database.close()


if __name__ == "__main__":
    main()
