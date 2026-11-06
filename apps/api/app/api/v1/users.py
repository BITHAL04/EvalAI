from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.auth import TokenClaims, fetch_clerk_profile
from app.core.config import get_settings
from app.core.db import get_db, set_tenant
from app.core.deps import Principal, admin_only, get_claims, get_principal, staff
from app.core.errors import DomainError, bad_request, not_found
from app.models import Institution, InstitutionMembership, Invitation, Notification, Role, RoleRow, User, UserProfile
from app.schemas.inputs import InviteIn, MembershipUpdate
from app.services.platform import audit, page

router = APIRouter(tags=["users"])


def user_out(u: User, role: str | None = None) -> dict:
    return {"id": str(u.id), "email": u.email, "full_name": u.profile.full_name if u.profile else "", "roll_number": u.profile.roll_number if u.profile else None,
            "is_active": u.is_active, "role": role}


def _accept_invites(db: Session, user: User) -> None:
    set_tenant(db, None, platform=True)  # a user can hold invitations from any institution
    for inv in db.scalars(select(Invitation).where(func.lower(Invitation.email) == user.email.lower(), Invitation.accepted_at.is_(None))):
        role = db.scalar(select(RoleRow).where(RoleRow.name == inv.role))
        exists = db.scalar(select(InstitutionMembership).where(InstitutionMembership.user_id == user.id, InstitutionMembership.institution_id == inv.institution_id))
        if not exists:
            db.add(InstitutionMembership(institution_id=inv.institution_id, user_id=user.id, role_id=role.id))
        inv.accepted_at = datetime.now(UTC)
        if inv.full_name and not user.profile.full_name:
            user.profile.full_name = inv.full_name
    db.flush()
    set_tenant(db, None)


@router.post("/users/sync")
def sync(claims: TokenClaims = Depends(get_claims), db: Session = Depends(get_db)):
    """Create or refresh the local user from verified token data. Takes no client input."""
    email, verified, name = claims.email, claims.email_verified is True, claims.name
    if not email or not verified:
        fetched = fetch_clerk_profile(claims.sub)
        if fetched[0]:
            email, verified, name = fetched[0], fetched[1], name or fetched[2]
    if not email:
        raise DomainError(503, "not_configured", "Could not read your email. Set CLERK_SECRET_KEY on the API or add an email claim to the session token.")
    if not verified:
        raise DomainError(403, "email_unverified", "Verify your email address to continue")
    email = email.lower()
    user = db.scalar(select(User).where(or_(User.clerk_user_id == claims.sub, func.lower(User.email) == email)))
    if user and user.clerk_user_id not in (None, claims.sub):
        raise DomainError(409, "conflict", "This email is linked to another account")
    if user is None:
        user = User(clerk_user_id=claims.sub, email=email)
        user.profile = UserProfile(full_name=name or "")
        db.add(user)
    user.clerk_user_id, user.email = claims.sub, email
    if user.profile is None:
        user.profile = UserProfile(full_name=name or "")
    elif name and not user.profile.full_name:
        user.profile.full_name = name
    if email in get_settings().bootstrap_admins:
        user.is_platform_admin = True
    db.flush()
    _accept_invites(db, user)
    audit(db, "user.synced", "user", user.id, actor_id=user.id)
    db.commit()
    return me_payload(db, user)


def me_payload(db: Session, user: User) -> dict:
    rows = db.execute(select(InstitutionMembership, Institution).join(Institution).where(
        InstitutionMembership.user_id == user.id, InstitutionMembership.is_active.is_(True)).order_by(InstitutionMembership.created_at)).all()
    return {**user_out(user), "is_platform_admin": user.is_platform_admin,
            "memberships": [{"institution_id": str(i.id), "institution": i.name, "role": m.role.name} for m, i in rows],
            "role": rows[0][0].role.name if rows else None}


