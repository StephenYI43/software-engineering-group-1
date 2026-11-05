"""Shared database boundary. Domain models must inherit this one Base."""

from app.core.db.base import Base
from app.core.db.session import Database, get_session, load_database_url

__all__ = ["Base", "Database", "get_session", "load_database_url"]
