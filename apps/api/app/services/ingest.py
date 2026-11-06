from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ai_engine.ingestion.chunker import chunk_pages
from ai_engine.ingestion.parsers import UnsupportedDocument, parse_document
from app.core.storage import get_storage
from app.models import DocumentChunk, DocumentProcessingJob, JobStatus, MaterialStatus, StudyMaterial
from app.services.platform import audit, get_ai, notify


def _job(db: Session, material: StudyMaterial) -> DocumentProcessingJob:
    return db.scalar(select(DocumentProcessingJob).where(DocumentProcessingJob.material_id == material.id)
                     .order_by(DocumentProcessingJob.created_at.desc()).limit(1))


def index_material(db: Session, material_id: UUID) -> dict:
    m = db.get(StudyMaterial, material_id)
    if m is None:
        return {"skipped": "deleted"}
    if m.status == MaterialStatus.indexed.value:
        return {"skipped": "already indexed"}
    tracker = _job(db, m)
    m.status, m.error = MaterialStatus.processing.value, None
    if tracker:
        tracker.status, tracker.stage = JobStatus.processing.value, "extracting"
    db.commit()
    try:
        parsed = parse_document(get_storage().read(m.storage_path), m.filename)
    except UnsupportedDocument as exc:
        fail_material(db, m, str(exc))
        return {"failed": str(exc)}
    chunks = chunk_pages(parsed.pages)
    if tracker:
        tracker.stage = "embedding"
    db.commit()
    ai = get_ai()
    vectors = ai.embed([c.text for c in chunks], task="document")
    db.execute(delete(DocumentChunk).where(DocumentChunk.material_id == m.id))  # safe re-run
    db.add_all(DocumentChunk(institution_id=m.institution_id, material_id=m.id, subject_id=m.subject_id, chunk_index=c.index,
                             page_start=c.page_start, page_end=c.page_end, chapter=c.chapter, text=c.text, embedding=v,
                             embedding_model=ai.embedding_model) for c, v in zip(chunks, vectors))
    m.status, m.page_count, m.chunk_count, m.doc_metadata = MaterialStatus.indexed.value, parsed.metadata.get("page_count"), len(chunks), parsed.metadata
    if tracker:
        tracker.status, tracker.stage = JobStatus.completed.value, "indexed"
    audit(db, "document.indexed", "study_material", m.id, institution_id=m.institution_id, actor_type="system", after={"chunks": len(chunks)})
    if m.uploaded_by:
        notify(db, m.uploaded_by, "document_indexed", "Document indexed", f"{m.title} is ready: {len(chunks)} sections.", "/teacher/documents", m.institution_id)
    db.commit()
    return {"chunks": len(chunks)}


def fail_material(db: Session, m: StudyMaterial, error: str) -> None:
    m.status, m.error = MaterialStatus.failed.value, error[:1000]
    tracker = _job(db, m)
    if tracker:
        tracker.status, tracker.stage, tracker.error = JobStatus.failed.value, "failed", error[:1000]
    if m.uploaded_by:
        notify(db, m.uploaded_by, "document_failed", "Document processing failed", f"{m.title}: {error[:200]}", "/teacher/documents", m.institution_id)
    db.commit()
