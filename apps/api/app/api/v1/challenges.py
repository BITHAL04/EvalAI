from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.evaluations import evaluation_out
from app.core.db import get_db
from app.core.deps import Principal, get_principal, staff, student_only
from app.core.errors import bad_request, conflict, not_found
from app.models import (
    AuditLog, Challenge, ChallengeEvidence, ChallengeStatus, Evaluation, ExaminationQuestion, Result, Role, Rubric, Submission, User,
)
from app.schemas.inputs import ChallengeDecisionIn, ChallengeIn
from app.services import challenges as svc
from app.services.platform import audit, enqueue, get_ai, notify_staff, page, rate_limit

router = APIRouter(tags=["challenges"])


def out(db: Session, c: Challenge, *, detail: bool = False, for_student: bool = False) -> dict:
    q = db.get(ExaminationQuestion, c.question_id)
    rubric = db.get(Rubric, c.original_rubric_id)
    disputed = next((x.criterion for x in rubric.criteria if x.id == c.rubric_criterion_id), None)
    u = db.get(User, c.student_id)
    d = {"id": str(c.id), "evaluation_id": str(c.evaluation_id), "question_number": q.question_number, "question_text": q.question_text, "category": c.category, "disputed_criterion": disputed,
         "status": c.status, "explanation": c.explanation, "original_marks": float(c.original_marks), "revised_marks": float(c.revised_marks) if c.revised_marks is not None else None,
         "max_marks": float(q.marks), "created_at": c.created_at, "examination_id": str(c.examination_id), "rubric_version": rubric.version,
         "evidence": [e.content for e in c.evidence],
         "decisions": [{"decision": x.decision, "original_marks": float(x.original_marks), "revised_marks": float(x.revised_marks), "reason": x.reason, "decided_at": x.decided_at} for x in c.decisions]}
    if not for_student:
        d["student"] = u.profile.full_name or u.email
    if detail and not for_student:
        d["ai_reviews"] = [{"recommendation": r.recommendation, "suggested_marks": float(r.suggested_marks) if r.suggested_marks is not None else None, "reasoning": r.reasoning,
                            "confidence": r.confidence, "escalated": r.escalated, "detail": r.detail, "model": r.model} for r in c.reviews]
        d["evaluation"] = evaluation_out(db, db.get(Evaluation, c.evaluation_id))
        d["audit"] = [{"action": a.action, "actor_type": a.actor_type, "before": a.before, "after": a.after, "created_at": a.created_at}
                      for a in db.scalars(select(AuditLog).where(AuditLog.entity_type == "challenge", AuditLog.entity_id == str(c.id)).order_by(AuditLog.created_at))]
    return d


def own(db: Session, p: Principal, cid) -> Challenge:
    c = db.get(Challenge, cid)
    if c is None or c.institution_id != p.institution_id or (p.role == Role.student.value and c.student_id != p.id):
        raise not_found("Challenge")
    return c


@router.post("/challenges", status_code=201)
def create(body: ChallengeIn, p: Principal = Depends(student_only), db: Session = Depends(get_db)):
    e = db.get(Evaluation, body.evaluation_id)
    s = db.get(Submission, e.submission_id) if e else None
    if e is None or s is None or s.student_id != p.id or s.institution_id != p.institution_id:
        raise not_found("Evaluation")
    r = db.scalar(select(Result).where(Result.submission_id == s.id, Result.status == "published"))
    if r is None:
        raise conflict("Results have not been published")
    if body.rubric_criterion_id and not any(x.id == body.rubric_criterion_id for x in db.get(Rubric, e.rubric_id).criteria):
        raise bad_request("That criterion is not part of this rubric")
    if e.marks_awarded is None:
        raise bad_request("This answer has no marks to challenge")
    open_states = (ChallengeStatus.submitted.value, ChallengeStatus.under_ai_review.value, ChallengeStatus.pending_teacher_review.value)
    if db.scalar(select(Challenge).where(Challenge.evaluation_id == e.id, Challenge.status.in_(open_states))):
        raise conflict("You already have an open challenge on this question")
    rate_limit(db, f"challenge:{p.id}", 5)
    c = Challenge(institution_id=p.institution_id, evaluation_id=e.id, submission_id=s.id, question_id=e.question_id, examination_id=s.examination_id, student_id=p.id,
                  category=body.category, rubric_criterion_id=body.rubric_criterion_id, explanation=body.explanation, original_marks=e.marks_awarded, original_rubric_id=e.rubric_id)
    for text in body.evidence:
        c.evidence.append(ChallengeEvidence(institution_id=p.institution_id, content=text[:4000]))
    db.add(c)
    db.flush()
    audit(db, "challenge.submitted", "challenge", c.id, actor_id=p.id, after={"category": c.category, "marks": float(c.original_marks)})
    try:
        get_ai()
        enqueue(db, "assess_challenge", {"challenge_id": str(c.id)}, f"challenge:{c.id}", p.institution_id)
    except Exception:  # noqa: BLE001 - an AI outage must not stop a student raising a dispute
        c.status = ChallengeStatus.pending_teacher_review.value
    notify_staff(db, p.institution_id, "challenge_submitted", "Challenge submitted", s.examination.title, f"/teacher/challenges/{c.id}")
    db.commit()
    return out(db, c, for_student=True)


@router.get("/challenges")
def list_challenges(status: str | None = None, limit: int = 50, offset: int = 0, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    stmt = select(Challenge).where(Challenge.institution_id == p.institution_id).order_by(Challenge.created_at.desc())
    student = p.role == Role.student.value
    if student:
        stmt = stmt.where(Challenge.student_id == p.id)
    if status:
        stmt = stmt.where(Challenge.status == status)
    rows, total = page(db, stmt, min(limit, 100), offset)
    return {"items": [out(db, c, for_student=student) for c in rows], "total": total}


@router.get("/challenges/{cid}")
def get_one(cid: uuid.UUID, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    c = own(db, p, cid)
    return out(db, c, detail=True, for_student=p.role == Role.student.value)


@router.post("/challenges/{cid}/review")
def rerun_ai(cid: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    c = own(db, p, cid)
    if c.status != ChallengeStatus.pending_teacher_review.value:
        raise conflict("Only a challenge awaiting a decision can be re-reviewed")
    get_ai()
    rate_limit(db, f"generate:{p.id}")
    c.status = ChallengeStatus.submitted.value
    job = enqueue(db, "assess_challenge", {"challenge_id": str(c.id)}, f"challenge:{c.id}:{uuid.uuid4()}", p.institution_id)
    db.commit()
    return {"job_id": str(job.id)}


@router.post("/challenges/{cid}/decision")
def decision(cid: uuid.UUID, body: ChallengeDecisionIn, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    c = own(db, p, cid)
    svc.decide(db, c, user_id=p.id, decision=body.decision, revised_marks=body.revised_marks, reason=body.reason, criterion_marks=body.criterion_marks, rubric_note=body.rubric_note)
    db.commit()
    return out(db, c, detail=True)


@router.post("/challenges/{cid}/finalize")
def finalize(cid: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    c = own(db, p, cid)
    if c.status not in (ChallengeStatus.accepted.value, ChallengeStatus.partially_accepted.value, ChallengeStatus.rejected.value):
        raise conflict("Decide this challenge first")
    c.status = ChallengeStatus.resolved.value
    audit(db, "challenge.resolved", "challenge", c.id, actor_id=p.id, after={"marks": float(c.revised_marks)})
    db.commit()
    return out(db, c, detail=True)



