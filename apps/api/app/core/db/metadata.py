"""Explicit registry: add accepted domain model imports here, not another Base."""

from app.core.db import models as platform_models
from app.core.db.base import Base
from app.domains.tutoring import models as tutoring_models

__all__ = ["Base", "platform_models", "tutoring_models"]
