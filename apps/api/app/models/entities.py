"""All persistent entities. Tables with the Tenant mixin are isolated by RLS (see migration 0002)."""
from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import PK, Base, Tenant, Timestamps, fk

EMBEDDING_DIM = 768  # must match GEMINI output dimensionality; changing it requires a migration.


class Role(str, enum.Enum):
    admin = "admin"
    teacher = "teacher"
    student = "student"


class JobStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    requires_review = "requires_review"


class MaterialStatus(str, enum.Enum):
    uploaded = "uploaded"
    processing = "processing"
    indexed = "indexed"
    failed = "failed"


class ExamStatus(str, enum.Enum):
    draft = "draft"
    generating = "generating"
    review = "review"
    published = "published"
    closed = "closed"
    results_published = "results_published"


class SubmissionStatus(str, enum.Enum):
    awaiting_upload = "awaiting_upload"
    uploaded = "uploaded"
    submitted = "submitted"
    extracting = "extracting"
    extracted = "extracted"
    evaluating = "evaluating"
    evaluated = "evaluated"
    approved = "approved"
    failed = "failed"
    superseded = "superseded"


class EvaluationStatus(str, enum.Enum):
    provisional = "provisional"
    needs_review = "needs_review"
    teacher_reviewed = "teacher_reviewed"
    approved = "approved"


class ChallengeStatus(str, enum.Enum):
    submitted = "submitted"
    under_ai_review = "under_ai_review"
    pending_teacher_review = "pending_teacher_review"
    accepted = "accepted"
    partially_accepted = "partially_accepted"
    rejected = "rejected"
    resolved = "resolved"


# ---------------------------------------------------------------- identity & organization
class Institution(PK, Timestamps, Base):
    __tablename__ = "institutions"
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class User(PK, Timestamps, Base):
    __tablename__ = "users"
    clerk_user_id: Mapped[str | None] = mapped_column(String(120), unique=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    profile: Mapped["UserProfile"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan", lazy="joined")


class UserProfile(PK, Timestamps, Base):
    __tablename__ = "user_profiles"
    user_id: Mapped[uuid.UUID] = fk("users.id")
    __table_args__ = (UniqueConstraint("user_id"),)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    avatar_url: Mapped[str | None] = mapped_column(Text)
    roll_number: Mapped[str | None] = mapped_column(String(60))
    department: Mapped[str | None] = mapped_column(String(120))
    user: Mapped[User] = relationship(back_populates="profile")


class RoleRow(PK, Base):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(30), unique=True)
    description: Mapped[str] = mapped_column(String(200), default="")


class InstitutionMembership(PK, Timestamps, Base):
    """The only source of a user's role. Never read from a client or a token claim."""
    __tablename__ = "institution_memberships"
    __table_args__ = (UniqueConstraint("institution_id", "user_id"),)
    institution_id: Mapped[uuid.UUID] = fk("institutions.id")
    user_id: Mapped[uuid.UUID] = fk("users.id")
    role_id: Mapped[uuid.UUID] = fk("roles.id", ondelete="RESTRICT")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[RoleRow] = relationship(lazy="joined")


class Invitation(PK, Timestamps, Tenant, Base):
    __tablename__ = "invitations"
    __table_args__ = (UniqueConstraint("institution_id", "email"),)
    email: Mapped[str] = mapped_column(String(320), index=True)
    role: Mapped[str] = mapped_column(String(30))
    full_name: Mapped[str] = mapped_column(String(200), default="")
    invited_by: Mapped[uuid.UUID | None] = fk("users.id", ondelete="SET NULL", nullable=True, index=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Course(PK, Timestamps, Tenant, Base):
    __tablename__ = "courses"
    __table_args__ = (UniqueConstraint("institution_id", "code"),)
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text, default="")


class Subject(PK, Timestamps, Tenant, Base):
    __tablename__ = "subjects"
    __table_args__ = (UniqueConstraint("institution_id", "code"),)
    course_id: Mapped[uuid.UUID | None] = fk("courses.id", ondelete="SET NULL", nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(40))
    semester: Mapped[str | None] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[uuid.UUID | None] = fk("users.id", ondelete="SET NULL", nullable=True, index=False)


class Enrollment(PK, Timestamps, Tenant, Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("subject_id", "user_id"),)
    subject_id: Mapped[uuid.UUID] = fk("subjects.id")
    user_id: Mapped[uuid.UUID] = fk("users.id")
    user: Mapped[User] = relationship(lazy="joined")


# ---------------------------------------------------------------- academic documents
class StudyMaterial(PK, Timestamps, Tenant, Base):
    __tablename__ = "study_materials"
    __table_args__ = (UniqueConstraint("subject_id", "sha256"),)
    subject_id: Mapped[uuid.UUID] = fk("subjects.id")
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(40), default="reference")  # textbook|notes|reference|past_paper|question_bank
    storage_path: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(String(300))
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default=MaterialStatus.uploaded.value, index=True)
    page_count: Mapped[int | None] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    doc_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[uuid.UUID | None] = fk("users.id", ondelete="SET NULL", nullable=True, index=False)


