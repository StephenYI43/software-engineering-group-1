"""Explicit registry: add accepted domain model imports here, not another Base."""

from app.core.db import models as platform_models
from app.core.db.base import Base

__all__ = ["Base", "platform_models"]
