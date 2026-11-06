from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.submissions import own_sub, start_evaluation
from app.core.db import get_db
from app.core.deps import Principal, get_principal, staff
from app.core.errors import bad_request, conflict, not_found
from app.models import (
    Challenge, Evaluation, EvaluationStatus, EvaluationVersion, ExaminationQuestion, ExtractedAnswer, Result, Role, Rubric, Submission, SubmissionStatus,
)
from app.schemas.inputs import TeacherReviewIn
from app.services.grading import D, record_version, refresh_result
from app.services.platform import audit

router = APIRouter(tags=["evaluations"])


def evaluation_out(db: Session, e: Evaluation, *, for_student: bool = False) -> dict:
    q = db.get(ExaminationQuestion, e.question_id)
    a = db.get(ExtractedAnswer, e.extracted_answer_id) if e.extracted_answer_id else None
    rubric = db.get(Rubric, e.rubric_id)
    r = {k: v for k, v in (e.report or {}).items() if k != "trace" or not for_student}
    out = {"id": str(e.id), "submission_id": str(e.submission_id), "question_id": str(e.question_id), "question_number": q.question_number, "question_text": q.question_text, "topic": q.topic,
           "max_marks": float(e.max_marks), "marks_awarded": float(e.marks_awarded) if e.marks_awarded is not None else None, "version": e.version, "status": e.status,
           "expected_concepts": rubric.expected_concepts, "rubric_version": rubric.version,
           "criteria": [{"criterion_id": str(c.rubric_criterion_id), "criterion": c.criterion, "category": c.category, "max_marks": float(c.max_marks), "awarded_marks": float(c.awarded_marks), "reason": c.reason} for c in e.criterion_scores],
           "answer_text": a.best_text if a else "", "pages": sorted({x.page_number for x in a.page_references}) if a else [],
           "contains_diagram": a.contains_diagram if a else False, "report": r, "is_demo": e.is_demo}
    if not for_student:
        out |= {"confidence": e.confidence, "requires_human_review": e.requires_human_review, "review_reasons": e.review_reasons, "ocr_confidence": a.ocr_confidence if a else None, "model": e.model}
    return out


def own_eval(db: Session, p: Principal, eid) -> Evaluation:
    e = db.get(Evaluation, eid)
    if e is None or e.institution_id != p.institution_id:
        raise not_found("Evaluation")
    return e


def _student_can_see(db: Session, p: Principal, e: Evaluation) -> bool:
    s = db.get(Submission, e.submission_id)
    r = db.scalar(select(Result).where(Result.submission_id == s.id))
    return s.student_id == p.id and r is not None and r.status == "published"


