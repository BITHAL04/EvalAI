"""Request bodies. Marks, roles and owner ids are validated here or derived on the server."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from ai_engine.schemas import CriterionCategory, Difficulty, QuestionType


class SubjectIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    code: str = Field(min_length=2, max_length=40)
    semester: str | None = Field(None, max_length=40)
    description: str = ""
    course_id: UUID | None = None


class CourseIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    code: str = Field(min_length=2, max_length=40)
    description: str = ""


class UploadUrlIn(BaseModel):
    filename: str = Field(min_length=1, max_length=300)
    size_bytes: int = Field(gt=0)
    content_type: str = "application/octet-stream"
    subject_id: UUID


class DocumentIn(BaseModel):
    upload_token: str
    title: str = Field(min_length=2, max_length=300)
    kind: Literal["textbook", "ebook", "notes", "reference", "past_paper", "question_bank", "course_material"] = "reference"


class RubricCriterionIn(BaseModel):
    criterion: str = Field(min_length=2, max_length=200)
    category: CriterionCategory = "conceptual_correctness"
    max_marks: float = Field(gt=0)
    expected_evidence: str = ""


class BankQuestionIn(BaseModel):
    subject_id: UUID
    question_text: str = Field(min_length=10)
    topic: str = Field(min_length=2, max_length=200)
    difficulty: Difficulty = "Medium"
    question_type: QuestionType = "descriptive"
    marks: float = Field(gt=0, le=100)
    expected_answer: str = ""
    expected_concepts: list[str] = []
    rubric: list[RubricCriterionIn] = []


class GenerateQuestionsIn(BaseModel):
    subject_id: UUID
    topics: list[str] = Field(min_length=1)
    material_ids: list[UUID] = []
    count: int = Field(3, ge=1, le=10)
    marks: float = Field(5, gt=0, le=100)
    difficulty: Difficulty = "Medium"
    question_type: QuestionType = "descriptive"


class MarkRow(BaseModel):
    marks: float = Field(gt=0, le=100)
    count: int = Field(ge=1, le=50)


class ExamIn(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    subject_id: UUID
    course_id: UUID | None = None
    semester: str | None = None
    topics: list[str] = Field(min_length=1)
    material_ids: list[UUID] = []
    total_marks: float = Field(gt=0, le=1000)
    duration_minutes: int = Field(gt=0, le=600)
    difficulty: dict[Difficulty, float] = {"Easy": 30, "Medium": 50, "Hard": 20}
    question_types: list[QuestionType] = Field(default=["descriptive"], min_length=1)
    mark_distribution: list[MarkRow] = Field(min_length=1)
    negative_marking: bool = False
    instructions: str = ""
    generation_notes: str = ""
    duplicate_policy: Literal["replace", "reject"] = "replace"
    submission_deadline: datetime | None = None

    @model_validator(mode="after")
    def totals(self):
        s = sum(r.marks * r.count for r in self.mark_distribution)
        if abs(s - self.total_marks) > 1e-6:
            raise ValueError(f"Mark distribution adds up to {s:g}, not {self.total_marks:g}")
        return self


class ExamUpdate(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=300)
    duration_minutes: int | None = Field(None, gt=0, le=600)
    instructions: str | None = None
    duplicate_policy: Literal["replace", "reject"] | None = None
    submission_deadline: datetime | None = None


class QuestionUpdate(BaseModel):
    question_text: str | None = Field(None, min_length=10)
    topic: str | None = None
    difficulty: Difficulty | None = None
    marks: float | None = Field(None, gt=0, le=100)
    expected_answer: str | None = None
    expected_concepts: list[str] | None = None
    rubric: list[RubricCriterionIn] | None = None


class ExamQuestionIn(BaseModel):
    question_text: str = Field(min_length=10)
    topic: str
    difficulty: Difficulty = "Medium"
    question_type: QuestionType = "descriptive"
    marks: float = Field(gt=0)
    expected_answer: str = Field(min_length=3)
    expected_concepts: list[str] = []
    rubric: list[RubricCriterionIn] = Field(min_length=1)


class SubmissionIn(BaseModel):
    examination_id: UUID
    filename: str = Field(min_length=1, max_length=300)
    size_bytes: int = Field(gt=0)


class AnswerCorrectionIn(BaseModel):
    corrected_text: str
    question_number: int | None = None


class CriterionMark(BaseModel):
    criterion_id: UUID
    awarded_marks: float = Field(ge=0)
    reason: str = Field(min_length=3)


class TeacherReviewIn(BaseModel):
    criteria: list[CriterionMark] = Field(min_length=1)
    reason: str = Field(min_length=3)


class ChallengeIn(BaseModel):
    evaluation_id: UUID
    category: Literal["incorrect_deduction", "missed_concept", "incomplete_answer_key", "incorrect_rubric", "ambiguous_question", "handwriting_error", "diagram_interpretation"]
    rubric_criterion_id: UUID | None = None
    explanation: str = Field(min_length=20, max_length=4000)
    evidence: list[str] = Field(default=[], max_length=5)


class ChallengeDecisionIn(BaseModel):
    decision: Literal["accepted", "partially_accepted", "rejected"]
    revised_marks: float | None = Field(None, ge=0)
    criterion_marks: dict[UUID, float] | None = None
    reason: str = Field(min_length=5)
    rubric_note: str | None = None


class BenchmarkIn(BaseModel):
    tier: Literal["strong", "average", "weak"]
    answer_text: str = Field(min_length=10)
    expected_marks: float = Field(ge=0)


class InstitutionIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9-]{2,80}$")


class InviteIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: Literal["admin", "teacher", "student"]
    full_name: str = ""


class EnrollIn(BaseModel):
    user_ids: list[UUID] = Field(min_length=1)


class MembershipUpdate(BaseModel):
    is_active: bool
