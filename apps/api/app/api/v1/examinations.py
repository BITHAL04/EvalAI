from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_engine.question_generator.blueprint import BlueprintError, build_blueprint
from app.core.db import get_db
from app.core.deps import Principal, get_principal, staff
from app.core.errors import bad_request, conflict, not_found
from app.core.storage import get_storage
from app.models import (
    BenchmarkAnswer, ConsistencyReport, Enrollment, ExamStatus, Examination, ExaminationQuestion, MaterialStatus, Result, Role, StudyMaterial, Subject, Submission,
)
from app.schemas.inputs import BenchmarkIn, ExamIn, ExamQuestionIn, ExamUpdate, QuestionUpdate
from app.services import exams as svc
from app.services.grading import publish_results
from app.services.platform import audit, enqueue, notify, page, rate_limit, require_ai

router = APIRouter(tags=["examinations"])
EDITABLE = (ExamStatus.draft.value, ExamStatus.review.value)


def exam_out(e: Examination, **extra) -> dict:
    return {"id": str(e.id), "title": e.title, "subject_id": str(e.subject_id), "subject": e.subject.name, "semester": e.semester, "total_marks": float(e.total_marks),
            "duration_minutes": e.duration_minutes, "instructions": e.instructions, "status": e.status, "published_at": e.published_at,
            "submission_deadline": e.submission_deadline, "duplicate_policy": e.duplicate_policy, "is_demo": e.is_demo, "created_at": e.created_at,
            "results_published_at": e.results_published_at, **extra}


def question_out(q: ExaminationQuestion) -> dict:
    r = svc.latest_rubric(q)
    return {"id": str(q.id), "question_number": q.question_number, "question_text": q.question_text, "topic": q.topic, "difficulty": q.difficulty,
            "question_type": q.question_type, "marks": float(q.marks), "expected_answer": q.expected_answer, "expected_concepts": q.expected_concepts,
            "source_references": q.source_references, "origin": q.origin,
            "rubric": {"id": str(r.id), "version": r.version, "status": r.status,
                       "criteria": [{"id": str(c.id), "criterion": c.criterion, "category": c.category, "max_marks": float(c.max_marks), "expected_evidence": c.expected_evidence} for c in r.criteria]} if r else None}


def own_exam(db: Session, p: Principal, exam_id, *, student_visible: bool = False) -> Examination:
    e = db.get(Examination, exam_id)
    if e is None or e.institution_id != p.institution_id:
        raise not_found("Examination")
    if p.role == Role.student.value:
        enrolled = db.scalar(select(Enrollment).where(Enrollment.subject_id == e.subject_id, Enrollment.user_id == p.id))
        if not student_visible or not enrolled or e.status not in (ExamStatus.published.value, ExamStatus.closed.value, ExamStatus.results_published.value):
            raise not_found("Examination")
    return e


def _editable(e: Examination) -> None:
    if e.status not in EDITABLE:
        raise conflict("A published paper cannot be edited")


