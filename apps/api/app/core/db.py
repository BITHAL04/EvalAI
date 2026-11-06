"""Engine and session handling, including the tenant context that drives Postgres RLS."""
from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import ConfigurationError, get_settings

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        s = get_settings()
        if not s.database_url:
            raise ConfigurationError("DATABASE_URL is not set. See docs/DEPLOYMENT.md.")
        _engine = create_engine(s.database_url, pool_pre_ping=True, pool_size=s.database_pool_size, max_overflow=5)
    return _engine


def session_factory() -> sessionmaker[Session]:
    global _factory
    if _factory is None:
        _factory = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _factory


def reset_engine() -> None:
    global _engine, _factory
    if _engine is not None:
        _engine.dispose()
    _engine, _factory = None, None


def set_tenant(session: Session, institution_id: UUID | str | None, *, platform: bool = False) -> None:
    """Record the tenant on the session; applied to each transaction by the hook below."""
    session.info["institution_id"] = str(institution_id) if institution_id else ""
    session.info["platform"] = platform
    conn = session.connection()
    _apply(conn, session.info)


def _apply(conn, info: dict) -> None:
    conn.execute(
        text("select set_config('app.institution_id', :i, true), set_config('app.platform', :p, true)"),
        {"i": info.get("institution_id", ""), "p": "on" if info.get("platform") else "off"},
    )


@event.listens_for(Session, "after_begin")
def _reapply_tenant(session: Session, transaction, connection) -> None:
    if "institution_id" in session.info or session.info.get("platform"):
        _apply(connection, session.info)


@event.listens_for(Session, "before_flush")
def _stamp_institution(session: Session, flush_context, instances) -> None:
    tenant = session.info.get("institution_id")
    for obj in session.new:
        if hasattr(obj, "institution_id") and getattr(obj, "institution_id", None) is None and tenant:
            obj.institution_id = UUID(tenant)


def get_db() -> Iterator[Session]:
    db = session_factory()()
    try:
        yield db
    finally:
        db.close()


def system_session() -> Session:
    """Session for the worker and scripts: crosses tenants, never reachable from a request."""
    db = session_factory()()
    db.info["platform"] = True
    db.info["institution_id"] = ""
    return db
