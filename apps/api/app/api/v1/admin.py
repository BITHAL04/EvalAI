from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import TokenClaims
from app.core.db import get_db, set_tenant
from app.core.deps import Principal, admin_only, get_claims
from app.core.errors import DomainError, forbidden
from app.models import (
    AuditLog, Evaluation, Examination, Institution, InstitutionMembership, RoleRow, Result, Subject, Submission, User,
)
from app.schemas.inputs import InstitutionIn
from app.services.platform import audit

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview")
def overview(p: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    i = p.institution_id
    roles = dict(db.execute(select(RoleRow.name, func.count()).join(InstitutionMembership).where(InstitutionMembership.institution_id == i, InstitutionMembership.is_active.is_(True)).group_by(RoleRow.name)).all())
    exams = dict(db.execute(select(Examination.status, func.count()).where(Examination.institution_id == i).group_by(Examination.status)).all())
    evals = db.execute(select(func.count(), func.avg(Evaluation.confidence), func.count().filter(Evaluation.requires_human_review)).where(Evaluation.institution_id == i, Evaluation.is_demo.is_(False))).one()
    from app.models import EvaluationVersion
    teacher_changes = db.scalar(select(func.count(func.distinct(EvaluationVersion.evaluation_id))).where(EvaluationVersion.institution_id == i, EvaluationVersion.actor_type.in_(["teacher", "challenge"])))
    return {"institution": db.get(Institution, i).name, "users": roles, "examinations": exams, "subjects": db.scalar(select(func.count()).select_from(Subject).where(Subject.institution_id == i)),
            "submissions": db.scalar(select(func.count()).select_from(Submission).where(Submission.institution_id == i, Submission.is_current.is_(True))),
            "results": db.scalar(select(func.count()).select_from(Result).where(Result.institution_id == i)),
            "evaluation_quality": {"evaluations": evals[0], "average_confidence": round(float(evals[1]), 3) if evals[1] is not None else None, "flagged_for_review": evals[2], "changed_by_teachers": teacher_changes}}


@router.get("/audit-logs")
def audit_logs(action: str | None = None, limit: int = 50, offset: int = 0, p: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    stmt = select(AuditLog).where(AuditLog.institution_id == p.institution_id).order_by(AuditLog.created_at.desc())
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"%{action}%"))
    rows = db.scalars(stmt.limit(min(limit, 200)).offset(offset)).all()
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    users = {u.id: u.email for u in db.scalars(select(User).where(User.id.in_({a.actor_id for a in rows if a.actor_id}))).unique()}
    return {"total": total, "items": [{"id": str(a.id), "action": a.action, "entity_type": a.entity_type, "entity_id": a.entity_id, "actor": users.get(a.actor_id) or a.actor_type, "before": a.before, "after": a.after, "created_at": a.created_at} for a in rows]}


def _platform(claims: TokenClaims, db: Session) -> User:
    u = db.scalar(select(User).where(User.clerk_user_id == claims.sub))
    if u is None or not u.is_platform_admin:
        raise forbidden("Platform administrators only")
    return u


@router.get("/institutions")
def institutions(claims: TokenClaims = Depends(get_claims), db: Session = Depends(get_db)):
    _platform(claims, db)
    return {"items": [{"id": str(i.id), "name": i.name, "slug": i.slug, "is_active": i.is_active} for i in db.scalars(select(Institution).order_by(Institution.name))]}


@router.post("/institutions", status_code=201)
def create_institution(body: InstitutionIn, claims: TokenClaims = Depends(get_claims), db: Session = Depends(get_db)):
    u = _platform(claims, db)
    if db.scalar(select(Institution).where(Institution.slug == body.slug)):
        raise DomainError(409, "conflict", "That slug is taken")
    i = Institution(name=body.name, slug=body.slug, settings={})
    db.add(i)
    db.flush()
    role = db.scalar(select(RoleRow).where(RoleRow.name == "admin"))
    db.add(InstitutionMembership(institution_id=i.id, user_id=u.id, role_id=role.id))
    set_tenant(db, i.id)
    audit(db, "institution.created", "institution", i.id, actor_id=u.id, institution_id=i.id, after={"name": i.name})
    db.commit()
    return {"id": str(i.id), "name": i.name, "slug": i.slug}


@router.get("/configuration")
def configuration(p: Principal = Depends(admin_only)):
    """Which integrations are configured, and the active thresholds. Never returns secret values."""
    from app.core.config import get_settings
    s = get_settings()
    return {"environment": s.environment, "storage_provider": s.storage_provider,
            "integrations": {"database": bool(s.database_url), "clerk": bool(s.clerk_jwks_url and s.clerk_issuer), "clerk_backend_api": bool(s.clerk_secret_key),
                             "supabase_storage": bool(s.supabase_url and s.supabase_service_role_key), "gemini": bool(s.gemini_api_key and s.gemini_model and s.gemini_embedding_model)},
            "models": {"generation": s.gemini_model or None, "vision": s.gemini_vision_model or s.gemini_model or None, "embedding": s.gemini_embedding_model or None},
            "limits": {"max_upload_size_mb": s.max_upload_size_mb, "max_answer_sheet_pages": s.max_answer_sheet_pages, "ai_rate_limit_per_minute": s.ai_rate_limit_per_minute,
                       "signed_url_ttl_seconds": s.signed_url_ttl_seconds, "ocr_review_threshold": s.ocr_review_threshold, "evaluation_review_threshold": s.evaluation_review_threshold}}