@router.get("/examinations")
def list_exams(status: str | None = None, subject_id: uuid.UUID | None = None, limit: int = 50, offset: int = 0, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    stmt = select(Examination).where(Examination.institution_id == p.institution_id).order_by(Examination.created_at.desc())
    if p.role == Role.student.value:
        stmt = stmt.join(Enrollment, Enrollment.subject_id == Examination.subject_id).where(
            Enrollment.user_id == p.id, Examination.status.in_([ExamStatus.published.value, ExamStatus.closed.value, ExamStatus.results_published.value]))
    if status:
        stmt = stmt.where(Examination.status == status)
    if subject_id:
        stmt = stmt.where(Examination.subject_id == subject_id)
    rows, total = page(db, stmt, min(limit, 100), offset)
    ids = [e.id for e in rows]
    subs = dict(db.execute(select(Submission.examination_id, func.count()).where(Submission.examination_id.in_(ids), Submission.is_current.is_(True)).group_by(Submission.examination_id)).all())
    mine = {}
    if p.role == Role.student.value:
        mine = {s.examination_id: s for s in db.scalars(select(Submission).where(Submission.student_id == p.id, Submission.is_current.is_(True), Submission.examination_id.in_(ids))).unique()}
    items = []
    for e in rows:
        extra = {"submissions": subs.get(e.id, 0)}
        if p.role == Role.student.value:
            s = mine.get(e.id)
            extra = {"my_submission": {"id": str(s.id), "status": s.status, "version": s.version, "submitted_at": s.submitted_at} if s else None}
        items.append(exam_out(e, **extra))
    return {"items": items, "total": total}


@router.post("/examinations", status_code=201)
def create_exam(body: ExamIn, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    subject = db.get(Subject, body.subject_id)
    if subject is None or subject.institution_id != p.institution_id:
        raise not_found("Subject")
    try:
        build_blueprint(total_marks=body.total_marks, mark_distribution=[r.model_dump() for r in body.mark_distribution], difficulty=body.difficulty,
                        question_types=body.question_types, topics=body.topics)
    except BlueprintError as exc:
        raise bad_request(str(exc)) from exc
    if body.material_ids:
        n = db.scalar(select(func.count()).select_from(StudyMaterial).where(StudyMaterial.id.in_(body.material_ids), StudyMaterial.subject_id == body.subject_id))
        if n != len(set(body.material_ids)):
            raise bad_request("Reference documents must belong to the selected subject")
    e = Examination(institution_id=p.institution_id, subject_id=body.subject_id, course_id=body.course_id, title=body.title, semester=body.semester, total_marks=body.total_marks,
                    duration_minutes=body.duration_minutes, instructions=body.instructions, negative_marking=body.negative_marking, duplicate_policy=body.duplicate_policy,
                    submission_deadline=body.submission_deadline, created_by=p.id,
                    config={"topics": body.topics, "material_ids": [str(m) for m in body.material_ids], "difficulty": body.difficulty,
                            "question_types": body.question_types, "mark_distribution": [r.model_dump() for r in body.mark_distribution], "generation_notes": body.generation_notes})
    db.add(e)
    db.flush()
    audit(db, "exam.created", "examination", e.id, actor_id=p.id, after={"title": e.title})
    db.commit()
    return exam_out(e)


@router.get("/examinations/{exam_id}")
def get_exam(exam_id: uuid.UUID, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    e = own_exam(db, p, exam_id, student_visible=True)
    if p.role == Role.student.value:  # answer keys and rubrics never reach a student's exam view
        return exam_out(e, questions=[{"question_number": q.question_number, "question_text": q.question_text, "marks": float(q.marks), "topic": q.topic} for q in e.questions])
    rep = db.scalar(select(ConsistencyReport).where(ConsistencyReport.examination_id == e.id).order_by(ConsistencyReport.created_at.desc()).limit(1))
    return exam_out(e, config=e.config, generation_error=e.generation_error, questions=[question_out(q) for q in e.questions],
                    computed_total=sum(float(q.marks) for q in e.questions),
                    consistency=({"findings": rep.findings, "summary": rep.summary, "created_at": rep.created_at} if rep else None))


@router.put("/examinations/{exam_id}")
def update_exam(exam_id: uuid.UUID, body: ExamUpdate, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    e = own_exam(db, p, exam_id)
    data = body.model_dump(exclude_unset=True)
    if set(data) - {"submission_deadline"}:
        _editable(e)
    for k, v in data.items():
        setattr(e, k, v)
    audit(db, "exam.updated", "examination", e.id, actor_id=p.id, after={k: str(v) for k, v in data.items()})
    db.commit()
    return exam_out(e)


@router.delete("/examinations/{exam_id}", status_code=204)
def delete_exam(exam_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    e = own_exam(db, p, exam_id)
    _editable(e)
    audit(db, "exam.deleted", "examination", e.id, actor_id=p.id, before={"title": e.title})
    db.delete(e)
    db.commit()


@router.post("/examinations/{exam_id}/generate")
def generate(exam_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    e = own_exam(db, p, exam_id)
    _editable(e)
    require_ai()
    rate_limit(db, f"generate:{p.id}")
    q = select(func.count()).select_from(StudyMaterial).where(StudyMaterial.subject_id == e.subject_id, StudyMaterial.status == MaterialStatus.indexed.value)
    if not db.scalar(q):
        raise bad_request("Upload and index at least one document for this subject first")
    e.status, e.generation_error = ExamStatus.generating.value, None
    job = enqueue(db, "generate_exam", {"examination_id": str(e.id)}, f"generate:{e.id}:{uuid.uuid4()}", e.institution_id)
    db.commit()
    return {"job_id": str(job.id), "status": e.status}


def _renumber(e: Examination) -> None:
    for i, q in enumerate(sorted(e.questions, key=lambda x: x.question_number), start=1):
        q.question_number = i


@router.post("/examinations/{exam_id}/questions", status_code=201)
def add_question(exam_id: uuid.UUID, body: ExamQuestionIn, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    e = own_exam(db, p, exam_id)
    _editable(e)
    if abs(sum(r.max_marks for r in body.rubric) - body.marks) > 1e-6:
        raise bad_request("Rubric marks must add up to the question's marks")
    q = ExaminationQuestion(institution_id=e.institution_id, examination_id=e.id, question_number=len(e.questions) + 1, origin="manual",
                            **body.model_dump(exclude={"rubric"}))
    db.add(q)
    db.flush()
    svc.add_rubric(db, q, [r.model_dump() for r in body.rubric])
    if e.status == ExamStatus.draft.value:
        e.status = ExamStatus.review.value
    audit(db, "question.added", "examination_question", q.id, actor_id=p.id)
    db.commit()
    return question_out(q)


def own_question(db: Session, p: Principal, qid) -> tuple[ExaminationQuestion, Examination]:
    q = db.get(ExaminationQuestion, qid)
    if q is None or q.institution_id != p.institution_id:
        raise not_found("Question")
    return q, db.get(Examination, q.examination_id)


@router.put("/examination-questions/{question_id}")
def edit_question(question_id: uuid.UUID, body: QuestionUpdate, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    q, e = own_question(db, p, question_id)
    _editable(e)
    before = question_out(q)
    data = body.model_dump(exclude_unset=True, exclude={"rubric"})
    for k, v in data.items():
        setattr(q, k, v)
    if body.rubric is not None:
        marks = float(body.marks if body.marks is not None else q.marks)
        if abs(sum(r.max_marks for r in body.rubric) - marks) > 1e-6:
            raise bad_request("Rubric marks must add up to the question's marks")
        for r in list(q.rubrics):
            q.rubrics.remove(r)
            db.delete(r)
        db.flush()
        svc.add_rubric(db, q, [r.model_dump() for r in body.rubric], reason="Edited by teacher")
    elif body.marks is not None:
        r = svc.latest_rubric(q)
        if r and abs(sum(float(c.max_marks) for c in r.criteria) - body.marks) > 1e-6:
            raise bad_request("Marks changed: update the rubric so it adds up to the new total")
    q.understanding = None
    audit(db, "question.edited", "examination_question", q.id, actor_id=p.id, before={"text": before["question_text"], "marks": before["marks"]}, after={k: str(v) for k, v in data.items()})
    db.commit()
    db.refresh(q)
    return question_out(q)


@router.delete("/examination-questions/{question_id}", status_code=204)
def delete_exam_question(question_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    q, e = own_question(db, p, question_id)
    _editable(e)
    e.questions.remove(q)
    db.flush()
    _renumber(e)
    audit(db, "question.deleted", "examination_question", question_id, actor_id=p.id)
    db.commit()


@router.post("/examination-questions/{question_id}/regenerate")
def regenerate(question_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    q, e = own_question(db, p, question_id)
    _editable(e)
    require_ai()
    rate_limit(db, f"generate:{p.id}")
    job = enqueue(db, "regenerate_question", {"question_id": str(q.id)}, f"regen:{q.id}:{uuid.uuid4()}", e.institution_id)
    db.commit()
    return {"job_id": str(job.id)}


@router.post("/examinations/{exam_id}/recalculate")
def recalculate(exam_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    e = own_exam(db, p, exam_id)
    _editable(e)
    e.total_marks = sum(q.marks for q in e.questions)
    audit(db, "exam.recalculated", "examination", e.id, actor_id=p.id, after={"total": float(e.total_marks)})
    db.commit()
    return exam_out(e)


@router.post("/examinations/{exam_id}/generate-paper")
def generate_paper(exam_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    e = own_exam(db, p, exam_id)
    if not e.questions:
        raise bad_request("Add questions first")
    path = svc.render_exam_pdf(db, e)
    db.commit()
    return {"download_url": get_storage().signed_download(path)}


@router.post("/examinations/{exam_id}/publish")
def publish(exam_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    """The explicit teacher confirmation. Nothing else makes a paper visible to students."""
    e = own_exam(db, p, exam_id)
    if e.status != ExamStatus.review.value:
        raise conflict("Only a paper in review can be published")
    if not e.questions:
        raise bad_request("Add questions first")
    total = sum(float(q.marks) for q in e.questions)
    if abs(total - float(e.total_marks)) > 1e-6:
        raise bad_request(f"Questions total {total:g} but the paper is set to {float(e.total_marks):g}. Recalculate or adjust marks.")
    for q in e.questions:
        r = svc.latest_rubric(q)
        if r is None or abs(sum(float(c.max_marks) for c in r.criteria) - float(q.marks)) > 1e-6:
            raise bad_request(f"Rubric for Q{q.question_number} does not add up to its marks")
    svc.publish_exam(db, e, p.id)
    audit(db, "exam.published", "examination", e.id, actor_id=p.id, after={"total": total, "questions": len(e.questions)})
    for uid in db.scalars(select(Enrollment.user_id).where(Enrollment.subject_id == e.subject_id)):
        notify(db, uid, "exam_published", "New examination", e.title, f"/student/exams/{e.id}", e.institution_id)
    db.commit()
    return exam_out(e)


@router.post("/examinations/{exam_id}/close")
def close(exam_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    e = own_exam(db, p, exam_id)
    if e.status != ExamStatus.published.value:
        raise conflict("Only a published exam can be closed")
    e.status = ExamStatus.closed.value
    audit(db, "exam.closed", "examination", e.id, actor_id=p.id)
    db.commit()
    return exam_out(e)


@router.get("/examinations/{exam_id}/paper")
def paper(exam_id: uuid.UUID, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    e = own_exam(db, p, exam_id, student_visible=True)
    if not e.paper_storage_path:
        raise not_found("Paper")
    return {"download_url": get_storage().signed_download(e.paper_storage_path)}


@router.post("/examinations/{exam_id}/publish-results")
def publish_exam_results(exam_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    e = own_exam(db, p, exam_id)
    if e.status not in (ExamStatus.published.value, ExamStatus.closed.value, ExamStatus.results_published.value):
        raise conflict("Results can only be published for a published exam")
    n = publish_results(db, e, p.id)
    if n == 0:
        raise bad_request("No approved results to publish. Approve submissions first.")
    e.status, e.results_published_at = ExamStatus.results_published.value, datetime.now(UTC)
    audit(db, "results.published", "examination", e.id, actor_id=p.id, after={"results": n})
    db.commit()
    return {"published": n}


@router.get("/examinations/{exam_id}/submissions")
def exam_submissions(exam_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    from app.models import Evaluation, User
    e = own_exam(db, p, exam_id)
    subs = db.scalars(select(Submission).where(Submission.examination_id == e.id, Submission.is_current.is_(True)).order_by(Submission.submitted_at.desc())).unique().all()
    out = []
    for s in subs:
        u = db.get(User, s.student_id)
        total, flagged, n = db.execute(select(func.sum(Evaluation.marks_awarded), func.count().filter(Evaluation.requires_human_review), func.count()).where(Evaluation.submission_id == s.id)).one()
        res = db.scalar(select(Result).where(Result.submission_id == s.id))
        out.append({"id": str(s.id), "student": u.profile.full_name or u.email, "roll_number": u.profile.roll_number, "status": s.status, "version": s.version, "submitted_at": s.submitted_at,
                    "provisional_marks": float(total) if total is not None else None, "flagged": flagged, "evaluated": n, "result_status": res.status if res else None})
    return {"items": out, "max_marks": float(e.total_marks)}


@router.get("/examination-questions/{question_id}/benchmarks")
def benchmarks(question_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    own_question(db, p, question_id)
    rows = db.scalars(select(BenchmarkAnswer).where(BenchmarkAnswer.question_id == question_id)).all()
    return {"items": [{"id": str(b.id), "tier": b.tier, "answer_text": b.answer_text, "expected_marks": float(b.expected_marks),
                       "last_ai_marks": float(b.last_ai_marks) if b.last_ai_marks is not None else None} for b in rows]}


@router.post("/examination-questions/{question_id}/benchmarks", status_code=201)
def add_benchmark(question_id: uuid.UUID, body: BenchmarkIn, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    q, _ = own_question(db, p, question_id)
    if body.expected_marks > float(q.marks):
        raise bad_request("Expected marks exceed the question's marks")
    b = db.scalar(select(BenchmarkAnswer).where(BenchmarkAnswer.question_id == q.id, BenchmarkAnswer.tier == body.tier))
    if b:
        b.answer_text, b.expected_marks, b.last_ai_marks = body.answer_text, body.expected_marks, None
    else:
        b = BenchmarkAnswer(institution_id=p.institution_id, question_id=q.id, created_by=p.id, **body.model_dump())
        db.add(b)
    db.commit()
    return {"id": str(b.id), "tier": b.tier}


@router.post("/examinations/{exam_id}/calibrate")
def calibrate(exam_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    e = own_exam(db, p, exam_id)
    require_ai()
    rate_limit(db, f"generate:{p.id}")
    if e.status in EDITABLE:
        raise conflict("Publish the paper first: calibration uses approved rubrics")
    job = enqueue(db, "run_benchmarks", {"examination_id": str(e.id)}, f"bench:{e.id}:{uuid.uuid4()}", e.institution_id)
    db.commit()
    return {"job_id": str(job.id)}


@router.get("/jobs/{job_id}", tags=["jobs"])
def job_status(job_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    from app.models import BackgroundJob
    j = db.get(BackgroundJob, job_id)
    if j is None or j.institution_id != p.institution_id:
        raise not_found("Job")
    return {"id": str(j.id), "type": j.job_type, "status": j.status, "attempts": j.attempts, "error": j.error, "result": j.result}



