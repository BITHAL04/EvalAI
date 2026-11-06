"""Persistent job worker. Run as a separate process: `python -m app.worker`.

Jobs live in Postgres, so they survive restarts. SKIP LOCKED lets several workers run safely, and
a job whose worker died is reclaimed after WORKER_LOCK_TIMEOUT_SECONDS.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))  # ai_engine at repo root

import logging
import os
import signal
import socket
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ai_engine.providers.base import AIError
from app.core.config import ConfigurationError, get_settings
from app.core.db import system_session
from app.models import (
    BackgroundJob, Challenge, ChallengeStatus, ExamStatus, Examination, ExtractionJob, JobStatus, StudyMaterial, Submission, SubmissionStatus,
)
from app.services import challenges, exams, extraction, grading, ingest
from app.services.platform import audit, notify, notify_staff

log = logging.getLogger("evalai.worker")
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
_stop = False


def _on_final_failure(db: Session, job: BackgroundJob, error: str) -> None:
    """Leave every domain object in a visible, recoverable state."""
    p = job.payload
    if job.job_type == "index_document":
        m = db.get(StudyMaterial, UUID(p["material_id"]))
        if m:
            ingest.fail_material(db, m, error)
    elif job.job_type == "generate_exam":
        e = db.get(Examination, UUID(p["examination_id"]))
        if e:
            e.status, e.generation_error = ExamStatus.draft.value, error[:1000]
            if e.created_by:
                notify(db, e.created_by, "exam_generation_failed", "Paper generation failed", error[:200], f"/teacher/exams/{e.id}", e.institution_id)
    elif job.job_type in ("extract_submission", "evaluate_submission"):
        s = db.get(Submission, UUID(p["submission_id"]))
        if s:
            s.status = SubmissionStatus.failed.value
            t = db.scalar(select(ExtractionJob).where(ExtractionJob.submission_id == s.id).order_by(ExtractionJob.created_at.desc()).limit(1))
            if t and job.job_type == "extract_submission":
                t.status = JobStatus.failed.value
            notify_staff(db, s.institution_id, "processing_failed", "Answer sheet processing failed", error[:200], f"/teacher/submissions/{s.id}")
    elif job.job_type == "assess_challenge":
        c = db.get(Challenge, UUID(p["challenge_id"]))
        if c and c.status in (ChallengeStatus.submitted.value, ChallengeStatus.under_ai_review.value):
            c.status = ChallengeStatus.pending_teacher_review.value  # a teacher can decide without the AI's view
    db.commit()


HANDLERS: dict[str, Callable[[Session, dict], dict]] = {
    "index_document": lambda db, p: ingest.index_material(db, UUID(p["material_id"])),
    "generate_exam": lambda db, p: exams.generate_exam(db, UUID(p["examination_id"])),
    "regenerate_question": lambda db, p: exams.regenerate_question(db, UUID(p["question_id"])),
    "extract_submission": lambda db, p: extraction.run_extraction(db, UUID(p["submission_id"])),
    "evaluate_submission": lambda db, p: grading.evaluate_submission(db, UUID(p["submission_id"]), force=p.get("force", False)),
    "consistency_check": lambda db, p: grading.consistency_check(db, UUID(p["examination_id"])),
    "run_benchmarks": lambda db, p: grading.run_benchmarks(db, UUID(p["examination_id"])),
    "assess_challenge": lambda db, p: challenges.assess(db, UUID(p["challenge_id"])),
}


def claim(db: Session) -> BackgroundJob | None:
    now = datetime.now(UTC)
    stale = now - timedelta(seconds=get_settings().worker_lock_timeout_seconds)
    job = db.scalar(select(BackgroundJob).where(
        or_(BackgroundJob.status == JobStatus.queued.value,
            (BackgroundJob.status == JobStatus.processing.value) & (BackgroundJob.locked_at < stale)),
        BackgroundJob.run_after <= now).order_by(BackgroundJob.run_after).limit(1).with_for_update(skip_locked=True))
    if job is None:
        db.rollback()
        return None
    job.status, job.locked_by, job.locked_at = JobStatus.processing.value, WORKER_ID, now
    job.attempts += 1
    db.commit()
    return job


def run_job(db: Session, job: BackgroundJob) -> None:
    payload, job_id = job.payload, job.id
    log.info("job start id=%s type=%s attempt=%s", job_id, job.job_type, job.attempts)
    try:
        result = HANDLERS[job.job_type](db, payload)
        job = db.get(BackgroundJob, job_id)
        job.status, job.result, job.error, job.locked_by = JobStatus.completed.value, result, None, None
        db.commit()
    except Exception as exc:  # noqa: BLE001 - a job failure must never stop the worker
        db.rollback()
        job = db.get(BackgroundJob, job_id)
        error = str(exc)[:1000] or type(exc).__name__
        permanent = isinstance(exc, ConfigurationError) or (isinstance(exc, AIError) and type(exc) is AIError)
        log.warning("job failed id=%s type=%s: %s", job_id, job.job_type, error, exc_info=not permanent)
        job.error, job.locked_by = error, None
        if permanent or job.attempts >= job.max_attempts:
            job.status = JobStatus.failed.value
            db.commit()
            audit(db, "job.failed", "background_job", job.id, institution_id=job.institution_id, actor_type="system", after={"error": error})
            _on_final_failure(db, job, error)
            db.commit()
        else:
            job.status, job.run_after = JobStatus.queued.value, datetime.now(UTC) + timedelta(seconds=30 * 2 ** job.attempts)
            db.commit()


def run_pending(limit: int = 100) -> int:
    """Drain the queue once (used by tests and the acceptance run)."""
    n = 0
    while n < limit:
        with system_session() as db:
            job = claim(db)
            if job is None:
                return n
            run_job(db, job)
            n += 1
    return n


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    get_settings()

    def stop(*_):
        global _stop
        _stop = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    log.info("worker started as %s", WORKER_ID)
    while not _stop:
        try:
            if run_pending(limit=1) == 0:
                time.sleep(get_settings().worker_poll_seconds)
        except Exception:  # noqa: BLE001 - e.g. database restart
            log.exception("worker loop error")
            time.sleep(5)


if __name__ == "__main__":
    main()
