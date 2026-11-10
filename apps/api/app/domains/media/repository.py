"""Preference storage. The caller supplies a verified user ID and owns the transaction."""

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.db.repository import new_id
from app.domains.media.models import AvatarConfigVersion, AvatarProfile
from app.domains.media.preferences import MediaPreferences

DEFAULT_CONFIG_KEY = "default"


class MediaRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_preferences(self, user_id: str) -> MediaPreferences:
        profile = self.session.scalar(select(AvatarProfile).where(AvatarProfile.user_id == user_id))
        if profile is None:
            return MediaPreferences()
        return MediaPreferences(
            profile.auto_play, profile.volume, profile.speech_rate, profile.subtitles_enabled
        )

    def save_preferences(self, user_id: str, preferences: MediaPreferences) -> None:
        config_id = self.session.scalar(
            select(AvatarConfigVersion.id).where(
                AvatarConfigVersion.config_key == DEFAULT_CONFIG_KEY,
                AvatarConfigVersion.status == "active",
            )
        )
        if config_id is None:
            raise RuntimeError("An active default avatar configuration is required")
        statement = insert(AvatarProfile).values(
            id=new_id("avatar"),
            user_id=user_id,
            config_version_id=config_id,
            auto_play=preferences.auto_play,
            volume=preferences.volume,
            speech_rate=preferences.speech_rate,
            subtitles_enabled=preferences.subtitles_enabled,
        )
        self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[AvatarProfile.user_id],
                set_={
                    "auto_play": statement.excluded.auto_play,
                    "volume": statement.excluded.volume,
                    "speech_rate": statement.excluded.speech_rate,
                    "subtitles_enabled": statement.excluded.subtitles_enabled,
                    "updated_at": func.now(),
                },
            ).returning(AvatarProfile),
            execution_options={"populate_existing": True},
        )