class DocumentChunk(PK, Tenant, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("material_id", "chunk_index"),
        Index("ix_document_chunks_embedding_hnsw", "embedding", postgresql_using="hnsw",
              postgresql_ops={"embedding": "vector_cosine_ops"}),
    )
    material_id: Mapped[uuid.UUID] = fk("study_materials.id")
    subject_id: Mapped[uuid.UUID] = fk("subjects.id")
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    chapter: Mapped[str | None] = mapped_column(String(300), index=True)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentProcessingJob(PK, Timestamps, Tenant, Base):
    __tablename__ = "document_processing_jobs"
    material_id: Mapped[uuid.UUID] = fk("study_materials.id")
    background_job_id: Mapped[uuid.UUID | None] = fk("background_jobs.id", ondelete="SET NULL", nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=JobStatus.queued.value)
    stage: Mapped[str] = mapped_column(String(40), default="queued")
    error: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------- examination
class QuestionBankItem(PK, Timestamps, Tenant, Base):
    __tablename__ = "question_bank"
    subject_id: Mapped[uuid.UUID] = fk("subjects.id")
    question_text: Mapped[str] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(String(200), default="General", index=True)
    difficulty: Mapped[str] = mapped_column(String(20), default="Medium")
    question_type: Mapped[str] = mapped_column(String(40), default="descriptive")
    marks: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    expected_answer: Mapped[str] = mapped_column(Text, default="")
    expected_concepts: Mapped[list[str]] = mapped_column(JSONB, default=list)
    rubric: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    source_references: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    origin: Mapped[str] = mapped_column(String(20), default="manual")  # manual|ai|seed
    created_by: Mapped[uuid.UUID | None] = fk("users.id", ondelete="SET NULL", nullable=True, index=False)


class Examination(PK, Timestamps, Tenant, Base):
    __tablename__ = "examinations"
    subject_id: Mapped[uuid.UUID] = fk("subjects.id", ondelete="RESTRICT")
    course_id: Mapped[uuid.UUID | None] = fk("courses.id", ondelete="SET NULL", nullable=True, index=False)
    title: Mapped[str] = mapped_column(String(300))
    semester: Mapped[str | None] = mapped_column(String(40))
    total_marks: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    instructions: Mapped[str] = mapped_column(Text, default="")
    negative_marking: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(30), default=ExamStatus.draft.value, index=True)
    generation_error: Mapped[str | None] = mapped_column(Text)
    paper_storage_path: Mapped[str | None] = mapped_column(Text)
    duplicate_policy: Mapped[str] = mapped_column(String(20), default="replace")  # replace|reject
    submission_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None] = fk("users.id", ondelete="SET NULL", nullable=True, index=False)
    results_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[uuid.UUID | None] = fk("users.id", ondelete="SET NULL", nullable=True, index=False)
    subject: Mapped[Subject] = relationship(lazy="joined")
    questions: Mapped[list["ExaminationQuestion"]] = relationship(
        back_populates="examination", cascade="all, delete-orphan", order_by="ExaminationQuestion.question_number")


