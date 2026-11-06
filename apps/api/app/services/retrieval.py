"""pgvector search. Tenant scope is a required argument and also enforced by RLS."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_engine.retrieval.retriever import AcademicRetriever, SearchFn
from ai_engine.schemas import RetrievedChunk
from app.models import DocumentChunk, MaterialStatus, StudyMaterial
from app.services.platform import get_ai


def vector_search(db: Session, institution_id: UUID, subject_id: UUID, material_ids: list[UUID] | None = None,
                  chapters: list[str] | None = None) -> SearchFn:
    def search(vector: list[float], top_k: int) -> list[RetrievedChunk]:
        distance = DocumentChunk.embedding.cosine_distance(vector).label("distance")
        q = (select(DocumentChunk, StudyMaterial.title, distance).join(StudyMaterial, StudyMaterial.id == DocumentChunk.material_id)
             .where(DocumentChunk.institution_id == institution_id, DocumentChunk.subject_id == subject_id,
                    DocumentChunk.embedding.is_not(None), StudyMaterial.status == MaterialStatus.indexed.value)
             .order_by(distance).limit(top_k))
        if material_ids:
            q = q.where(DocumentChunk.material_id.in_(material_ids))
        if chapters:
            q = q.where(DocumentChunk.chapter.in_(chapters))
        return [RetrievedChunk(material_id=str(c.material_id), material_title=title, chunk_id=str(c.id), page_start=c.page_start,
                               page_end=c.page_end, chapter=c.chapter, score=round(1 - float(d), 4), text=c.text)
                for c, title, d in db.execute(q).all()]
    return search


def retriever_for(db: Session, institution_id: UUID, subject_id: UUID, material_ids: list[UUID] | None = None, top_k: int = 8) -> AcademicRetriever:
    return AcademicRetriever(get_ai(), vector_search(db, institution_id, subject_id, material_ids), top_k=top_k)
