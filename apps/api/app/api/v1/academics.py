"""Courses, subjects, enrolment, documents and the question bank."""
from __future__ import annotations

import hashlib
import re
import time
import uuid

import jwt
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_engine.ingestion.parsers import UnsupportedDocument, detect_kind
from ai_engine.question_generator.blueprint import build_blueprint
from ai_engine.workflows.paper_generation import build_paper_graph
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import Principal, get_principal, staff
from app.core.errors import DomainError, bad_request, conflict, forbidden, not_found
from app.core.storage import StorageError, get_storage
from app.models import (
    Course, DocumentProcessingJob, Enrollment, Examination, MaterialStatus, QuestionBankItem, Role, StudyMaterial, Subject,
)
from app.schemas.inputs import BankQuestionIn, CourseIn, DocumentIn, EnrollIn, GenerateQuestionsIn, SubjectIn, UploadUrlIn
from app.services.platform import audit, enqueue, get_ai, page, rate_limit, require_ai
from app.services.retrieval import retriever_for

router = APIRouter()
ALLOWED_EXT = (".pdf", ".txt", ".docx")


def safe_name(name: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", name.rsplit("/", 1)[-1])[:120] or "file"


def own_subject(db: Session, p: Principal, subject_id) -> Subject:
    s = db.get(Subject, subject_id)
    if s is None or s.institution_id != p.institution_id:
        raise not_found("Subject")
    return s


def subject_out(s: Subject, **extra) -> dict:
    return {"id": str(s.id), "name": s.name, "code": s.code, "semester": s.semester, "description": s.description,
            "course_id": str(s.course_id) if s.course_id else None, **extra}


# ------------------------------------------------------- courses & subjects
@router.get("/courses", tags=["subjects"])
def courses(p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    rows = db.scalars(select(Course).where(Course.institution_id == p.institution_id).order_by(Course.name)).all()
    return {"items": [{"id": str(c.id), "name": c.name, "code": c.code, "description": c.description} for c in rows]}


@router.post("/courses", status_code=201, tags=["subjects"])
def create_course(body: CourseIn, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    c = Course(institution_id=p.institution_id, **body.model_dump())
    db.add(c)
    audit(db, "course.created", "course", None, actor_id=p.id, after={"code": body.code})
    db.commit()
    return {"id": str(c.id), **body.model_dump()}


@router.get("/subjects", tags=["subjects"])
def subjects(q: str | None = None, limit: int = 50, offset: int = 0, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    stmt = select(Subject).where(Subject.institution_id == p.institution_id).order_by(Subject.name)
    if p.role == Role.student.value:
        stmt = stmt.join(Enrollment, Enrollment.subject_id == Subject.id).where(Enrollment.user_id == p.id)
    if q:
        stmt = stmt.where(Subject.name.ilike(f"%{q}%"))
    rows, total = page(db, stmt, min(limit, 100), offset)
    ids = [s.id for s in rows]
    docs = dict(db.execute(select(StudyMaterial.subject_id, func.count()).where(StudyMaterial.subject_id.in_(ids)).group_by(StudyMaterial.subject_id)).all())
    students = dict(db.execute(select(Enrollment.subject_id, func.count()).where(Enrollment.subject_id.in_(ids)).group_by(Enrollment.subject_id)).all())
    exams = dict(db.execute(select(Examination.subject_id, func.count()).where(Examination.subject_id.in_(ids)).group_by(Examination.subject_id)).all())
    return {"items": [subject_out(s, documents=docs.get(s.id, 0), students=students.get(s.id, 0), examinations=exams.get(s.id, 0)) for s in rows], "total": total}


@router.post("/subjects", status_code=201, tags=["subjects"])
def create_subject(body: SubjectIn, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    if body.course_id and db.get(Course, body.course_id) is None:
        raise not_found("Course")
    if db.scalar(select(Subject).where(Subject.institution_id == p.institution_id, Subject.code == body.code)):
        raise conflict(f"Subject code {body.code} is already in use")
    s = Subject(institution_id=p.institution_id, created_by=p.id, **body.model_dump())
    db.add(s)
    db.flush()
    audit(db, "subject.created", "subject", s.id, actor_id=p.id, after={"name": s.name})
    db.commit()
    return subject_out(s)


@router.get("/subjects/{subject_id}", tags=["subjects"])
def get_subject(subject_id: uuid.UUID, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    s = own_subject(db, p, subject_id)
    if p.role == Role.student.value and not db.scalar(select(Enrollment).where(Enrollment.subject_id == s.id, Enrollment.user_id == p.id)):
        raise not_found("Subject")
    return subject_out(s)


@router.put("/subjects/{subject_id}", tags=["subjects"])
def update_subject(subject_id: uuid.UUID, body: SubjectIn, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    s = own_subject(db, p, subject_id)
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    audit(db, "subject.updated", "subject", s.id, actor_id=p.id)
    db.commit()
    return subject_out(s)


@router.delete("/subjects/{subject_id}", status_code=204, tags=["subjects"])
def delete_subject(subject_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    s = own_subject(db, p, subject_id)
    if db.scalar(select(func.count()).select_from(Examination).where(Examination.subject_id == s.id)):
        raise conflict("This subject has examinations and cannot be deleted")
    audit(db, "subject.deleted", "subject", s.id, actor_id=p.id, before={"name": s.name})
    db.delete(s)
    db.commit()


@router.get("/subjects/{subject_id}/enrollments", tags=["subjects"])
def enrollments(subject_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    own_subject(db, p, subject_id)
    rows = db.scalars(select(Enrollment).where(Enrollment.subject_id == subject_id)).unique().all()
    return {"items": [{"id": str(e.user.id), "email": e.user.email, "full_name": e.user.profile.full_name if e.user.profile else ""} for e in rows]}


@router.post("/subjects/{subject_id}/enrollments", tags=["subjects"])
def enroll(subject_id: uuid.UUID, body: EnrollIn, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    from app.models import InstitutionMembership
    own_subject(db, p, subject_id)
    added = 0
    for uid in body.user_ids:
        if not db.scalar(select(InstitutionMembership).where(InstitutionMembership.user_id == uid, InstitutionMembership.institution_id == p.institution_id)):
            raise bad_request("Students must belong to this institution")
        if not db.scalar(select(Enrollment).where(Enrollment.subject_id == subject_id, Enrollment.user_id == uid)):
            db.add(Enrollment(institution_id=p.institution_id, subject_id=subject_id, user_id=uid))
            added += 1
    audit(db, "subject.enrolled", "subject", subject_id, actor_id=p.id, after={"added": added})
    db.commit()
    return {"added": added}


@router.delete("/subjects/{subject_id}/enrollments/{user_id}", status_code=204, tags=["subjects"])
def unenroll(subject_id: uuid.UUID, user_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    own_subject(db, p, subject_id)
    db.query(Enrollment).filter(Enrollment.subject_id == subject_id, Enrollment.user_id == user_id).delete()
    db.commit()


# ------------------------------------------------------- documents
def material_out(m: StudyMaterial) -> dict:
    return {"id": str(m.id), "subject_id": str(m.subject_id), "title": m.title, "kind": m.kind, "filename": m.filename, "size_bytes": m.size_bytes,
            "status": m.status, "page_count": m.page_count, "chunk_count": m.chunk_count, "error": m.error, "created_at": m.created_at}


@router.post("/documents/upload-url", tags=["documents"])
def document_upload_url(body: UploadUrlIn, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    s = get_settings()
    own_subject(db, p, body.subject_id)
    if not body.filename.lower().endswith(ALLOWED_EXT):
        raise bad_request("Only PDF, TXT and DOCX files are supported", "unsupported_file")
    if body.size_bytes > s.max_upload_size_mb * 1024 * 1024:
        raise DomainError(413, "file_too_large", f"Files can be at most {s.max_upload_size_mb} MB")
    path = f"{p.institution_id}/documents/{body.subject_id}/{uuid.uuid4()}-{safe_name(body.filename)}"
    up = get_storage().signed_upload(path, body.content_type)
    # The path is sealed in a signed token, so the client cannot register arbitrary storage objects.
    token = jwt.encode({"path": path, "filename": body.filename, "subject": str(body.subject_id), "inst": str(p.institution_id),
                        "exp": int(time.time()) + 3600}, s.signing_secret(), algorithm="HS256")
    return {"upload_url": up.url, "method": up.method, "headers": up.headers, "upload_token": token}


@router.post("/documents", status_code=201, tags=["documents"])
def register_document(body: DocumentIn, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    s = get_settings()
    try:
        t = jwt.decode(body.upload_token, s.signing_secret(), algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise bad_request("Upload expired. Please upload the file again.", "invalid_upload") from exc
    if t["inst"] != str(p.institution_id):
        raise forbidden()
    storage = get_storage()
    try:
        data = storage.read(t["path"])
    except StorageError as exc:
        raise bad_request("The file was not uploaded", "upload_missing") from exc
    if len(data) > s.max_upload_size_mb * 1024 * 1024:
        storage.delete(t["path"])
        raise DomainError(413, "file_too_large", f"Files can be at most {s.max_upload_size_mb} MB")
    try:
        kind = detect_kind(data, t["filename"])
    except UnsupportedDocument as exc:
        storage.delete(t["path"])
        raise bad_request(str(exc), "unsupported_file") from exc
    digest = hashlib.sha256(data).hexdigest()
    if db.scalar(select(StudyMaterial).where(StudyMaterial.subject_id == t["subject"], StudyMaterial.sha256 == digest)):
        storage.delete(t["path"])
        raise conflict("This document is already in this subject")
    mime = {"pdf": "application/pdf", "txt": "text/plain", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}[kind]
    m = StudyMaterial(institution_id=p.institution_id, subject_id=uuid.UUID(t["subject"]), title=body.title, kind=body.kind, storage_path=t["path"],
                      filename=t["filename"], mime_type=mime, size_bytes=len(data), sha256=digest, uploaded_by=p.id)
    db.add(m)
    db.flush()
    _queue_index(db, m, 1)
    audit(db, "document.uploaded", "study_material", m.id, actor_id=p.id, after={"title": m.title})
    db.commit()
    return material_out(m)


def _queue_index(db: Session, m: StudyMaterial, attempt: int) -> None:
    job = enqueue(db, "index_document", {"material_id": str(m.id)}, f"index:{m.id}:{attempt}", m.institution_id)
    db.add(DocumentProcessingJob(institution_id=m.institution_id, material_id=m.id, background_job_id=job.id))


@router.get("/documents", tags=["documents"])
def documents(subject_id: uuid.UUID | None = None, status: str | None = None, limit: int = 50, offset: int = 0, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    stmt = select(StudyMaterial).where(StudyMaterial.institution_id == p.institution_id).order_by(StudyMaterial.created_at.desc())
    if subject_id:
        stmt = stmt.where(StudyMaterial.subject_id == subject_id)
    if status:
        stmt = stmt.where(StudyMaterial.status == status)
    rows, total = page(db, stmt, min(limit, 100), offset)
    return {"items": [material_out(m) for m in rows], "total": total}


def own_material(db: Session, p: Principal, doc_id) -> StudyMaterial:
    m = db.get(StudyMaterial, doc_id)
    if m is None or m.institution_id != p.institution_id:
        raise not_found("Document")
    return m


@router.get("/documents/{doc_id}", tags=["documents"])
def document(doc_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    m = own_material(db, p, doc_id)
    return {**material_out(m), "download_url": get_storage().signed_download(m.storage_path), "metadata": m.doc_metadata}


@router.post("/documents/{doc_id}/process", tags=["documents"])
@router.post("/documents/{doc_id}/retry", tags=["documents"])
def retry_document(doc_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    m = own_material(db, p, doc_id)
    if m.status not in (MaterialStatus.failed.value, MaterialStatus.uploaded.value):
        raise conflict(f"Document is {m.status}")
    require_ai()
    attempts = db.scalar(select(func.count()).select_from(DocumentProcessingJob).where(DocumentProcessingJob.material_id == m.id)) or 0
    m.status, m.error = MaterialStatus.uploaded.value, None
    _queue_index(db, m, attempts + 1)
    audit(db, "document.retry", "study_material", m.id, actor_id=p.id)
    db.commit()
    return material_out(m)


@router.delete("/documents/{doc_id}", status_code=204, tags=["documents"])
def delete_document(doc_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    m = own_material(db, p, doc_id)
    audit(db, "document.deleted", "study_material", m.id, actor_id=p.id, before={"title": m.title})
    path = m.storage_path
    db.delete(m)
    db.commit()
    get_storage().delete(path)


@router.get("/subjects/{subject_id}/topics", tags=["documents"])
def subject_topics(subject_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    """Chapters found while indexing, offered as topic suggestions."""
    from app.models import DocumentChunk
    own_subject(db, p, subject_id)
    rows = db.scalars(select(DocumentChunk.chapter).where(DocumentChunk.subject_id == subject_id, DocumentChunk.chapter.is_not(None)).distinct()).all()
    bank = db.scalars(select(QuestionBankItem.topic).where(QuestionBankItem.subject_id == subject_id).distinct()).all()
    return {"items": sorted(set(rows) | set(bank))}


# ------------------------------------------------------- question bank
def bank_out(q: QuestionBankItem) -> dict:
    return {"id": str(q.id), "subject_id": str(q.subject_id), "question_text": q.question_text, "topic": q.topic, "difficulty": q.difficulty,
            "question_type": q.question_type, "marks": float(q.marks), "expected_answer": q.expected_answer, "expected_concepts": q.expected_concepts,
            "rubric": q.rubric, "source_references": q.source_references, "origin": q.origin}


@router.get("/questions", tags=["questions"])
def questions(subject_id: uuid.UUID | None = None, topic: str | None = None, difficulty: str | None = None, limit: int = 50, offset: int = 0,
              p: Principal = Depends(staff), db: Session = Depends(get_db)):
    stmt = select(QuestionBankItem).where(QuestionBankItem.institution_id == p.institution_id).order_by(QuestionBankItem.created_at.desc())
    for col, val in ((QuestionBankItem.subject_id, subject_id), (QuestionBankItem.topic, topic), (QuestionBankItem.difficulty, difficulty)):
        if val:
            stmt = stmt.where(col == val)
    rows, total = page(db, stmt, min(limit, 100), offset)
    return {"items": [bank_out(q) for q in rows], "total": total}


@router.post("/questions", status_code=201, tags=["questions"])
def create_question(body: BankQuestionIn, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    own_subject(db, p, body.subject_id)
    data = body.model_dump()
    data["rubric"] = [r.model_dump() for r in body.rubric]
    q = QuestionBankItem(institution_id=p.institution_id, created_by=p.id, origin="manual", **data)
    db.add(q)
    db.commit()
    return bank_out(q)


@router.post("/questions/generate", status_code=201, tags=["questions"])
def generate_questions(body: GenerateQuestionsIn, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    own_subject(db, p, body.subject_id)
    require_ai()
    rate_limit(db, f"generate:{p.id}")
    slots = build_blueprint(total_marks=body.marks * body.count, mark_distribution=[{"marks": body.marks, "count": body.count}],
                            difficulty={body.difficulty: 1}, question_types=[body.question_type], topics=body.topics)
    existing = list(db.scalars(select(QuestionBankItem.question_text).where(QuestionBankItem.subject_id == body.subject_id).limit(100)))
    state = build_paper_graph(get_ai(), retriever_for(db, p.institution_id, body.subject_id, body.material_ids or None)).invoke(
        {"slots": slots, "existing_questions": existing, "instructions": ""}, {"recursion_limit": 30})
    out = []
    for q in state["questions"]:
        row = QuestionBankItem(institution_id=p.institution_id, subject_id=body.subject_id, question_text=q.question_text, topic=q.topic, difficulty=q.difficulty,
                               question_type=q.question_type, marks=q.marks, expected_answer=q.expected_answer, expected_concepts=q.expected_concepts,
                               rubric=[c.model_dump() for c in q.rubric], source_references=[r.model_dump() for r in q.source_references], origin="ai", created_by=p.id)
        db.add(row)
        out.append(row)
    db.commit()
    return {"items": [bank_out(q) for q in out], "warnings": state.get("warnings", [])}


def own_bank(db: Session, p: Principal, qid) -> QuestionBankItem:
    q = db.get(QuestionBankItem, qid)
    if q is None or q.institution_id != p.institution_id:
        raise not_found("Question")
    return q


@router.put("/questions/{question_id}", tags=["questions"])
def update_question(question_id: uuid.UUID, body: BankQuestionIn, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    q = own_bank(db, p, question_id)
    data = body.model_dump()
    data["rubric"] = [r.model_dump() for r in body.rubric]
    for k, v in data.items():
        setattr(q, k, v)
    db.commit()
    return bank_out(q)


@router.delete("/questions/{question_id}", status_code=204, tags=["questions"])
def delete_question(question_id: uuid.UUID, p: Principal = Depends(staff), db: Session = Depends(get_db)):
    db.delete(own_bank(db, p, question_id))
    db.commit()



