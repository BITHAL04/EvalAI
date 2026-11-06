from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from ai_engine.providers.base import ImageInput
from ai_engine.workflows.challenge import ChallengeInput, assess_challenge
from app.core.errors import bad_request, conflict
from app.core.storage import get_storage
from app.models import (
    Challenge, ChallengeDecision, ChallengeReview, ChallengeStatus, Evaluation, ExaminationQuestion, ExtractedAnswer,
    Rubric, Submission,
)
from app.services.exams import add_rubric
from app.services.grading import D, record_version, refresh_result
from app.services.platform import audit, get_ai, notify, notify_staff
from app.services.retrieval import retriever_for


def assess(db: Session, challenge_id: UUID) -> dict:
    c = db.get(Challenge, challenge_id)
    if c is None or c.status not in (ChallengeStatus.submitted.value, ChallengeStatus.under_ai_review.value):
        return {"skipped": "already reviewed"}
    c.status = ChallengeStatus.under_ai_review.value
    db.commit()
    e = db.get(Evaluation, c.evaluation_id)
    q = db.get(ExaminationQuestion, c.question_id)
    sub = db.get(Submission, c.submission_id)
    rubric = db.get(Rubric, c.original_rubric_id)
    a = db.get(ExtractedAnswer, e.extracted_answer_id) if e.extracted_answer_id else None
    materials = [UUID(m) for m in sub.examination.config.get("material_ids", [])]
    from ai_engine.retrieval.retriever import retrieve_many
    refs = retrieve_many(retriever_for(db, c.institution_id, sub.examination.subject_id, materials, top_k=5), [q.question_text, c.explanation[:500]], limit=5).chunks
    images: list[ImageInput] = []
    if a:
        storage, paths = get_storage(), sub.files[0].page_image_paths
        images = [ImageInput(storage.read(paths[p - 1]), "image/jpeg", f"Page {p}") for p in sorted({r.page_number for r in a.page_references})[:4] if p <= len(paths)]
    disputed = next((x.criterion for x in rubric.criteria if x.id == c.rubric_criterion_id), None)
    state = assess_challenge(get_ai(), ChallengeInput(
        category=c.category, disputed_criterion=disputed, explanation=c.explanation, evidence=[x.content for x in c.evidence],
        question_text=q.question_text, expected_answer=rubric.expected_answer,
        rubric_text="\n".join(f"- {x.criterion} (max {float(x.max_marks):g}): {x.expected_evidence}" for x in rubric.criteria),
        answer_text=a.best_text if a else "", evaluation_summary="\n".join(f"{s.criterion}: {float(s.awarded_marks):g}/{float(s.max_marks):g} - {s.reason}" for s in e.criterion_scores),
        original_marks=float(c.original_marks), max_marks=float(e.max_marks), references=refs, page_images=images))
    rec = state["recommendation"]
    db.add(ChallengeReview(institution_id=c.institution_id, challenge_id=c.id, recommendation=rec.recommendation,
                           suggested_marks=None if rec.suggested_marks is None else D(rec.suggested_marks), reasoning=rec.reasoning,
                           confidence=rec.confidence, escalated=state["escalated"], model=",".join(sorted(set(state["models"]))),
                           detail={"analysis": state["analysis"].model_dump(), "validity": state["validity"].model_dump(),
                                   "rubric_change_suggested": rec.rubric_change_suggested, "sources": [r.model_dump(exclude={"text"}) for r in refs]}))
    c.status = ChallengeStatus.pending_teacher_review.value
    audit(db, "challenge.ai_reviewed", "challenge", c.id, institution_id=c.institution_id, actor_type="ai", after={"recommendation": rec.recommendation, "escalated": state["escalated"]})
    notify_staff(db, c.institution_id, "challenge_ready", "Challenge awaiting your decision", f"Q{q.question_number}: {c.category.replace('_', ' ')}", f"/teacher/challenges/{c.id}")
    db.commit()
    return {"recommendation": rec.recommendation}


def _redistribute(e: Evaluation, target: Decimal, preferred: UUID | None) -> None:
    """Move the question total to `target`, starting with the disputed criterion."""
    delta = target - sum(s.awarded_marks for s in e.criterion_scores)
    rows = sorted(e.criterion_scores, key=lambda s: s.rubric_criterion_id != preferred)
    for s in rows:
        if delta == 0:
            break
        room = s.max_marks - s.awarded_marks if delta > 0 else -s.awarded_marks
        step = min(delta, room) if delta > 0 else max(delta, room)
        s.awarded_marks += step
        delta -= step
    if delta != 0:
        raise bad_request("Revised marks do not fit within the rubric's criteria")


def decide(db: Session, c: Challenge, *, user_id: UUID, decision: str, revised_marks: float | None, reason: str,
           criterion_marks: dict[UUID, float] | None, rubric_note: str | None) -> Challenge:
    if c.status != ChallengeStatus.pending_teacher_review.value:
        raise conflict("This challenge is not awaiting a decision")
    e = db.get(Evaluation, c.evaluation_id)
    original = e.marks_awarded
    if decision == "rejected":
        new = original
    else:
        if criterion_marks:
            for s in e.criterion_scores:
                if s.rubric_criterion_id in criterion_marks:
                    v = D(criterion_marks[s.rubric_criterion_id])
                    if v < 0 or v > s.max_marks:
                        raise bad_request(f"{s.criterion} must be between 0 and {s.max_marks}")
                    s.awarded_marks = v
            new = sum(s.awarded_marks for s in e.criterion_scores)
        else:
            if revised_marks is None:
                raise bad_request("Enter the revised marks")
            new = D(revised_marks)
            if new < 0 or new > e.max_marks:
                raise bad_request(f"Marks must be between 0 and {e.max_marks}")
            _redistribute(e, new, c.rubric_criterion_id)
        if new == original and decision == "accepted":
            raise bad_request("An accepted challenge must change the marks; otherwise reject it")
        e.marks_awarded, e.version = new, e.version + 1
        e.report = {**e.report, "marks_awarded": float(new)}
        record_version(db, e, "challenge", user_id, f"Challenge {decision}: {reason}")
    if rubric_note:
        q = db.get(ExaminationQuestion, c.question_id)
        old = db.get(Rubric, c.original_rubric_id)
        latest = q.rubrics[-1]
        latest.status = "superseded"
        crit = [{"criterion": x.criterion, "category": x.category, "max_marks": x.max_marks,
                 "expected_evidence": x.expected_evidence + (f" Also accept: {rubric_note}" if x.id == c.rubric_criterion_id or c.rubric_criterion_id is None and x.position == 1 else "")}
                for x in old.criteria]
        r = add_rubric(db, q, crit, version=latest.version + 1, status="approved", reason=f"Challenge {c.id}: {rubric_note}")
        r.approved_by, r.approved_at = user_id, datetime.now(UTC)
        db.flush()
        c.revised_rubric_id = r.id
    c.revised_marks, c.status = new, decision
    db.add(ChallengeDecision(institution_id=c.institution_id, challenge_id=c.id, decided_by=user_id, decision=decision, original_marks=original, revised_marks=new, reason=reason))
    sub = db.get(Submission, c.submission_id)
    db.flush()
    refresh_result(db, sub)
    audit(db, "challenge.decided", "challenge", c.id, actor_id=user_id, before={"marks": float(original)}, after={"marks": float(new), "decision": decision, "reason": reason})
    notify(db, c.student_id, "challenge_resolved", "Your challenge was reviewed", f"Decision: {decision.replace('_', ' ')}. Marks: {float(new):g}.", f"/student/challenges/{c.id}", c.institution_id)
    return c