class ExaminationQuestion(PK, Timestamps, Tenant, Base):
    __tablename__ = "examination_questions"
    __table_args__ = (
        UniqueConstraint("examination_id", "question_number", deferrable=True, initially="DEFERRED"),
        CheckConstraint("marks > 0", name="marks_positive"),
    )
    examination_id: Mapped[uuid.UUID] = fk("examinations.id")
    question_number: Mapped[int] = mapped_column(Integer)
    question_text: Mapped[str] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(String(200), index=True)
    difficulty: Mapped[str] = mapped_column(String(20))
    question_type: Mapped[str] = mapped_column(String(40))
    marks: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    expected_answer: Mapped[str] = mapped_column(Text)
    expected_concepts: Mapped[list[str]] = mapped_column(JSONB, default=list)
    source_references: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    origin: Mapped[str] = mapped_column(String(20), default="ai")  # ai|manual|bank|seed
    understanding: Mapped[dict | None] = mapped_column(JSONB)  # cached so every student sees the same reading
    examination: Mapped[Examination] = relationship(back_populates="questions")
    rubrics: Mapped[list["Rubric"]] = relationship(back_populates="question", cascade="all, delete-orphan", order_by="Rubric.version")


class ExaminationTopic(PK, Tenant, Base):
    __tablename__ = "examination_topics"
    __table_args__ = (UniqueConstraint("examination_id", "name"),)
    examination_id: Mapped[uuid.UUID] = fk("examinations.id")
    name: Mapped[str] = mapped_column(String(200))
    weight: Mapped[float] = mapped_column(Float, default=1.0)


class Rubric(PK, Timestamps, Tenant, Base):
    """Immutable once approved; an edit after approval creates the next version."""
    __tablename__ = "rubrics"
    __table_args__ = (UniqueConstraint("question_id", "version"),)
    question_id: Mapped[uuid.UUID] = fk("examination_questions.id")
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|approved|superseded
    expected_answer: Mapped[str] = mapped_column(Text, default="")
    expected_concepts: Mapped[list[str]] = mapped_column(JSONB, default=list)
    change_reason: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[uuid.UUID | None] = fk("users.id", ondelete="SET NULL", nullable=True, index=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    question: Mapped[ExaminationQuestion] = relationship(back_populates="rubrics")
    criteria: Mapped[list["RubricCriterion"]] = relationship(
        back_populates="rubric", cascade="all, delete-orphan", order_by="RubricCriterion.position", lazy="selectin")


class RubricCriterion(PK, Tenant, Base):
    __tablename__ = "rubric_criteria"
    __table_args__ = (
        UniqueConstraint("rubric_id", "position"),
        CheckConstraint("max_marks > 0", name="max_positive"),
    )
    rubric_id: Mapped[uuid.UUID] = fk("rubrics.id")
    position: Mapped[int] = mapped_column(Integer)
    criterion: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(40), default="conceptual_correctness")
    max_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    expected_evidence: Mapped[str] = mapped_column(Text, default="")
    rubric: Mapped[Rubric] = relationship(back_populates="criteria")


