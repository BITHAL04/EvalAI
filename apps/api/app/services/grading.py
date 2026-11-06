"""Evaluation persistence. AI output is stored as provisional; only a teacher action can finalise it."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_engine.analytics.consistency import GradedAnswer, benchmark_drift, score_outliers, similar_but_different
from ai_engine.analytics.insights import QuestionOutcome, recommendations, topic_breakdown
from ai_engine.evaluation.scoring import RubricItem
from ai_engine.providers.base import ImageInput
from ai_engine.schemas import EvaluationReport, QuestionUnderstanding
from ai_engine.workflows.evaluation import EvaluationInput, evaluate_answer
from app.core.config import get_settings
from app.core.storage import get_storage
from app.models import (
    BenchmarkAnswer, ConsistencyReport, CriterionScore, Evaluation, EvaluationEvidence, EvaluationStatus, EvaluationVersion,
    Examination, ExaminationQuestion, ExtractedAnswer, Result, Rubric, StudentPerformanceSnapshot, Submission, SubmissionStatus,
    TopicPerformance,
)
from app.services.exams import approved_rubric
from app.services.platform import audit, enqueue, get_ai, notify, notify_staff
from app.services.retrieval import retriever_for

D = lambda x: Decimal(str(x)).quantize(Decimal("0.01"))  # noqa: E731
MAX_VISUAL_PAGES = 4


def snapshot(e: Evaluation) -> dict:
    return {"marks_awarded": float(e.marks_awarded) if e.marks_awarded is not None else None, "status": e.status, "report": e.report,
            "criteria": [{"criterion_id": str(c.rubric_criterion_id), "criterion": c.criterion, "max_marks": float(c.max_marks),
                          "awarded_marks": float(c.awarded_marks), "reason": c.reason} for c in e.criterion_scores]}


def record_version(db: Session, e: Evaluation, actor_type: str, actor_id: UUID | None, reason: str) -> None:
    db.flush()
    db.add(EvaluationVersion(institution_id=e.institution_id, evaluation_id=e.id, version=e.version, rubric_id=e.rubric_id,
                             marks_awarded=e.marks_awarded, snapshot=snapshot(e), actor_type=actor_type, actor_id=actor_id, reason=reason, model=e.model))


def _store_report(db: Session, e: Evaluation, report: EvaluationReport) -> None:
    e.marks_awarded = None if report.marks_awarded is None else D(report.marks_awarded)
    e.confidence, e.requires_human_review, e.review_reasons = report.confidence, report.requires_human_review, report.review_reasons
    e.report = report.model_dump(exclude={"criteria"})
    e.status = EvaluationStatus.needs_review.value if report.requires_human_review or report.marks_awarded is None else EvaluationStatus.provisional.value
    e.criterion_scores.clear()
    e.evidence.clear()
    db.flush()
    for c in report.criteria:
        e.criterion_scores.append(CriterionScore(institution_id=e.institution_id, rubric_criterion_id=UUID(c.criterion_id), criterion=c.criterion,
                                                 category=c.category, max_marks=D(c.max_marks), awarded_marks=D(c.awarded_marks), reason=c.reason))
    for ref in report.evidence_references:
        e.evidence.append(EvaluationEvidence(institution_id=e.institution_id, kind=ref["kind"], page_number=ref.get("page_number"), quote=ref.get("quote", "")))


def _empty_report(q: ExaminationQuestion, rubric: Rubric, *, reasons: list[str], marks: float | None, feedback: str) -> EvaluationReport:
    from ai_engine.schemas import CriterionResult
    crit = [CriterionResult(criterion_id=str(c.id), criterion=c.criterion, category=c.category, max_marks=float(c.max_marks), awarded_marks=0, reason=feedback)
            for c in rubric.criteria] if marks is not None else []
    return EvaluationReport(question_number=q.question_number, max_marks=float(q.marks), marks_awarded=marks, confidence=0, criteria=crit,
                            missing_points=q.expected_concepts if marks is not None else [], overall_feedback=feedback,
                            requires_human_review=bool(reasons), review_reasons=reasons)


def _build_input(db: Session, sub: Submission, q: ExaminationQuestion, rubric: Rubric, a: ExtractedAnswer) -> EvaluationInput:
    s = get_settings()
    storage = get_storage()
    pages = sorted({r.page_number for r in a.page_references})
    paths = sub.files[0].page_image_paths
    images = [ImageInput(storage.read(paths[p - 1]), "image/jpeg", f"Original page {p}") for p in pages[:MAX_VISUAL_PAGES] if p <= len(paths)]
    query = q.question_text
    exam = sub.examination
    materials = [UUID(m) for m in exam.config.get("material_ids", [])]
    refs = []
    if a.best_text.strip():
        from llama_index.core.schema import QueryBundle  # noqa: F401
        from ai_engine.retrieval.retriever import retrieve_many
        refs = retrieve_many(retriever_for(db, sub.institution_id, exam.subject_id, materials, top_k=4), [query], limit=4).chunks
    return EvaluationInput(
        question_number=q.question_number, question_text=q.question_text, topic=q.topic, difficulty=q.difficulty, max_marks=float(q.marks),
        expected_answer=rubric.expected_answer, expected_concepts=rubric.expected_concepts,
        rubric=[RubricItem(str(c.id), c.criterion, c.category, float(c.max_marks), c.expected_evidence) for c in rubric.criteria],
        answer_text=a.best_text, ocr_confidence=1.0 if a.corrected_text is not None else a.ocr_confidence,
        ocr_flags=[] if a.corrected_text is not None else list(a.verification_reasons), contains_diagram=a.contains_diagram,
        contains_equation=a.contains_equation, page_images=images, page_numbers=pages, references=refs,
        understanding=QuestionUnderstanding(**q.understanding) if q.understanding else None, review_threshold=s.evaluation_review_threshold)


def evaluate_submission(db: Session, submission_id: UUID, *, force: bool = False) -> dict:
    sub = db.get(Submission, submission_id)
    if sub is None or not sub.is_current:
        return {"skipped": "superseded"}
    sub.status = SubmissionStatus.evaluating.value
    db.commit()
    ai = get_ai()
    questions = db.scalars(select(ExaminationQuestion).where(ExaminationQuestion.examination_id == sub.examination_id).order_by(ExaminationQuestion.question_number)).all()
    answers = {a.question_number: a for a in db.scalars(select(ExtractedAnswer).where(ExtractedAnswer.submission_id == sub.id))}
    failures = bool(sub_failed_pages(db, sub))
    done = flagged = 0
    for q in questions:
        rubric = approved_rubric(q)
        if rubric is None:
            continue  # cannot happen for a published exam; never grade without an approved rubric
        e = db.scalar(select(Evaluation).where(Evaluation.submission_id == sub.id, Evaluation.question_id == q.id))
        if e and not force:  # job retry: keep finished work
            done += 1
            continue
        if e and e.status == EvaluationStatus.approved.value:
            continue  # approved marks only change through a teacher action
        a = answers.get(q.question_number)
        if a is None:
            if failures:
                report = _empty_report(q, rubric, marks=None, reasons=["Pages failed to process, so this answer may exist but was not read"],
                                       feedback="This answer could not be read and needs manual marking.")
            else:
                report = _empty_report(q, rubric, marks=0.0, reasons=["No answer detected; confirm against the original pages"],
                                       feedback="No answer to this question was found in the booklet.")
            model = None
        else:
            data = _build_input(db, sub, q, rubric, a)
            report = evaluate_answer(ai, data)
            model = ",".join(report.trace.get("models", [])) or None
            if q.understanding is None and report.trace.get("understanding"):
                q.understanding = report.trace["understanding"]
        if e is None:
            e = Evaluation(institution_id=sub.institution_id, submission_id=sub.id, question_id=q.id, rubric_id=rubric.id,
                           extracted_answer_id=a.id if a else None, max_marks=q.marks, version=1, model=model)
            db.add(e)
            db.flush()
        else:
            e.version += 1
            e.rubric_id, e.model, e.extracted_answer_id = rubric.id, model, a.id if a else None
        _store_report(db, e, report)
        record_version(db, e, "ai", None, "AI evaluation")
        db.commit()  # each question is durable, so a crash resumes rather than restarts
        done += 1
        flagged += e.requires_human_review
    sub.status = SubmissionStatus.evaluated.value
    audit(db, "submission.evaluated", "submission", sub.id, institution_id=sub.institution_id, actor_type="ai", after={"questions": done, "flagged": flagged})
    notify_staff(db, sub.institution_id, "evaluation_completed", "Evaluation complete",
                 f"{sub.examination.title}: {done} answers, {flagged} flagged for review.", f"/teacher/submissions/{sub.id}")
    enqueue(db, "consistency_check", {"examination_id": str(sub.examination_id)}, f"consistency:{sub.examination_id}:{datetime.now(UTC):%Y%m%d%H%M}", sub.institution_id)
    db.commit()
    return {"evaluated": done, "flagged": flagged}


def sub_failed_pages(db: Session, sub: Submission) -> list[dict]:
    from app.models import ExtractionJob
    j = db.scalar(select(ExtractionJob).where(ExtractionJob.submission_id == sub.id).order_by(ExtractionJob.created_at.desc()).limit(1))
    return j.page_failures if j else []


def run_benchmarks(db: Session, examination_id: UUID) -> dict:
    """Grade the teacher's reference answers with the same graph and compare."""
    ai = get_ai()
    exam = db.get(Examination, examination_id)
    count = 0
    for q in exam.questions:
        rubric = approved_rubric(q)
        for b in db.scalars(select(BenchmarkAnswer).where(BenchmarkAnswer.question_id == q.id)):
            data = EvaluationInput(question_number=q.question_number, question_text=q.question_text, topic=q.topic, difficulty=q.difficulty,
                                   max_marks=float(q.marks), expected_answer=rubric.expected_answer, expected_concepts=rubric.expected_concepts,
                                   rubric=[RubricItem(str(c.id), c.criterion, c.category, float(c.max_marks), c.expected_evidence) for c in rubric.criteria],
                                   answer_text=b.answer_text, understanding=QuestionUnderstanding(**q.understanding) if q.understanding else None)
            report = evaluate_answer(ai, data)
            b.last_ai_marks, b.last_run_at = D(report.marks_awarded or 0), datetime.now(UTC)
            db.commit()
            count += 1
    consistency_check(db, examination_id)
    return {"benchmarks": count}


