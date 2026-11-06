from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_engine.handwriting.preprocess import page_count
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import Principal, get_principal, staff, student_only
from app.core.errors import DomainError, bad_request, conflict, not_found
from app.core.storage import StorageError, get_storage
from app.models import (
    Enrollment, Evaluation, ExamStatus, Examination, ExtractedAnswer, ExtractionJob, Result, Role, Submission, SubmissionFile, SubmissionStatus,
)
from app.schemas.inputs import AnswerCorrectionIn, SubmissionIn
from app.services.extraction import page_images
from app.services.platform import audit, enqueue, notify_staff, rate_limit, require_ai

router = APIRouter(tags=["submissions"])
LOCKED = (SubmissionStatus.approved.value,)


def sub_out(s: Submission) -> dict:
    f = s.files[0] if s.files else None
    return {"id": str(s.id), "examination_id": str(s.examination_id), "examination": s.examination.title, "version": s.version, "status": s.status, "is_current": s.is_current,
            "submitted_at": s.submitted_at, "filename": f.filename if f else None, "page_count": f.page_count if f else None}


def own_sub(db: Session, p: Principal, sid) -> Submission:
    s = db.get(Submission, sid)
    if s is None or s.institution_id != p.institution_id or (p.role == Role.student.value and s.student_id != p.id):
        raise not_found("Submission")
    return s


@router.post("/submissions", status_code=201)
def create_submission(body: SubmissionIn, p: Principal = Depends(student_only), db: Session = Depends(get_db)):
    cfg = get_settings()
    e = db.get(Examination, body.examination_id)
    enrolled = e and db.scalar(select(Enrollment).where(Enrollment.subject_id == e.subject_id, Enrollment.user_id == p.id))
    if e is None or e.institution_id != p.institution_id or not enrolled:
        raise not_found("Examination")
    if e.status != ExamStatus.published.value:
        raise conflict("This examination is not accepting submissions")
    if e.submission_deadline and datetime.now(UTC) > e.submission_deadline:
        raise conflict("The submission deadline has passed", "deadline_passed")
    if not body.filename.lower().endswith(".pdf"):
        raise bad_request("Answer sheets must be a PDF", "unsupported_file")
    if body.size_bytes > cfg.max_upload_size_mb * 1024 * 1024:
        raise DomainError(413, "file_too_large", f"Files can be at most {cfg.max_upload_size_mb} MB")
    cur = db.scalar(select(Submission).where(Submission.examination_id == e.id, Submission.student_id == p.id, Submission.is_current.is_(True)))
    version = 1
    if cur:
        draft = cur.status in (SubmissionStatus.awaiting_upload.value, SubmissionStatus.uploaded.value)
        if not draft and e.duplicate_policy == "reject":
            raise conflict("You have already submitted, and this examination does not allow resubmission", "duplicate_submission")
        if db.scalar(select(func.count()).select_from(Result).where(Result.submission_id == cur.id)):
            raise conflict("This submission has already been graded")
        cur.is_current = False
        cur.status = SubmissionStatus.superseded.value
        version = cur.version + 1
        db.flush()
    s = Submission(institution_id=p.institution_id, examination_id=e.id, student_id=p.id, version=version)
    db.add(s)
    db.flush()
    path = f"{p.institution_id}/submissions/{s.id}/answer-sheet.pdf"
    db.add(SubmissionFile(institution_id=p.institution_id, submission_id=s.id, storage_path=path, filename=body.filename[:300]))
    up = get_storage().signed_upload(path, "application/pdf")
    audit(db, "submission.created", "submission", s.id, actor_id=p.id, after={"version": version})
    db.commit()
    return {**sub_out(s), "upload_url": up.url, "method": up.method, "headers": up.headers}


