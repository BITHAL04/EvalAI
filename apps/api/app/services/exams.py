from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_engine.question_generator.blueprint import build_blueprint
from ai_engine.question_generator.paper_pdf import PaperData, render_paper
from ai_engine.schemas import BlueprintSlot, PaperQuestion
from ai_engine.workflows.paper_generation import build_paper_graph
from app.core.storage import get_storage
from app.models import (
    ExamStatus, Examination, ExaminationQuestion, ExaminationTopic, Institution, Rubric, RubricCriterion,
)
from app.services.platform import audit, get_ai, notify
from app.services.retrieval import retriever_for


def latest_rubric(q: ExaminationQuestion) -> Rubric | None:
    return q.rubrics[-1] if q.rubrics else None


def approved_rubric(q: ExaminationQuestion) -> Rubric | None:
    return next((r for r in reversed(q.rubrics) if r.status == "approved"), None)


def add_rubric(db: Session, q: ExaminationQuestion, criteria: list[dict], *, version: int = 1, status: str = "draft", reason: str | None = None) -> Rubric:
    r = Rubric(question=q, institution_id=q.institution_id, version=version, status=status, expected_answer=q.expected_answer,
               expected_concepts=q.expected_concepts, change_reason=reason)
    for i, c in enumerate(criteria, start=1):
        r.criteria.append(RubricCriterion(institution_id=q.institution_id, position=i, criterion=c["criterion"], category=c.get("category", "conceptual_correctness"),
                                          max_marks=c["max_marks"], expected_evidence=c.get("expected_evidence", "")))
    db.add(r)
    return r


def _persist(db: Session, exam: Examination, pq: PaperQuestion, origin: str = "ai") -> ExaminationQuestion:
    q = ExaminationQuestion(institution_id=exam.institution_id, examination_id=exam.id, question_number=pq.question_number,
                            question_text=pq.question_text, topic=pq.topic, difficulty=pq.difficulty, question_type=pq.question_type,
                            marks=pq.marks, expected_answer=pq.expected_answer, expected_concepts=pq.expected_concepts,
                            source_references=[r.model_dump() for r in pq.source_references], origin=origin)
    db.add(q)
    db.flush()
    add_rubric(db, q, [c.model_dump() for c in pq.rubric])
    return q


def _slots(exam: Examination) -> list[BlueprintSlot]:
    c = exam.config
    return build_blueprint(total_marks=float(exam.total_marks), mark_distribution=c["mark_distribution"], difficulty=c["difficulty"],
                           question_types=c["question_types"], topics=c["topics"])


def generate_exam(db: Session, exam_id: UUID) -> dict:
    exam = db.get(Examination, exam_id)
    if exam is None or exam.status != ExamStatus.generating.value:
        return {"skipped": "not generating"}
    materials = [UUID(m) for m in exam.config.get("material_ids", [])]
    graph = build_paper_graph(get_ai(), retriever_for(db, exam.institution_id, exam.subject_id, materials))
    state = graph.invoke({"slots": _slots(exam), "existing_questions": [], "instructions": exam.config.get("generation_notes", "")}, {"recursion_limit": 30})
    for q in list(exam.questions):
        db.delete(q)
    db.flush()
    for pq in state["questions"]:
        _persist(db, exam, pq)
    exam.status, exam.generation_error = ExamStatus.review.value, None
    exam.config = {**exam.config, "generation": {"warnings": state.get("warnings", []), "models": sorted(set(state.get("models", [])))}}
    audit(db, "exam.generated", "examination", exam.id, institution_id=exam.institution_id, actor_type="ai", after={"questions": len(state["questions"])})
    if exam.created_by:
        notify(db, exam.created_by, "exam_generated", "Paper ready for review", exam.title, f"/teacher/exams/{exam.id}", exam.institution_id)
    db.commit()
    return {"questions": len(state["questions"])}


def regenerate_question(db: Session, question_id: UUID) -> dict:
    q = db.get(ExaminationQuestion, question_id)
    if q is None:
        return {"skipped": "deleted"}
    exam = db.get(Examination, q.examination_id)
    if exam.status not in (ExamStatus.review.value, ExamStatus.draft.value):
        return {"skipped": "paper already published"}
    others = [o.question_text for o in exam.questions if o.id != q.id]
    slot = BlueprintSlot(slot=1, marks=float(q.marks), difficulty=q.difficulty, question_type=q.question_type, topic=q.topic)
    materials = [UUID(m) for m in exam.config.get("material_ids", [])]
    graph = build_paper_graph(get_ai(), retriever_for(db, exam.institution_id, exam.subject_id, materials))
    new = graph.invoke({"slots": [slot], "existing_questions": [*others, q.question_text], "instructions": ""}, {"recursion_limit": 30})["questions"][0]
    q.question_text, q.topic, q.difficulty, q.expected_answer, q.expected_concepts = new.question_text, new.topic, new.difficulty, new.expected_answer, new.expected_concepts
    q.source_references, q.origin, q.understanding = [r.model_dump() for r in new.source_references], "ai", None
    for r in list(q.rubrics):
        db.delete(r)
    q.rubrics.clear()
    db.flush()
    add_rubric(db, q, [c.model_dump() for c in new.rubric])
    audit(db, "question.regenerated", "examination_question", q.id, institution_id=q.institution_id, actor_type="ai")
    db.commit()
    return {"question_id": str(q.id)}


def render_exam_pdf(db: Session, exam: Examination) -> str:
    inst = db.get(Institution, exam.institution_id)
    pdf = render_paper(PaperData(institution=inst.name, title=exam.title, subject=exam.subject.name, duration_minutes=exam.duration_minutes,
                                 max_marks=float(exam.total_marks), instructions=exam.instructions,
                                 questions=[(q.question_number, q.question_text, float(q.marks)) for q in exam.questions]))
    path = f"{exam.institution_id}/papers/{exam.id}.pdf"
    get_storage().write(path, pdf, "application/pdf")
    exam.paper_storage_path = path
    return path


def sync_topics(db: Session, exam: Examination) -> None:
    have = {t.name: t for t in db.scalars(select(ExaminationTopic).where(ExaminationTopic.examination_id == exam.id))}
    wanted = {q.topic for q in exam.questions}
    for name, t in have.items():
        if name not in wanted:
            db.delete(t)
    for name in wanted - set(have):
        db.add(ExaminationTopic(institution_id=exam.institution_id, examination_id=exam.id, name=name))


def publish_exam(db: Session, exam: Examination, user_id: UUID) -> None:
    now = datetime.now(UTC)
    for q in exam.questions:
        r = latest_rubric(q)
        r.status, r.approved_by, r.approved_at, r.expected_answer, r.expected_concepts = "approved", user_id, now, q.expected_answer, q.expected_concepts
    sync_topics(db, exam)
    render_exam_pdf(db, exam)
    exam.status, exam.published_at, exam.published_by = ExamStatus.published.value, now, user_id
