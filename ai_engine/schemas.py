"""Typed contracts for every AI operation. Nothing unvalidated leaves the provider layer."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Difficulty = Literal["Easy", "Medium", "Hard"]
QuestionType = Literal["short_answer", "descriptive", "long_answer", "analytical", "application",
                       "case_study", "derivation", "diagram"]
CriterionCategory = Literal["conceptual_correctness", "relevance", "coverage", "explanation_depth", "technical_accuracy",
                            "logical_reasoning", "examples", "diagram", "mathematical", "organization"]


class SourceReference(BaseModel):
    material_id: str
    material_title: str = ""
    chunk_id: str
    page_start: int | None = None
    page_end: int | None = None
    chapter: str | None = None
    score: float | None = None


class RetrievedChunk(SourceReference):
    text: str


# ---- question generation
class BlueprintSlot(BaseModel):
    slot: int
    marks: float = Field(gt=0)
    difficulty: Difficulty
    question_type: QuestionType
    topic: str


class GeneratedQuestion(BaseModel):
    slot: int
    question_text: str = Field(min_length=10)
    topic: str
    expected_answer: str = Field(min_length=10)
    expected_concepts: list[str] = Field(min_length=1)
    source_chunk_ids: list[str] = Field(default_factory=list)


class GeneratedQuestionSet(BaseModel):
    questions: list[GeneratedQuestion]


class DifficultyVerdict(BaseModel):
    slot: int
    assessed_difficulty: Difficulty
    reason: str = ""


class DifficultyAssessment(BaseModel):
    verdicts: list[DifficultyVerdict]


class RubricCriterionDraft(BaseModel):
    criterion: str = Field(min_length=2)
    category: CriterionCategory
    max_marks: float = Field(gt=0)
    expected_evidence: str = Field(min_length=3)


class RubricDraft(BaseModel):
    criteria: list[RubricCriterionDraft] = Field(min_length=1)


class PaperQuestion(BaseModel):
    """The question contract from the product spec."""
    question_number: int
    question_text: str
    topic: str
    difficulty: Difficulty
    question_type: QuestionType
    marks: float
    expected_answer: str
    expected_concepts: list[str]
    rubric: list[RubricCriterionDraft]
    source_references: list[SourceReference] = Field(default_factory=list)


# ---- handwriting
class PageBlock(BaseModel):
    question_number: int | None = Field(None, description="Number the student wrote; null if none is visible")
    is_continuation: bool = Field(False, description="True when this text continues the previous page's answer")
    text: str = Field("", description="Exact transcription. Use [illegible] for unreadable words; never guess.")
    confidence: float = Field(ge=0, le=1)
    contains_diagram: bool = False
    contains_equation: bool = False
    diagram_description: str = ""
    region: str = Field("", description="Where on the page, e.g. 'top half'")
    illegible_segments: int = Field(0, ge=0)


class PageTranscription(BaseModel):
    rotation_needed: Literal[0, 90, 180, 270] = 0
    is_blank: bool = False
    written_page_number: int | None = None
    blocks: list[PageBlock] = Field(default_factory=list)


class PageReference(BaseModel):
    page_number: int
    region: str = ""


class ExtractedAnswerOut(BaseModel):
    question_number: int
    pages: list[int]
    recognized_text: str
    ocr_confidence: float = Field(ge=0, le=1)
    contains_diagram: bool
    contains_equation: bool
    page_references: list[PageReference]
    needs_human_verification: bool
    verification_reasons: list[str] = Field(default_factory=list)


class ExtractionOutput(BaseModel):
    submission_id: str
    answers: list[ExtractedAnswerOut]
    warnings: list[str] = Field(default_factory=list)
    page_failures: list[dict] = Field(default_factory=list)


# ---- evaluation
class QuestionUnderstanding(BaseModel):
    asks_for: str
    learning_outcomes: list[str] = Field(min_length=1)
    command_verb: str = ""


class IdentifiedConcepts(BaseModel):
    concepts: list[str] = Field(default_factory=list)
    misconceptions: list[str] = Field(default_factory=list)


class CoverageItem(BaseModel):
    concept: str
    status: Literal["covered", "partial", "missing"]
    evidence_quote: str = ""


class CoverageAssessment(BaseModel):
    items: list[CoverageItem]
    valid_alternatives: list[str] = Field(default_factory=list,
                                          description="Correct points outside the key that also answer the question")


class IncorrectStatement(BaseModel):
    quote: str
    issue: Literal["incorrect_fact", "contradiction", "unsupported_claim", "misused_term", "incorrect_equation", "invalid_reasoning"]
    explanation: str


class CorrectnessAssessment(BaseModel):
    incorrect_statements: list[IncorrectStatement] = Field(default_factory=list)


class RelevanceAssessment(BaseModel):
    answers_the_question: bool
    relevance: float = Field(ge=0, le=1)
    off_topic_portion: float = Field(0, ge=0, le=1)
    note: str = ""


class VisualAssessment(BaseModel):
    readable: bool
    diagram_findings: str = ""
    equation_findings: str = ""
    correctness: float = Field(ge=0, le=1)


class CriterionAward(BaseModel):
    criterion_id: str
    awarded_marks: float = Field(ge=0)
    reason: str = Field(min_length=3)
    evidence_quotes: list[str] = Field(default_factory=list)


class RubricScoring(BaseModel):
    awards: list[CriterionAward]


class StudentFeedback(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    overall_feedback: str
    suggested_improved_answer: str = ""


class CriterionResult(BaseModel):
    criterion_id: str
    criterion: str
    category: str
    max_marks: float
    awarded_marks: float
    reason: str


class EvaluationReport(BaseModel):
    question_number: int
    max_marks: float
    marks_awarded: float | None
    confidence: float
    criteria: list[CriterionResult]
    covered_points: list[str] = Field(default_factory=list)
    partially_covered_points: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    valid_alternative_points: list[str] = Field(default_factory=list)
    incorrect_statements: list[IncorrectStatement] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    overall_feedback: str = ""
    suggested_improved_answer: str = ""
    requires_human_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    evidence_references: list[dict] = Field(default_factory=list)
    trace: dict = Field(default_factory=dict)


# ---- challenge
class ArgumentAnalysis(BaseModel):
    claim_summary: str
    claim_type: Literal["marking_error", "alternative_answer", "rubric_defect", "ambiguous_question", "ocr_error", "diagram_misread", "no_valid_claim"]
    student_answer_supports_claim: bool


class AlternativeValidity(BaseModel):
    is_valid: bool
    supported_by_sources: bool
    reasoning: str
    uncertain: bool = False


class ChallengeRecommendation(BaseModel):
    recommendation: Literal["accept", "partially_accept", "reject", "escalate"]
    suggested_marks: float | None = Field(None, ge=0)
    reasoning: str = Field(min_length=10)
    confidence: float = Field(ge=0, le=1)
    rubric_change_suggested: str = ""