def consistency_check(db: Session, examination_id: UUID) -> dict:
    rows = db.execute(select(Evaluation, ExaminationQuestion, ExtractedAnswer.recognized_text).join(ExaminationQuestion, Evaluation.question_id == ExaminationQuestion.id)
                      .outerjoin(ExtractedAnswer, Evaluation.extracted_answer_id == ExtractedAnswer.id)
                      .join(Submission, Evaluation.submission_id == Submission.id)
                      .where(ExaminationQuestion.examination_id == examination_id, Submission.is_current.is_(True), Evaluation.marks_awarded.is_not(None))).all()
    institution = db.get(Examination, examination_id).institution_id
    graded = [GradedAnswer(str(e.id), str(q.id), q.question_number, float(e.marks_awarded) / float(e.max_marks)) for e, q, _ in rows]
    texts = [t or "" for *_, t in rows]
    if 2 <= len(graded) and any(texts):
        try:
            for g, v in zip(graded, get_ai().embed([t[:4000] or " " for t in texts], task="document")):
                g.embedding = v
        except Exception:  # noqa: BLE001 - similarity is an extra signal; outlier checks still run
            pass
    benches = db.execute(select(BenchmarkAnswer, ExaminationQuestion).join(ExaminationQuestion, BenchmarkAnswer.question_id == ExaminationQuestion.id)
                         .where(ExaminationQuestion.examination_id == examination_id, BenchmarkAnswer.last_ai_marks.is_not(None))).all()
    drift, summary = benchmark_drift([{"question_number": q.question_number, "tier": b.tier, "expected": float(b.expected_marks),
                                       "actual": float(b.last_ai_marks), "max": float(q.marks)} for b, q in benches])
    findings = score_outliers(graded) + similar_but_different(graded) + drift
    db.add(ConsistencyReport(institution_id=institution, examination_id=examination_id, findings=findings, summary={**summary, "answers": len(graded)}))
    db.commit()
    return {"findings": len(findings)}


