"""Explicit registry: add accepted domain model imports here, not another Base."""

from app.core.db import models as platform_models
from app.core.db.base import Base
from app.domains.media import models as media_models

__all__ = ["Base", "media_models", "platform_models"]