@router.post("/submissions/{sid}/upload")
def confirm_upload(sid: uuid.UUID, p: Principal = Depends(student_only), db: Session = Depends(get_db)):
    """Check what actually arrived, then render preview pages."""
    cfg = get_settings()
    s = own_sub(db, p, sid)
    if s.status not in (SubmissionStatus.awaiting_upload.value, SubmissionStatus.uploaded.value):
        raise conflict("Already submitted")
    f = s.files[0]
    storage = get_storage()
    try:
        data = storage.read(f.storage_path)
    except StorageError as exc:
        raise bad_request("The file did not finish uploading. Please try again.", "upload_missing") from exc
    if data[:5] != b"%PDF-":
        storage.delete(f.storage_path)
        raise bad_request("That file is not a valid PDF", "unsupported_file")
    if len(data) > cfg.max_upload_size_mb * 1024 * 1024:
        storage.delete(f.storage_path)
        raise DomainError(413, "file_too_large", f"Files can be at most {cfg.max_upload_size_mb} MB")
    try:
        pages = page_count(data)
    except Exception as exc:
        raise bad_request("That PDF could not be opened", "unsupported_file") from exc
    if pages == 0 or pages > cfg.max_answer_sheet_pages:
        raise bad_request(f"Answer sheets must have 1 to {cfg.max_answer_sheet_pages} pages", "too_many_pages")
    f.size_bytes, f.sha256, f.page_count, f.uploaded_at, f.page_image_paths = len(data), hashlib.sha256(data).hexdigest(), pages, datetime.now(UTC), []
    s.status = SubmissionStatus.uploaded.value
    db.commit()
    page_images(db, s)
    return sub_out(s)