@router.post("/evaluations/{submission_id}/start")
def start(submission_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    return start_evaluation(db, p, own_sub(db, p, submission_id), force=False)


@router.get("/evaluations/{eid}")
def get_evaluation(eid: uuid.UUID, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    e = own_eval(db, p, eid)
    if p.role == Role.student.value:
        if not _student_can_see(db, p, e):
            raise not_found("Evaluation")  # provisional marks are never shown to students
        return evaluation_out(db, e, for_student=True)
    return evaluation_out(db, e)


@router.get("/evaluations/{eid}/report")
def report(eid: uuid.UUID, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return get_evaluation(eid, p, db)


@router.get("/evaluations/{eid}/history")
def history(eid: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    own_eval(db, p, eid)
    rows = db.scalars(select(EvaluationVersion).where(EvaluationVersion.evaluation_id == eid).order_by(EvaluationVersion.version)).all()
    return {"items": [{"version": v.version, "marks_awarded": float(v.marks_awarded) if v.marks_awarded is not None else None, "actor_type": v.actor_type, "reason": v.reason, "model": v.model, "created_at": v.created_at} for v in rows]}


@router.put("/evaluations/{eid}/teacher-review")
def teacher_review(eid: uuid.UUID, body: TeacherReviewIn, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    e = own_eval(db, p, eid)
    if db.scalar(select(Result).where(Result.submission_id == e.submission_id, Result.status == "published")):
        raise conflict("Results are published. Marks can now change only through a challenge.")
    scores = {c.rubric_criterion_id: c for c in e.criterion_scores}
    if not scores:  # could not be evaluated: the teacher marks it by hand against the rubric
        from app.models import CriterionScore
        for c in db.get(Rubric, e.rubric_id).criteria:
            s = CriterionScore(institution_id=e.institution_id, rubric_criterion_id=c.id, criterion=c.criterion, category=c.category, max_marks=c.max_marks, awarded_marks=0, reason="")
            e.criterion_scores.append(s)
            scores[c.id] = s
    before = float(e.marks_awarded) if e.marks_awarded is not None else None
    for row in body.criteria:
        c = scores.get(row.criterion_id)
        if c is None:
            raise bad_request("That criterion is not in this rubric")
        v = D(row.awarded_marks)
        if v > c.max_marks:
            raise bad_request(f"{c.criterion} cannot exceed {c.max_marks}")
        c.awarded_marks, c.reason = v, row.reason
    if {r.criterion_id for r in body.criteria} != set(scores) and e.marks_awarded is None:
        raise bad_request("Mark every criterion")
    e.marks_awarded = sum(c.awarded_marks for c in e.criterion_scores)
    e.version += 1
    e.status, e.requires_human_review, e.review_reasons = EvaluationStatus.teacher_reviewed.value, False, []
    e.report = {**e.report, "marks_awarded": float(e.marks_awarded)}
    record_version(db, e, "teacher", p.id, body.reason)
    audit(db, "evaluation.reviewed", "evaluation", e.id, actor_id=p.id, before={"marks": before}, after={"marks": float(e.marks_awarded), "reason": body.reason})
    db.commit()
    return evaluation_out(db, e)


@router.post("/evaluations/{eid}/approve")
def approve_one(eid: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    e = own_eval(db, p, eid)
    if e.marks_awarded is None:
        raise bad_request("Mark this answer manually before approving")
    if e.requires_human_review:
        raise bad_request("This answer is flagged. Review it before approving.", "needs_review")
    e.status = EvaluationStatus.approved.value
    audit(db, "evaluation.approved", "evaluation", e.id, actor_id=p.id, after={"marks": float(e.marks_awarded)})
    db.commit()
    return {"id": str(e.id), "status": e.status}


@router.post("/evaluations/submission/{submission_id}/approve")
def approve_submission(submission_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    """Teacher sign-off for a whole answer sheet. This is what makes marks final."""
    s = own_sub(db, p, submission_id)
    if s.status not in (SubmissionStatus.evaluated.value, SubmissionStatus.approved.value):
        raise conflict("Evaluation has not finished")
    rows = db.scalars(select(Evaluation).where(Evaluation.submission_id == s.id)).all()
    blocked = [db.get(ExaminationQuestion, e.question_id).question_number for e in rows if e.marks_awarded is None or e.requires_human_review]
    if blocked:
        raise bad_request(f"Review flagged answers first: {', '.join(f'Q{n}' for n in sorted(blocked))}", "needs_review")
    if len(rows) != len(s.examination.questions):
        raise bad_request("Some questions have not been evaluated")
    for e in rows:
        e.status = EvaluationStatus.approved.value
    s.status = SubmissionStatus.approved.value
    r = refresh_result(db, s)
    audit(db, "submission.approved", "submission", s.id, actor_id=p.id, after={"total": float(r.total_marks), "at": datetime.now(UTC).isoformat()})
    db.commit()
    return {"status": s.status, "total_marks": float(r.total_marks), "max_marks": float(r.max_marks)}


@router.get("/results")
def my_results(p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    from app.models import Examination
    rows = db.execute(select(Result, Examination).join(Examination, Result.examination_id == Examination.id).where(Result.student_id == p.id, Result.status == "published").order_by(Result.published_at.desc())).unique().all()
    return {"items": [{"examination_id": str(x.id), "examination": x.title, "subject": x.subject.name, "total_marks": float(r.total_marks), "max_marks": float(r.max_marks), "percentage": r.percentage, "published_at": r.published_at, "is_demo": r.is_demo} for r, x in rows]}


@router.get("/results/{exam_id}")
def result_detail(exam_id: uuid.UUID, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    from app.models import Examination, TopicPerformance
    r = db.scalar(select(Result).where(Result.examination_id == exam_id, Result.student_id == p.id, Result.status == "published"))
    if r is None:
        raise not_found("Result")
    exam = db.get(Examination, exam_id)
    evals = db.scalars(select(Evaluation).where(Evaluation.submission_id == r.submission_id)).all()
    topics = db.scalars(select(TopicPerformance).where(TopicPerformance.result_id == r.id).order_by(TopicPerformance.score.desc())).all()
    challenges = {c.evaluation_id: c for c in db.scalars(select(Challenge).where(Challenge.submission_id == r.submission_id).order_by(Challenge.created_at))}
    questions = sorted((evaluation_out(db, e, for_student=True) | {"challenge": ({"id": str(challenges[e.id].id), "status": challenges[e.id].status} if e.id in challenges else None)} for e in evals), key=lambda x: x["question_number"])
    return {"examination": exam.title, "subject": exam.subject.name, "submission_id": str(r.submission_id), "total_marks": float(r.total_marks), "max_marks": float(r.max_marks), "percentage": r.percentage, "is_demo": r.is_demo,
            "status": r.status, "published_at": r.published_at, "insights": r.insights, "questions": questions,
            "topics": [{"name": t.topic, "score": t.score, "status": t.status, "marks": float(t.marks), "max_marks": float(t.max_marks)} for t in topics]}
