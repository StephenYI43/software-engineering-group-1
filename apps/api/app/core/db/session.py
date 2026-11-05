"""Explicit PostgreSQL configuration; no automatic migration, seed or fallback."""

import os
from collections.abc import Iterator

from fastapi import HTTPException, Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker


def load_database_url(raw: str | None = None) -> URL | None:
    value = os.getenv("DATABASE_URL", "") if raw is None else raw
    if not value:
        return None
    try:
        url = make_url(value)
    except Exception:
        raise ValueError("DATABASE_URL must be a valid PostgreSQL URL") from None
    if url.drivername not in ("postgresql", "postgresql+psycopg"):
        raise ValueError("DATABASE_URL must use postgresql+psycopg")
    if not url.host or not url.database or not url.username:
        raise ValueError("DATABASE_URL requires host, database and username")
    return url.set(drivername="postgresql+psycopg")


class Database:
    """One engine/factory per application; callers own transaction boundaries."""

    def __init__(self, url: URL) -> None:
        self.engine: Engine = create_engine(
            url,
            pool_pre_ping=True,
            hide_parameters=True,
            connect_args={"connect_timeout": 5, "options": "-c timezone=UTC"},
        )
        self.sessions: sessionmaker[Session] = sessionmaker(
            self.engine, expire_on_commit=False, autoflush=False
        )

    def close(self) -> None:
        self.engine.dispose()


def get_session(request: Request) -> Iterator[Session]:
    """Synchronous FastAPI dependency; close/rollback, never implicitly commit."""
    database: Database | None = getattr(request.app.state, "database", None)
    if database is None:
        raise HTTPException(status_code=503, detail="Database is not configured")
    with database.sessions() as session:
        yield session