# ---------------------------------------------------------------- submissions
class Submission(PK, Timestamps, Tenant, Base):
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("examination_id", "student_id", "version"),
        Index("uq_submissions_current", "examination_id", "student_id", unique=True,
              postgresql_where="is_current"),
    )
    examination_id: Mapped[uuid.UUID] = fk("examinations.id", ondelete="RESTRICT")
    student_id: Mapped[uuid.UUID] = fk("users.id", ondelete="RESTRICT")
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(30), default=SubmissionStatus.awaiting_upload.value, index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    examination: Mapped[Examination] = relationship(lazy="joined")
    files: Mapped[list["SubmissionFile"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class SubmissionFile(PK, Timestamps, Tenant, Base):
    __tablename__ = "submission_files"
    submission_id: Mapped[uuid.UUID] = fk("submissions.id")
    storage_path: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(String(300))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    page_count: Mapped[int | None] = mapped_column(Integer)
    page_image_paths: Mapped[list[str]] = mapped_column(JSONB, default=list)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExtractionJob(PK, Timestamps, Tenant, Base):
    __tablename__ = "extraction_jobs"
    submission_id: Mapped[uuid.UUID] = fk("submissions.id")
    background_job_id: Mapped[uuid.UUID | None] = fk("background_jobs.id", ondelete="SET NULL", nullable=True, index=False)
    status: Mapped[str] = mapped_column(String(20), default=JobStatus.queued.value)
    pages_total: Mapped[int] = mapped_column(Integer, default=0)
    pages_done: Mapped[int] = mapped_column(Integer, default=0)
    page_failures: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    model: Mapped[str | None] = mapped_column(String(120))


class ExtractedAnswer(PK, Timestamps, Tenant, Base):
    __tablename__ = "extracted_answers"
    __table_args__ = (UniqueConstraint("submission_id", "question_number"),)
    submission_id: Mapped[uuid.UUID] = fk("submissions.id")
    question_id: Mapped[uuid.UUID | None] = fk("examination_questions.id", ondelete="SET NULL", nullable=True)
    question_number: Mapped[int] = mapped_column(Integer)  # 0 = could not be attributed to a question
    recognized_text: Mapped[str] = mapped_column(Text, default="")
    corrected_text: Mapped[str | None] = mapped_column(Text)
    corrected_by: Mapped[uuid.UUID | None] = fk("users.id", ondelete="SET NULL", nullable=True, index=False)
    ocr_confidence: Mapped[float] = mapped_column(Float, default=0)
    contains_diagram: Mapped[bool] = mapped_column(Boolean, default=False)
    contains_equation: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_human_verification: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_reasons: Mapped[list[str]] = mapped_column(JSONB, default=list)
    page_references: Mapped[list["AnswerPageReference"]] = relationship(cascade="all, delete-orphan", lazy="selectin")

    @property
    def best_text(self) -> str:
        return self.corrected_text if self.corrected_text is not None else self.recognized_text


class AnswerPageReference(PK, Tenant, Base):
    __tablename__ = "answer_page_references"
    extracted_answer_id: Mapped[uuid.UUID] = fk("extracted_answers.id")
    page_number: Mapped[int] = mapped_column(Integer)
    region: Mapped[str] = mapped_column(String(200), default="")


# ---------------------------------------------------------------- evaluation
class Evaluation(PK, Timestamps, Tenant, Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        UniqueConstraint("submission_id", "question_id"),
        CheckConstraint("marks_awarded IS NULL OR (marks_awarded >= 0 AND marks_awarded <= max_marks)", name="marks_bounds"),
    )
    submission_id: Mapped[uuid.UUID] = fk("submissions.id")
    question_id: Mapped[uuid.UUID] = fk("examination_questions.id", ondelete="RESTRICT")
    rubric_id: Mapped[uuid.UUID] = fk("rubrics.id", ondelete="RESTRICT")
    extracted_answer_id: Mapped[uuid.UUID | None] = fk("extracted_answers.id", ondelete="SET NULL", nullable=True, index=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default=EvaluationStatus.provisional.value, index=True)
    marks_awarded: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))  # NULL = could not be evaluated
    max_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    confidence: Mapped[float] = mapped_column(Float, default=0)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reasons: Mapped[list[str]] = mapped_column(JSONB, default=list)
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    model: Mapped[str | None] = mapped_column(String(120))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    criterion_scores: Mapped[list["CriterionScore"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    evidence: Mapped[list["EvaluationEvidence"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class CriterionScore(PK, Tenant, Base):
    """Scores of the *current* version. History lives in evaluation_versions.snapshot."""
    __tablename__ = "criterion_scores"
    __table_args__ = (
        UniqueConstraint("evaluation_id", "rubric_criterion_id"),
        CheckConstraint("awarded_marks >= 0 AND awarded_marks <= max_marks", name="bounds"),
    )
    evaluation_id: Mapped[uuid.UUID] = fk("evaluations.id")
    rubric_criterion_id: Mapped[uuid.UUID] = fk("rubric_criteria.id", ondelete="RESTRICT")
    criterion: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(40), default="")
    max_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    awarded_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    reason: Mapped[str] = mapped_column(Text, default="")


class EvaluationEvidence(PK, Tenant, Base):
    __tablename__ = "evaluation_evidence"
    evaluation_id: Mapped[uuid.UUID] = fk("evaluations.id")
    kind: Mapped[str] = mapped_column(String(30))  # answer_quote|page_image|reference|deduction
    page_number: Mapped[int | None] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")


class EvaluationVersion(PK, Tenant, Base):
    """Append-only; a database trigger rejects UPDATE and DELETE."""
    __tablename__ = "evaluation_versions"
    __table_args__ = (UniqueConstraint("evaluation_id", "version"),)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("evaluations.id", ondelete="RESTRICT"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    rubric_id: Mapped[uuid.UUID] = fk("rubrics.id", ondelete="RESTRICT", index=False)
    marks_awarded: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    actor_type: Mapped[str] = mapped_column(String(20))  # ai|teacher|challenge
    actor_id: Mapped[uuid.UUID | None] = fk("users.id", ondelete="SET NULL", nullable=True, index=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BenchmarkAnswer(PK, Timestamps, Tenant, Base):
    __tablename__ = "benchmark_answers"
    __table_args__ = (UniqueConstraint("question_id", "tier"),)
    question_id: Mapped[uuid.UUID] = fk("examination_questions.id")
    tier: Mapped[str] = mapped_column(String(20))  # strong|average|weak
    answer_text: Mapped[str] = mapped_column(Text)
    expected_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    last_ai_marks: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = fk("users.id", ondelete="SET NULL", nullable=True, index=False)


class ConsistencyReport(PK, Tenant, Base):
    __tablename__ = "consistency_reports"
    examination_id: Mapped[uuid.UUID] = fk("examinations.id")
    findings: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------- results & analytics
class Result(PK, Timestamps, Tenant, Base):
    __tablename__ = "results"
    __table_args__ = (UniqueConstraint("submission_id"),)
    submission_id: Mapped[uuid.UUID] = fk("submissions.id", ondelete="RESTRICT")
    examination_id: Mapped[uuid.UUID] = fk("examinations.id", ondelete="RESTRICT")
    student_id: Mapped[uuid.UUID] = fk("users.id", ondelete="RESTRICT")
    total_marks: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    max_marks: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    percentage: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="approved")  # approved|published
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None] = fk("users.id", ondelete="SET NULL", nullable=True, index=False)
    insights: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class TopicPerformance(PK, Tenant, Base):
    __tablename__ = "topic_performance"
    __table_args__ = (UniqueConstraint("result_id", "topic"),)
    result_id: Mapped[uuid.UUID] = fk("results.id")
    student_id: Mapped[uuid.UUID] = fk("users.id")
    examination_id: Mapped[uuid.UUID] = fk("examinations.id")
    subject_id: Mapped[uuid.UUID] = fk("subjects.id")
    topic: Mapped[str] = mapped_column(String(200))
    marks: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    max_marks: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    score: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30))


class StudentPerformanceSnapshot(PK, Tenant, Base):
    __tablename__ = "student_performance_snapshots"
    __table_args__ = (UniqueConstraint("student_id", "examination_id"),)
    student_id: Mapped[uuid.UUID] = fk("users.id")
    examination_id: Mapped[uuid.UUID] = fk("examinations.id")
    subject_id: Mapped[uuid.UUID] = fk("subjects.id")
    percentage: Mapped[float] = mapped_column(Float)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------- challenges
class Challenge(PK, Timestamps, Tenant, Base):
    __tablename__ = "challenges"
    __table_args__ = (Index("uq_challenge_open", "evaluation_id", unique=True,
                            postgresql_where="status IN ('submitted','under_ai_review','pending_teacher_review')"),)
    evaluation_id: Mapped[uuid.UUID] = fk("evaluations.id", ondelete="RESTRICT")
    submission_id: Mapped[uuid.UUID] = fk("submissions.id", ondelete="RESTRICT")
    question_id: Mapped[uuid.UUID] = fk("examination_questions.id", ondelete="RESTRICT", index=False)
    examination_id: Mapped[uuid.UUID] = fk("examinations.id", ondelete="RESTRICT")
    student_id: Mapped[uuid.UUID] = fk("users.id", ondelete="RESTRICT")
    category: Mapped[str] = mapped_column(String(40))
    rubric_criterion_id: Mapped[uuid.UUID | None] = fk("rubric_criteria.id", ondelete="SET NULL", nullable=True, index=False)
    explanation: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default=ChallengeStatus.submitted.value, index=True)
    original_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    revised_marks: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    original_rubric_id: Mapped[uuid.UUID] = fk("rubrics.id", ondelete="RESTRICT", index=False)
    revised_rubric_id: Mapped[uuid.UUID | None] = fk("rubrics.id", ondelete="SET NULL", nullable=True, index=False)
    evidence: Mapped[list["ChallengeEvidence"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    reviews: Mapped[list["ChallengeReview"]] = relationship(cascade="all, delete-orphan", lazy="selectin", order_by="ChallengeReview.created_at")
    decisions: Mapped[list["ChallengeDecision"]] = relationship(lazy="selectin", order_by="ChallengeDecision.decided_at")


class ChallengeEvidence(PK, Tenant, Base):
    __tablename__ = "challenge_evidence"
    challenge_id: Mapped[uuid.UUID] = fk("challenges.id")
    kind: Mapped[str] = mapped_column(String(20), default="text")
    content: Mapped[str] = mapped_column(Text)


class ChallengeReview(PK, Tenant, Base):
    __tablename__ = "challenge_reviews"
    challenge_id: Mapped[uuid.UUID] = fk("challenges.id")
    recommendation: Mapped[str] = mapped_column(String(30))  # accept|partially_accept|reject|escalate
    suggested_marks: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    reasoning: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    model: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChallengeDecision(PK, Tenant, Base):
    """Append-only; a database trigger rejects UPDATE and DELETE."""
    __tablename__ = "challenge_decisions"
    challenge_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("challenges.id", ondelete="RESTRICT"), index=True)
    decided_by: Mapped[uuid.UUID | None] = fk("users.id", ondelete="SET NULL", nullable=True, index=False)
    decision: Mapped[str] = mapped_column(String(30))
    original_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    revised_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    reason: Mapped[str] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------- platform
class Notification(PK, Tenant, Base):
    __tablename__ = "notifications"
    user_id: Mapped[uuid.UUID] = fk("users.id")
    kind: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str | None] = mapped_column(String(300))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class AuditLog(PK, Base):
    """Append-only; a database trigger rejects UPDATE and DELETE."""
    __tablename__ = "audit_logs"
    institution_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("institutions.id", ondelete="SET NULL"), index=True)
    actor_id: Mapped[uuid.UUID | None] = fk("users.id", ondelete="SET NULL", nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), default="user")  # user|system|ai
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), index=True)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    # Client-side default: an INSERT ... RETURNING would need read access the writer may not have.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now(), index=True)


class BackgroundJob(PK, Timestamps, Base):
    __tablename__ = "background_jobs"
    __table_args__ = (
        Index("ix_background_jobs_claim", "status", "run_after"),
        UniqueConstraint("idempotency_key"),
    )
    institution_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), index=True)
    job_type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default=JobStatus.queued.value)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=4)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_by: Mapped[str | None] = mapped_column(String(100))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    progress: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)


class RateLimitHit(Base):
    """Fixed-window counters kept in Postgres so limits hold across Render instances."""
    __tablename__ = "rate_limit_hits"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
