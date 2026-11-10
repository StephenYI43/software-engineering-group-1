"""PostgreSQL checks use the isolated database fixture."""

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.db.models import User
from app.core.db.session import Database
from app.domains.media.models import AvatarConfigVersion, AvatarProfile
from app.domains.media.preferences import MediaPreferences
from app.domains.media.repository import MediaRepository
from app.domains.media.seed import seed_default_avatar

pytestmark = pytest.mark.postgres
USER_A = "user_" + "a" * 32
USER_B = "user_" + "b" * 32


def test_preferences_seed_isolation_update_and_rollback(database: Database) -> None:
    with database.sessions.begin() as session:
        session.add_all(
            [
                User(id=USER_A, username="alice", username_key="alice", password_hash="synthetic"),
                User(id=USER_B, username="bob", username_key="bob", password_hash="synthetic"),
            ]
        )
        seed_default_avatar(session)
    with database.sessions.begin() as session:
        seed_default_avatar(session)
        assert session.scalar(select(func.count()).select_from(AvatarConfigVersion)) == 1
        repo = MediaRepository(session)
        assert repo.get_preferences(USER_A) == MediaPreferences()
        assert session.scalar(select(func.count()).select_from(AvatarProfile)) == 0
        repo.save_preferences(USER_A, MediaPreferences(auto_play=True, volume=Decimal("0.50")))
        assert repo.get_preferences(USER_A).volume == Decimal("0.50")
        repo.save_preferences(USER_A, MediaPreferences(auto_play=True, volume=Decimal("0.75")))
        assert repo.get_preferences(USER_A).volume == Decimal("0.75")
    with database.sessions() as session:
        repo = MediaRepository(session)
        assert repo.get_preferences(USER_A).volume == Decimal("0.75")
        assert repo.get_preferences(USER_B) == MediaPreferences()
        assert session.scalar(select(func.count()).select_from(AvatarProfile)) == 1
        repo.save_preferences(USER_B, MediaPreferences(auto_play=True))
        session.rollback()
    with database.sessions() as session:
        assert MediaRepository(session).get_preferences(USER_B) == MediaPreferences()
