"""All figures are computed from stored marks at read time. Students only ever see their own."""
from __future__ import annotations

import statistics
import uuid
from collections import Counter, defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.examinations import own_exam
from app.core.db import get_db
from app.core.deps import Principal, get_principal, staff
from app.core.errors import forbidden, not_found
from app.models import (
    Challenge, ChallengeStatus, Enrollment, Evaluation, ExamStatus, Examination, ExaminationQuestion, InstitutionMembership, JobStatus, BackgroundJob,
    Result, Role, RoleRow, StudentPerformanceSnapshot, Subject, Submission, TopicPerformance,
)

router = APIRouter(tags=["analytics"])


def histogram(values: list[float], bins: int = 10) -> list[dict]:
    out = [{"range": f"{i * 10}-{(i + 1) * 10}", "count": 0} for i in range(bins)]
    for v in values:
        out[min(int(v // 10), bins - 1)]["count"] += 1
    return out


@router.get("/analytics/student")
def student(p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    if p.role != Role.student.value:
        raise forbidden()
    rows = db.execute(select(StudentPerformanceSnapshot, Examination, Subject).join(Examination, StudentPerformanceSnapshot.examination_id == Examination.id)
                      .join(Subject, StudentPerformanceSnapshot.subject_id == Subject.id).where(StudentPerformanceSnapshot.student_id == p.id)
                      .order_by(StudentPerformanceSnapshot.taken_at)).unique().all()
    pct = [s.percentage for s, *_ in rows]
    by_subject: dict[str, list[float]] = defaultdict(list)
    for s, _, sub in rows:
        by_subject[sub.name].append(s.percentage)
    class_avg = {}
    for s, e, _ in rows:
        class_avg[e.id] = db.scalar(select(func.avg(Result.percentage)).where(Result.examination_id == e.id, Result.status == "published"))
    return {"exams_taken": len(rows), "average_percentage": round(statistics.mean(pct), 1) if pct else None,
            "trend": [{"examination": e.title, "percentage": s.percentage, "class_average": round(class_avg[e.id] or 0, 1), "date": s.taken_at} for s, e, _ in rows],
            "subjects": [{"subject": k, "percentage": round(statistics.mean(v), 1)} for k, v in by_subject.items()],
            "pending_challenges": db.scalar(select(func.count()).select_from(Challenge).where(Challenge.student_id == p.id, Challenge.status.in_(
                [ChallengeStatus.submitted.value, ChallengeStatus.under_ai_review.value, ChallengeStatus.pending_teacher_review.value])))}


@router.get("/analytics/student/topics")
def student_topics(p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    if p.role != Role.student.value:
        raise forbidden()
    rows = db.execute(select(TopicPerformance.topic, func.sum(TopicPerformance.marks), func.sum(TopicPerformance.max_marks))
                      .join(Result, TopicPerformance.result_id == Result.id)
                      .where(TopicPerformance.student_id == p.id, Result.status == "published").group_by(TopicPerformance.topic)).all()
    from ai_engine.analytics.insights import topic_status
    topics = sorted(({"name": t, "score": round(float(m) / float(x) * 100, 1)} for t, m, x in rows), key=lambda r: -r["score"])
    return {"topics": [{**t, "status": topic_status(t["score"])} for t in topics]}


def exam_analytics(db: Session, e: Examination) -> dict:
    enrolled = db.scalar(select(func.count()).select_from(Enrollment).where(Enrollment.subject_id == e.subject_id))
    subs = db.scalars(select(Submission).where(Submission.examination_id == e.id, Submission.is_current.is_(True), Submission.submitted_at.is_not(None))).unique().all()
    results = db.scalars(select(Result).where(Result.examination_id == e.id)).all()
    pct = [r.percentage for r in results]
    questions = db.scalars(select(ExaminationQuestion).where(ExaminationQuestion.examination_id == e.id).order_by(ExaminationQuestion.question_number)).all()
    sub_ids = [s.id for s in subs]
    evals = db.scalars(select(Evaluation).where(Evaluation.submission_id.in_(sub_ids))).all() if sub_ids else []
    missed, wrong = Counter(), Counter()
    per_q: dict = defaultdict(list)
    for ev in evals:
        if ev.marks_awarded is not None:
            per_q[ev.question_id].append(float(ev.marks_awarded) / float(ev.max_marks) * 100)
        missed.update(ev.report.get("missing_points", []))
        wrong.update(s.get("explanation", "")[:120] for s in ev.report.get("incorrect_statements", []))
    topic_rows = db.execute(select(TopicPerformance.topic, func.sum(TopicPerformance.marks), func.sum(TopicPerformance.max_marks)).where(TopicPerformance.examination_id == e.id).group_by(TopicPerformance.topic)).all()
    challenges = db.scalars(select(Challenge).where(Challenge.examination_id == e.id)).all()
    changed = [c for c in challenges if c.revised_marks is not None and c.revised_marks != c.original_marks]
    return {"examination": e.title, "status": e.status, "is_demo": e.is_demo, "students": enrolled, "submissions": len(subs), "evaluated_submissions": sum(1 for s in subs if s.status in ("evaluated", "approved")),
            "approved": len(results), "class_average": round(statistics.mean(pct), 1) if pct else None, "median": round(statistics.median(pct), 1) if pct else None,
            "highest": max(pct) if pct else None, "lowest": min(pct) if pct else None, "score_distribution": histogram(pct),
            "questions": [{"question_number": q.question_number, "label": f"Q{q.question_number}", "topic": q.topic, "stated_difficulty": q.difficulty,
                           "average": round(statistics.mean(per_q[q.id]), 1) if per_q[q.id] else None} for q in questions],
            "topics": sorted(({"name": t, "score": round(float(m) / float(x) * 100, 1)} for t, m, x in topic_rows), key=lambda r: r["score"]),
            "commonly_missed": [{"concept": k, "students": v} for k, v in missed.most_common(8)], "misconceptions": [{"issue": k, "students": v} for k, v in wrong.most_common(6) if k],
            "reevaluation": {"challenges": len(challenges), "marks_changed": len(changed), "open": sum(1 for c in challenges if c.status in ("submitted", "under_ai_review", "pending_teacher_review"))}}


@router.get("/analytics/examination/{exam_id}")
def examination(exam_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    return exam_analytics(db, own_exam(db, p, exam_id))


@router.get("/analytics/class/{subject_id}")
def class_view(subject_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    s = db.get(Subject, subject_id)
    if s is None or s.institution_id != p.institution_id:
        raise not_found("Subject")
    exams = db.scalars(select(Examination).where(Examination.subject_id == s.id, Examination.status == ExamStatus.results_published.value).order_by(Examination.published_at)).unique().all()
    rows = []
    for e in exams:
        avg = db.scalar(select(func.avg(Result.percentage)).where(Result.examination_id == e.id, Result.status == "published"))
        rows.append({"examination": e.title, "average": round(avg or 0, 1), "is_demo": e.is_demo})
    return {"subject": s.name, "examinations": rows}


@router.get("/analytics/teacher/overview")
def teacher_overview(p: Principal = Depends(staff), db: Session = Depends(get_db)):
    i = p.institution_id
    count = lambda stmt: db.scalar(select(func.count()).select_from(stmt.subquery())) or 0  # noqa: E731
    students = count(select(InstitutionMembership.id).join(RoleRow).where(InstitutionMembership.institution_id == i, RoleRow.name == "student", InstitutionMembership.is_active.is_(True)))
    active = count(select(Examination.id).where(Examination.institution_id == i, Examination.status == ExamStatus.published.value))
    pending = count(select(Submission.id).where(Submission.institution_id == i, Submission.is_current.is_(True), Submission.status.in_(["submitted", "extracting", "extracted", "evaluating"])))
    review = count(select(Submission.id).where(Submission.institution_id == i, Submission.is_current.is_(True), Submission.status == "evaluated"))
    done = count(select(Submission.id).where(Submission.institution_id == i, Submission.is_current.is_(True), Submission.status == "approved"))
    open_c = count(select(Challenge.id).where(Challenge.institution_id == i, Challenge.status == ChallengeStatus.pending_teacher_review.value))
    return {"total_students": students, "active_examinations": active, "pending_submissions": pending, "awaiting_review": review, "evaluations_completed": done, "open_challenges": open_c}


@router.get("/analytics/jobs")
def jobs(p: Principal = Depends(staff), db: Session = Depends(get_db)):
    rows = db.execute(select(BackgroundJob.status, func.count()).where(BackgroundJob.institution_id == p.institution_id).group_by(BackgroundJob.status)).all()
    d = dict(rows)
    recent = db.scalars(select(BackgroundJob).where(BackgroundJob.institution_id == p.institution_id).order_by(BackgroundJob.created_at.desc()).limit(15)).all()
    return {"counts": {s.value: d.get(s.value, 0) for s in JobStatus},
            "recent": [{"id": str(j.id), "type": j.job_type, "status": j.status, "attempts": j.attempts, "error": j.error, "created_at": j.created_at} for j in recent]}