@router.get("/users/me")
def me(claims: TokenClaims = Depends(get_claims), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.clerk_user_id == claims.sub))
    if user is None:
        raise DomainError(403, "not_synced", "Your account has not been set up yet")
    return me_payload(db, user)


@router.get("/users")
def list_users(role: str | None = None, q: str | None = None, limit: int = 50, offset: int = 0, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    stmt = (select(User, RoleRow.name).join(InstitutionMembership, InstitutionMembership.user_id == User.id).join(RoleRow)
            .where(InstitutionMembership.institution_id == p.institution_id).order_by(User.email))
    if role:
        stmt = stmt.where(RoleRow.name == role)
    if q:
        stmt = stmt.outerjoin(UserProfile).where(or_(User.email.ilike(f"%{q}%"), UserProfile.full_name.ilike(f"%{q}%")))
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = db.execute(stmt.limit(min(limit, 200)).offset(offset)).unique().all()
    return {"items": [user_out(u, r) for u, r in rows], "total": total}


@router.get("/invitations")
def invitations(p: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    rows = db.scalars(select(Invitation).where(Invitation.accepted_at.is_(None)).order_by(Invitation.created_at.desc())).all()
    return {"items": [{"id": str(i.id), "email": i.email, "role": i.role, "full_name": i.full_name} for i in rows]}


@router.post("/invitations", status_code=201)
def invite(body: InviteIn, p: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    email = body.email.lower()
    existing = db.scalar(select(User).where(func.lower(User.email) == email))
    role = db.scalar(select(RoleRow).where(RoleRow.name == body.role))
    if existing:
        if db.scalar(select(InstitutionMembership).where(InstitutionMembership.user_id == existing.id, InstitutionMembership.institution_id == p.institution_id)):
            raise bad_request("This person is already a member")
        db.add(InstitutionMembership(institution_id=p.institution_id, user_id=existing.id, role_id=role.id))
    else:
        db.add(Invitation(institution_id=p.institution_id, email=email, role=body.role, full_name=body.full_name, invited_by=p.id))
    audit(db, "user.invited", "invitation", None, actor_id=p.id, after={"email": email, "role": body.role})
    db.commit()
    return {"email": email, "role": body.role, "status": "added" if existing else "invited"}


@router.delete("/invitations/{invitation_id}", status_code=204)
def revoke(invitation_id: str, p: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    inv = db.get(Invitation, invitation_id)
    if inv is None or inv.institution_id != p.institution_id:
        raise not_found("Invitation")
    db.delete(inv)
    db.commit()


@router.put("/users/{user_id}/membership")
def set_membership(user_id: str, body: MembershipUpdate, p: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    m = db.scalar(select(InstitutionMembership).where(InstitutionMembership.user_id == user_id, InstitutionMembership.institution_id == p.institution_id))
    if m is None:
        raise not_found("Member")
    if m.user_id == p.id:
        raise bad_request("You cannot deactivate yourself")
    m.is_active = body.is_active
    audit(db, "membership.updated", "user", user_id, actor_id=p.id, after={"is_active": body.is_active})
    db.commit()
    return {"id": user_id, "is_active": m.is_active}


@router.get("/notifications")
def notifications(unread: bool = False, limit: int = 30, offset: int = 0, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    stmt = select(Notification).where(Notification.user_id == p.id).order_by(Notification.created_at.desc())
    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows, total = page(db, stmt, min(limit, 100), offset)
    unread_count = db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == p.id, Notification.read_at.is_(None)))
    return {"items": [{"id": str(n.id), "kind": n.kind, "title": n.title, "body": n.body, "link": n.link, "read": n.read_at is not None, "created_at": n.created_at} for n in rows],
            "total": total, "unread": unread_count}


@router.post("/notifications/read-all")
def read_all(p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.user_id == p.id, Notification.read_at.is_(None)).update({"read_at": datetime.now(UTC)})
    db.commit()
    return {"ok": True}


__all__ = ["router", "Role"]
