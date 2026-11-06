from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ai_engine.answer_extractor.extractor import extract_submission
from ai_engine.handwriting.preprocess import render_pdf_pages
from app.core.config import get_settings
from app.core.storage import get_storage
from app.models import (
    AnswerPageReference, ExaminationQuestion, ExtractedAnswer, ExtractionJob, JobStatus, Submission, SubmissionStatus,
)
from app.services.platform import audit, enqueue, get_ai, notify_staff


def page_images(db: Session, sub: Submission) -> list[str]:
    """Original pages are rendered once and kept, so evaluators can always see them."""
    f = sub.files[0]
    if f.page_image_paths:
        return f.page_image_paths
    storage = get_storage()
    paths = []
    for i, img in enumerate(render_pdf_pages(storage.read(f.storage_path)), start=1):
        path = f"{sub.institution_id}/submissions/{sub.id}/pages/{i}.jpg"
        storage.write(path, img, "image/jpeg")
        paths.append(path)
    f.page_image_paths = paths
    db.commit()
    return paths


def run_extraction(db: Session, submission_id: UUID) -> dict:
    sub = db.get(Submission, submission_id)
    if sub is None or not sub.is_current:
        return {"skipped": "superseded"}
    if sub.status not in (SubmissionStatus.submitted.value, SubmissionStatus.extracting.value, SubmissionStatus.failed.value):
        return {"skipped": sub.status}
    tracker = db.scalar(select(ExtractionJob).where(ExtractionJob.submission_id == sub.id).order_by(ExtractionJob.created_at.desc()).limit(1))
    sub.status = SubmissionStatus.extracting.value
    paths = page_images(db, sub)
    tracker.status, tracker.pages_total, tracker.pages_done = JobStatus.processing.value, len(paths), 0
    db.commit()
    storage = get_storage()
    images = [storage.read(p) for p in paths]
    questions = db.scalars(select(ExaminationQuestion).where(ExaminationQuestion.examination_id == sub.examination_id)
                           .order_by(ExaminationQuestion.question_number)).all()
    by_number = {q.question_number: q for q in questions}

    def progress(n: int) -> None:
        tracker.pages_done = n
        db.commit()

    output, model = extract_submission(get_ai(), str(sub.id), images, [(q.question_number, q.question_text) for q in questions],
                                       review_threshold=get_settings().ocr_review_threshold, on_page=progress)
    db.execute(delete(ExtractedAnswer).where(ExtractedAnswer.submission_id == sub.id))
    for a in output.answers:
        q = by_number.get(a.question_number)
        row = ExtractedAnswer(institution_id=sub.institution_id, submission_id=sub.id, question_id=q.id if q else None,
                              question_number=a.question_number, recognized_text=a.recognized_text, ocr_confidence=a.ocr_confidence,
                              contains_diagram=a.contains_diagram, contains_equation=a.contains_equation,
                              needs_human_verification=a.needs_human_verification, verification_reasons=a.verification_reasons)
        row.page_references = [AnswerPageReference(institution_id=sub.institution_id, page_number=r.page_number, region=r.region) for r in a.page_references]
        db.add(row)
    tracker.page_failures, tracker.warnings, tracker.model = output.page_failures, output.warnings, model
    tracker.status = JobStatus.requires_review.value if output.page_failures or any(a.needs_human_verification for a in output.answers) else JobStatus.completed.value
    audit(db, "submission.extracted", "submission", sub.id, institution_id=sub.institution_id, actor_type="ai",
          after={"answers": len(output.answers), "page_failures": len(output.page_failures), "model": model})
    if output.page_failures:
        sub.status = SubmissionStatus.failed.value
        notify_staff(db, sub.institution_id, "extraction_failed", "Pages failed to process", f"{len(output.page_failures)} page(s) need reprocessing.",
                     f"/teacher/submissions/{sub.id}")
        db.commit()
        return {"page_failures": len(output.page_failures)}
    sub.status = SubmissionStatus.extracted.value
    db.commit()
    enqueue(db, "evaluate_submission", {"submission_id": str(sub.id)}, f"evaluate:{sub.id}:v{sub.version}", sub.institution_id)
    db.commit()
    return {"answers": len(output.answers)}