@router.get("/submissions/{sid}/pages")
def pages(sid: uuid.UUID, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    s = own_sub(db, p, sid)
    storage = get_storage()
    return {"items": [{"page_number": i, "url": storage.signed_download(path)} for i, path in enumerate(s.files[0].page_image_paths, start=1)]}


@router.get("/submissions/{sid}/file")
def file_url(sid: uuid.UUID, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return {"download_url": get_storage().signed_download(own_sub(db, p, sid).files[0].storage_path)}


@router.post("/submissions/{sid}/process")
def process(sid: uuid.UUID, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    """Student: final confirmation of submission. Teacher: reprocess after a failure."""
    s = own_sub(db, p, sid)
    if p.role == Role.student.value:
        if s.status != SubmissionStatus.uploaded.value:
            raise conflict("Upload your answer sheet first" if s.status == SubmissionStatus.awaiting_upload.value else "Already submitted")
        if s.examination.status != ExamStatus.published.value:
            raise conflict("This examination is not accepting submissions")
        s.submitted_at = datetime.now(UTC)
        attempt = 1
    else:
        if s.status != SubmissionStatus.failed.value:
            raise conflict("Only a failed submission can be reprocessed")
        attempt = 1 + (db.scalar(select(func.count()).select_from(ExtractionJob).where(ExtractionJob.submission_id == s.id)) or 0)
    s.status = SubmissionStatus.submitted.value
    job = enqueue(db, "extract_submission", {"submission_id": str(s.id)}, f"extract:{s.id}:{attempt}", s.institution_id)
    db.add(ExtractionJob(institution_id=s.institution_id, submission_id=s.id, background_job_id=job.id))
    audit(db, "submission.submitted" if attempt == 1 else "submission.reprocess", "submission", s.id, actor_id=p.id)
    if attempt == 1:
        notify_staff(db, s.institution_id, "submission_received", "Answer sheet submitted", s.examination.title, f"/teacher/submissions/{s.id}")
    db.commit()
    return sub_out(s)


@router.get("/submissions/{sid}/status")
def status(sid: uuid.UUID, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    s = own_sub(db, p, sid)
    t = db.scalar(select(ExtractionJob).where(ExtractionJob.submission_id == s.id).order_by(ExtractionJob.created_at.desc()).limit(1))
    evaluated = db.scalar(select(func.count()).select_from(Evaluation).where(Evaluation.submission_id == s.id))
    return {"status": s.status, "extraction": {"status": t.status, "pages_total": t.pages_total, "pages_done": t.pages_done} if t else None,
            "questions_total": len(s.examination.questions), "questions_evaluated": evaluated}


@router.get("/submissions")
def my_submissions(p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    stmt = select(Submission).where(Submission.institution_id == p.institution_id, Submission.is_current.is_(True), Submission.submitted_at.is_not(None)).order_by(Submission.submitted_at.desc()).limit(100)
    if p.role == Role.student.value:
        stmt = stmt.where(Submission.student_id == p.id)
    return {"items": [sub_out(s) for s in db.scalars(stmt).unique()]}


@router.get("/submissions/{sid}")
def detail(sid: uuid.UUID, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    from app.models import User
    s = own_sub(db, p, sid)
    if p.role == Role.student.value:
        return sub_out(s)
    t = db.scalar(select(ExtractionJob).where(ExtractionJob.submission_id == s.id).order_by(ExtractionJob.created_at.desc()).limit(1))
    answers = db.scalars(select(ExtractedAnswer).where(ExtractedAnswer.submission_id == s.id).order_by(ExtractedAnswer.question_number)).all()
    evals = {e.question_id: e for e in db.scalars(select(Evaluation).where(Evaluation.submission_id == s.id))}
    u = db.get(User, s.student_id)
    from app.api.v1.evaluations import evaluation_out
    return {**sub_out(s), "student": u.profile.full_name or u.email,
            "extraction": {"status": t.status, "warnings": t.warnings, "page_failures": t.page_failures, "pages_total": t.pages_total, "pages_done": t.pages_done} if t else None,
            "answers": [answer_out(a) for a in answers],
            "evaluations": sorted((evaluation_out(db, e) for e in evals.values()), key=lambda x: x["question_number"]),
            "result": _result(db, s)}


def _result(db: Session, s: Submission) -> dict | None:
    r = db.scalar(select(Result).where(Result.submission_id == s.id))
    return {"status": r.status, "total_marks": float(r.total_marks), "max_marks": float(r.max_marks), "percentage": r.percentage} if r else None


def answer_out(a: ExtractedAnswer) -> dict:
    return {"id": str(a.id), "question_number": a.question_number, "recognized_text": a.recognized_text, "corrected_text": a.corrected_text, "ocr_confidence": a.ocr_confidence,
            "contains_diagram": a.contains_diagram, "contains_equation": a.contains_equation, "needs_human_verification": a.needs_human_verification,
            "verification_reasons": a.verification_reasons, "pages": sorted({r.page_number for r in a.page_references})}


@router.put("/extracted-answers/{aid}")
def correct_answer(aid: uuid.UUID, body: AnswerCorrectionIn, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    from app.models import ExaminationQuestion
    a = db.get(ExtractedAnswer, aid)
    if a is None or a.institution_id != p.institution_id:
        raise not_found("Answer")
    sub = db.get(Submission, a.submission_id)
    if sub.status in LOCKED:
        raise conflict("This submission has been approved")
    if body.question_number is not None and body.question_number != a.question_number:
        q = db.scalar(select(ExaminationQuestion).where(ExaminationQuestion.examination_id == sub.examination_id, ExaminationQuestion.question_number == body.question_number))
        if q is None:
            raise bad_request("That question is not on this paper")
        if db.scalar(select(ExtractedAnswer).where(ExtractedAnswer.submission_id == sub.id, ExtractedAnswer.question_number == body.question_number)):
            raise conflict("That question already has an answer; correct its text instead")
        a.question_number, a.question_id = body.question_number, q.id
    before = a.best_text
    a.corrected_text, a.corrected_by, a.needs_human_verification, a.verification_reasons = body.corrected_text, p.id, False, []
    audit(db, "answer.corrected", "extracted_answer", a.id, actor_id=p.id, before={"text": before[:2000]}, after={"text": body.corrected_text[:2000]})
    db.commit()
    return answer_out(a)


@router.post("/submissions/{sid}/reevaluate")
def reevaluate(sid: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    s = own_sub(db, p, sid)
    return start_evaluation(db, p, s, force=True)


def start_evaluation(db: Session, p: Principal, s: Submission, *, force: bool) -> dict:
    if s.status not in (SubmissionStatus.extracted.value, SubmissionStatus.evaluated.value, SubmissionStatus.failed.value):
        raise conflict(f"Submission is {s.status}")
    require_ai()
    rate_limit(db, f"evaluate:{p.id}", 30)
    job = enqueue(db, "evaluate_submission", {"submission_id": str(s.id), "force": force}, f"evaluate:{s.id}:{uuid.uuid4()}", s.institution_id)
    audit(db, "evaluation.started", "submission", s.id, actor_id=p.id)
    db.commit()
    return {"job_id": str(job.id)}