def outcomes_for(db: Session, submission_id: UUID) -> list[QuestionOutcome]:
    rows = db.execute(select(Evaluation, ExaminationQuestion).join(ExaminationQuestion, Evaluation.question_id == ExaminationQuestion.id)
                      .where(Evaluation.submission_id == submission_id).order_by(ExaminationQuestion.question_number)).all()
    return [QuestionOutcome(q.question_number, q.topic, float(e.marks_awarded or 0), float(e.max_marks), e.report.get("missing_points", []),
                            e.report.get("partially_covered_points", []), len(e.report.get("incorrect_statements", [])),
                            [{"category": c.category, "awarded_marks": float(c.awarded_marks), "max_marks": float(c.max_marks)} for c in e.criterion_scores])
            for e, q in rows]


def refresh_result(db: Session, sub: Submission, *, publisher: UUID | None = None) -> Result:
    """Recompute a result and everything derived from it from the evaluations."""
    outcomes = outcomes_for(db, sub.id)
    total, maximum = sum(o.marks for o in outcomes), sum(o.max_marks for o in outcomes)
    topics = topic_breakdown(outcomes)
    r = db.scalar(select(Result).where(Result.submission_id == sub.id))
    if r is None:
        r = Result(institution_id=sub.institution_id, submission_id=sub.id, examination_id=sub.examination_id, student_id=sub.student_id,
                   total_marks=0, max_marks=0, percentage=0, status="approved", is_demo=sub.is_demo)
        db.add(r)
    r.total_marks, r.max_marks, r.percentage = D(total), D(maximum), round(total / maximum * 100, 2) if maximum else 0
    r.insights = recommendations(outcomes, topics)
    db.flush()
    db.query(TopicPerformance).filter(TopicPerformance.result_id == r.id).delete()
    for t in topics:
        db.add(TopicPerformance(institution_id=sub.institution_id, result_id=r.id, student_id=sub.student_id, examination_id=sub.examination_id,
                                subject_id=sub.examination.subject_id, topic=t["name"], marks=D(t["marks"]), max_marks=D(t["max_marks"]), score=t["score"], status=t["status"]))
    if r.status == "published":
        _snapshot(db, sub, r)
    db.flush()
    return r


def _snapshot(db: Session, sub: Submission, r: Result) -> None:
    s = db.scalar(select(StudentPerformanceSnapshot).where(StudentPerformanceSnapshot.student_id == sub.student_id, StudentPerformanceSnapshot.examination_id == sub.examination_id))
    if s:
        s.percentage = r.percentage
    else:
        db.add(StudentPerformanceSnapshot(institution_id=sub.institution_id, student_id=sub.student_id, examination_id=sub.examination_id,
                                          subject_id=sub.examination.subject_id, percentage=r.percentage, taken_at=r.published_at or datetime.now(UTC)))


def publish_results(db: Session, exam: Examination, user_id: UUID) -> int:
    rows = db.scalars(select(Result).where(Result.examination_id == exam.id, Result.status == "approved")).all()
    now = datetime.now(UTC)
    for r in rows:
        r.status, r.published_at, r.published_by = "published", now, user_id
        sub = db.get(Submission, r.submission_id)
        _snapshot(db, sub, r)
        notify(db, r.student_id, "result_published", "Result published", exam.title, f"/student/results/{exam.id}", exam.institution_id)
    return len(rows)
