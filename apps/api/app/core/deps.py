from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import TokenClaims, verify_token
from app.core.db import get_db, set_tenant
from app.core.errors import DomainError, forbidden
from app.models import InstitutionMembership, Role, User


def get_claims(authorization: str | None = Header(default=None)) -> TokenClaims:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise DomainError(401, "not_authenticated", "Sign in to continue")
    return verify_token(authorization.split(" ", 1)[1].strip())


@dataclass
class Principal:
    user: User
    institution_id: UUID
    role: str

    @property
    def id(self) -> UUID:
        return self.user.id


def get_principal(claims: TokenClaims = Depends(get_claims), db: Session = Depends(get_db),
                  x_institution_id: UUID | None = Header(default=None)) -> Principal:
    user = db.scalar(select(User).where(User.clerk_user_id == claims.sub))
    if user is None:
        raise DomainError(403, "not_synced", "Your account has not been set up yet")
    if not user.is_active:
        raise forbidden("This account has been deactivated")
    rows = db.scalars(select(InstitutionMembership).where(
        InstitutionMembership.user_id == user.id, InstitutionMembership.is_active.is_(True))
        .order_by(InstitutionMembership.created_at)).all()
    if not rows:
        raise DomainError(403, "no_membership", "You have not been added to an institution yet. Ask your administrator for an invitation.")
    m = next((r for r in rows if r.institution_id == x_institution_id), None) if x_institution_id else rows[0]
    if m is None:
        raise forbidden("You are not a member of that institution")
    set_tenant(db, m.institution_id)
    return Principal(user=user, institution_id=m.institution_id, role=m.role.name)


def require(*roles: Role):
    names = {r.value for r in roles}

    def dep(p: Principal = Depends(get_principal)) -> Principal:
        if p.role not in names:
            raise forbidden()
        return p
    return dep


staff = require(Role.teacher, Role.admin)
teacher_only = require(Role.teacher)
student_only = require(Role.student)
admin_only = require(Role.admin)
