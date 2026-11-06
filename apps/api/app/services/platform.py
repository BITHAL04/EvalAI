"""Cross-cutting helpers: audit trail, notifications, jobs, rate limits, AI access."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ai_engine.providers.base import AIProvider
from ai_engine.providers.factory import AINotConfigured, build_gemini
from app.core.config import ConfigurationError, get_settings
from app.core.errors import DomainError
from app.models import AuditLog, BackgroundJob, InstitutionMembership, JobStatus, Notification, RateLimitHit, Role, RoleRow


def audit(db: Session, action: str, entity_type: str, entity_id: Any = None, *, institution_id: UUID | None = None,
          actor_id: UUID | None = None, actor_type: str = "user", before: dict | None = None, after: dict | None = None) -> None:
    tenant = db.info.get("institution_id")
    db.add(AuditLog(institution_id=institution_id or (UUID(tenant) if tenant else None), actor_id=actor_id, actor_type=actor_type,
                    action=action, entity_type=entity_type, entity_id=str(entity_id) if entity_id else None, before=before, after=after))


def notify(db: Session, user_id: UUID, kind: str, title: str, body: str = "", link: str | None = None,
           institution_id: UUID | None = None) -> None:
    db.add(Notification(user_id=user_id, kind=kind, title=title, body=body, link=link, institution_id=institution_id))


def notify_staff(db: Session, institution_id: UUID, kind: str, title: str, body: str = "", link: str | None = None) -> None:
    ids = db.scalars(select(InstitutionMembership.user_id).join(RoleRow).where(
        InstitutionMembership.institution_id == institution_id, InstitutionMembership.is_active.is_(True),
        RoleRow.name == Role.teacher.value)).all()
    for uid in ids:
        notify(db, uid, kind, title, body, link, institution_id)


def enqueue(db: Session, job_type: str, payload: dict, key: str, institution_id: UUID) -> BackgroundJob:
    """Idempotent: the same key returns the existing job instead of doing the work twice."""
    stmt = insert(BackgroundJob).values(job_type=job_type, payload=payload, idempotency_key=key, institution_id=institution_id,
                                        status=JobStatus.queued.value, attempts=0, max_attempts=4, progress={})
    db.execute(stmt.on_conflict_do_nothing(index_elements=["idempotency_key"]))
    return db.scalar(select(BackgroundJob).where(BackgroundJob.idempotency_key == key))


def rate_limit(db: Session, key: str, limit: int | None = None) -> None:
    limit = limit or get_settings().ai_rate_limit_per_minute
    window = datetime.now(UTC).replace(second=0, microsecond=0)
    stmt = insert(RateLimitHit).values(key=key, window_start=window, count=1)
    stmt = stmt.on_conflict_do_update(index_elements=["key", "window_start"], set_={"count": RateLimitHit.count + 1}).returning(RateLimitHit.count)
    count = db.execute(stmt).scalar_one()
    db.commit()
    if count > limit:
        raise DomainError(429, "rate_limited", "Too many AI requests. Try again in a minute.")


def get_ai() -> AIProvider:
    s = get_settings()
    try:
        return build_gemini(s.gemini_api_key, s.gemini_model, s.gemini_embedding_model, s.gemini_vision_model, s.embedding_dimensions,
                            s.ai_request_timeout, s.ai_max_retries, s.gemini_base_url)
    except AINotConfigured as exc:
        raise ConfigurationError(str(exc)) from exc


def require_ai() -> None:
    """Fail at request time, with guidance, rather than later inside a job."""
    get_ai()


def page(db: Session, stmt, limit: int, offset: int) -> tuple[list, int]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    return list(db.scalars(stmt.limit(limit).offset(offset)).unique().all()), total


def healthcheck(db: Session) -> None:
    db.execute(text("select 1"))
