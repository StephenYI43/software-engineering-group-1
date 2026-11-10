"""Test-only HTTP adapter. This module is never registered by the production app."""

from decimal import Decimal
from typing import Annotated

from fastapi import Depends, Request
from pydantic import BaseModel

from app.core.auth.dependencies import CurrentPrincipal, require_owner, require_user
from app.domains.media.preferences import MediaPreferences
from app.domains.media.repository import MediaRepository
from app.main import create_app


class TestPreferenceBody(BaseModel):
    volume: Decimal


def create_test_app():
    app = create_app()

    @app.get("/test/media/{owner_id}")
    def read(
        owner_id: str, request: Request, user: Annotated[CurrentPrincipal, Depends(require_user)]
    ):
        require_owner(user, owner_id)
        with request.app.state.database.sessions() as session:
            return {"volume": str(MediaRepository(session).get_preferences(user.user_id).volume)}

    @app.put("/test/media/{owner_id}")
    def write(
        owner_id: str,
        payload: TestPreferenceBody,
        request: Request,
        user: Annotated[CurrentPrincipal, Depends(require_user)],
    ):
        require_owner(user, owner_id)
        with request.app.state.database.sessions.begin() as session:
            MediaRepository(session).save_preferences(
                user.user_id, MediaPreferences(volume=payload.volume)
            )
        return {"ok": True}

    return app
