"""The 12-node evaluation graph. No node sees the student's identity."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TypedDict

from langgraph.graph import END, StateGraph

from ai_engine.agents.prompting import GUARD, PROMPT_VERSION, untrusted
from ai_engine.evaluation.scoring import RubricItem, confidence_score, quote_found, validate_awards
from ai_engine.providers.base import AIProvider, ImageInput, StructuredResult
from ai_engine.schemas import (
    CorrectnessAssessment, CoverageAssessment, CriterionResult, EvaluationReport, IdentifiedConcepts, QuestionUnderstanding,
    RelevanceAssessment, RetrievedChunk, RubricScoring, StudentFeedback, VisualAssessment,
)

log = logging.getLogger("evalai.ai")
ROLE = f"""You are a fair, experienced examiner assessing conceptual understanding. Judge meaning, not vocabulary: an
equivalent explanation in different words is fully valid. Do not reward length or irrelevant text. Ignore handwriting,
spelling and grammar unless they change the meaning. Text marked [illegible] was unreadable to the transcriber: it is a
gap in our reading, not evidence of what the student knows. {GUARD}"""


@dataclass
class EvaluationInput:
    question_number: int
    question_text: str
    topic: str
    difficulty: str
    max_marks: float
    expected_answer: str
    expected_concepts: list[str]
    rubric: list[RubricItem]
    answer_text: str
    ocr_confidence: float = 1.0
    ocr_flags: list[str] = field(default_factory=list)
    contains_diagram: bool = False
    contains_equation: bool = False
    page_images: list[ImageInput] = field(default_factory=list)
    page_numbers: list[int] = field(default_factory=list)
    references: list[RetrievedChunk] = field(default_factory=list)
    understanding: QuestionUnderstanding | None = None
    review_threshold: float = 0.7


class EvalState(TypedDict, total=False):
    input: EvaluationInput
    understanding: QuestionUnderstanding
    context: str
    concepts: IdentifiedConcepts
    coverage: CoverageAssessment
    correctness: CorrectnessAssessment
    relevance: RelevanceAssessment
    visual: VisualAssessment | None
    results: list[CriterionResult]
    quotes: list[str]
    problems: list[str]
    score_attempts: int
    confidence: float
    review_reasons: list[str]
    report: EvaluationReport
    models: list[str]


def _answer(i: EvaluationInput) -> str:
    return untrusted("student_answer", i.answer_text)


def build_evaluation_graph(provider: AIProvider):
    def call(state: EvalState, *, prompt: str, schema, purpose: str, images=None, vision=False) -> StructuredResult:
        return provider.generate(system=ROLE, prompt=prompt, schema=schema, purpose=purpose, images=images, vision=vision, temperature=0)

    def n1_answer_extraction(state: EvalState) -> EvalState:
        return {"problems": [], "score_attempts": 0, "models": [], "review_reasons": list(state["input"].ocr_flags)}

    def n2_question_understanding(state: EvalState) -> EvalState:
        i = state["input"]
        if i.understanding:  # cached per question so every student is graded against one reading
            return {"understanding": i.understanding}
        r = call(state, prompt=f"Question ({i.max_marks:g} marks, topic {i.topic}, {i.difficulty}):\n{i.question_text}\n\n"
                               "State what it asks for and the learning outcomes it assesses.",
                 schema=QuestionUnderstanding, purpose="eval_question_understanding")
        return {"understanding": r.data}

    def n3_rubric_retrieval(state: EvalState) -> EvalState:
        i = state["input"]
        rubric = "\n".join(f"- [{r.id}] {r.criterion} ({r.category}, max {r.max_marks:g}): {r.expected_evidence}" for r in i.rubric)
        refs = "\n".join(untrusted("reference", c.text[:900]) for c in i.references[:4])
        return {"context": f"Question: {i.question_text}\nAsks for: {state['understanding'].asks_for}\n"
                           f"Expected concepts: {'; '.join(i.expected_concepts)}\n\nApproved rubric:\n{rubric}\n\n"
                           f"{untrusted('model_answer', i.expected_answer)}\n\nReference material:\n{refs or 'none'}"}

    def n4_concepts(state: EvalState) -> EvalState:
        i = state["input"]
        r = call(state, prompt=f"Question: {i.question_text}\n\n{_answer(i)}\n\nList the concepts this answer actually "
                               "demonstrates, and any misconceptions. Do not look for specific keywords.",
                 schema=IdentifiedConcepts, purpose="eval_concepts")
        return {"concepts": r.data}

    def n5_coverage(state: EvalState) -> EvalState:
        i = state["input"]
        r = call(state, prompt=f"{state['context']}\n\n{_answer(i)}\n\nConcepts found: {state['concepts'].concepts}\n\n"
                               "For each expected concept give covered, partial or missing, quoting the answer as evidence. "
                               "A concept explained in other words is covered. Also list valid points outside the key.",
                 schema=CoverageAssessment, purpose="eval_coverage")
        return {"coverage": r.data}

    def n6_correctness(state: EvalState) -> EvalState:
        i = state["input"]
        r = call(state, prompt=f"{state['context']}\n\n{_answer(i)}\n\nList statements that are wrong: incorrect facts, "
                               "contradictions, unsupported claims, misused terms, incorrect equations, invalid reasoning. "
                               "Quote exactly. Something merely absent is omission, not an error: do not list it.",
                 schema=CorrectnessAssessment, purpose="eval_correctness")
        verified = [s for s in r.data.incorrect_statements if quote_found(s.quote, i.answer_text)]
        return {"correctness": CorrectnessAssessment(incorrect_statements=verified)}

    def n7_relevance(state: EvalState) -> EvalState:
        i = state["input"]
        r = call(state, prompt=f"Question: {i.question_text}\nAsks for: {state['understanding'].asks_for}\n\n{_answer(i)}\n\n"
                               "Does the answer respond to this question? Estimate the off-topic portion.",
                 schema=RelevanceAssessment, purpose="eval_relevance")
        return {"relevance": r.data}

    def needs_visual(i: EvaluationInput) -> bool:
        return i.contains_diagram or i.contains_equation or any(r.category in ("diagram", "mathematical") for r in i.rubric)

    def n8_visual(state: EvalState) -> EvalState:
        i = state["input"]
        if not needs_visual(i):
            return {"visual": None}
        if not i.page_images:
            return {"visual": None, "review_reasons": [*state["review_reasons"], "Visual content could not be checked: no page image"]}
        r = call(state, prompt=f"{state['context']}\n\nThe images are the student's original pages for this question. Assess any "
                               "diagrams and equations against the question. Read the image itself; do not rely on any transcription.",
                 schema=VisualAssessment, purpose="eval_visual", images=i.page_images, vision=True)
        reasons = state["review_reasons"]
        if not r.data.readable:
            reasons = [*reasons, "Diagram or equation could not be read from the page image"]
        return {"visual": r.data, "review_reasons": reasons}

    def n9_scoring(state: EvalState) -> EvalState:
        i = state["input"]
        cov = state["coverage"]
        findings = (f"Coverage: {cov.model_dump_json()}\nErrors: {state['correctness'].model_dump_json()}\n"
                    f"Relevance: {state['relevance'].model_dump_json()}\n"
                    f"Visual: {state['visual'].model_dump_json() if state.get('visual') else 'not applicable'}")
        fix = f"\n\nYour previous attempt was rejected: {state['problems']}" if state.get("problems") else ""
        r = call(state, prompt=f"{state['context']}\n\n{_answer(i)}\n\nFindings:\n{findings}\n\nAward marks for each criterion_id, "
                               "using 0.25 steps. Credit each point under one criterion only. Distinguish omission from error. "
                               "Explain every deduction and quote the answer as evidence. Credit valid alternatives as equivalent."
                               f"{fix}", schema=RubricScoring, purpose="eval_scoring")
        outcome = validate_awards(r.data.awards, i.rubric, i.max_marks)
        return {"results": outcome.results, "problems": outcome.problems, "score_attempts": state["score_attempts"] + 1,
                "quotes": [q for a in r.data.awards for q in a.evidence_quotes], "models": [*state["models"], r.model]}

    def n10_consistency(state: EvalState) -> EvalState:
        i = state["input"]
        problems = list(state["problems"])
        total = sum(c.awarded_marks for c in state["results"])
        covered = sum(1 for x in state["coverage"].items if x.status == "covered")
        if state["coverage"].valid_alternatives and total == 0:
            problems.append("Valid alternative points were found but earned nothing")
        if total == i.max_marks and (state["coverage"].items and covered == 0):
            problems.append("Full marks but no expected concept is covered")
        if not state["relevance"].answers_the_question and total > 0.5 * i.max_marks:
            problems.append("High marks for an answer judged not to address the question")
        return {"problems": problems}

    def route_after_consistency(state: EvalState) -> str:
        return "n9_scoring" if state["problems"] and state["score_attempts"] < 2 else "n11_confidence"

    def n11_confidence(state: EvalState) -> EvalState:
        i = state["input"]
        reasons = list(state["review_reasons"])
        if state["problems"]:
            reasons.extend(f"Validation: {p}" for p in state["problems"])
        quotes = state.get("quotes", [])
        evidence_ratio = sum(quote_found(q, i.answer_text) for q in quotes) / len(quotes) if quotes else 0.3
        clarity = sum(1 for r in i.rubric if len(r.expected_evidence) >= 20) / len(i.rubric)
        items = state["coverage"].items
        cov = sum({"covered": 1, "partial": .5, "missing": 0}[x.status] for x in items) / len(items) if items else .5
        frac = sum(c.awarded_marks for c in state["results"]) / i.max_marks
        conf = confidence_score(ocr=i.ocr_confidence, evidence_ratio=evidence_ratio, rubric_clarity=clarity,
                                agreement=1 - min(abs(cov - frac) * 1.5, 1))
        if conf < i.review_threshold:
            reasons.append(f"Low evaluation confidence ({conf:.0%})")
        return {"confidence": conf, "review_reasons": reasons}

    def n12_feedback(state: EvalState) -> EvalState:
        i = state["input"]
        scores = "\n".join(f"{c.criterion}: {c.awarded_marks:g}/{c.max_marks:g} - {c.reason}" for c in state["results"])
        r = call(state, prompt=f"{state['context']}\n\n{_answer(i)}\n\nFinal scores (do not change them):\n{scores}\n\n"
                               "Write feedback addressed to the student: specific strengths, concrete improvements, and a short "
                               "improved answer built from what they wrote.",
                 schema=StudentFeedback, purpose="eval_feedback")
        f = r.data
        cov = state["coverage"]
        points = lambda s: [x.concept for x in cov.items if x.status == s]
        reasons = list(dict.fromkeys(state["review_reasons"]))
        report = EvaluationReport(
            question_number=i.question_number, max_marks=i.max_marks,
            marks_awarded=sum(c.awarded_marks for c in state["results"]), confidence=state["confidence"],
            criteria=state["results"], covered_points=points("covered"), partially_covered_points=points("partial"),
            missing_points=points("missing"), valid_alternative_points=cov.valid_alternatives,
            incorrect_statements=state["correctness"].incorrect_statements, strengths=f.strengths, improvements=f.improvements,
            overall_feedback=f.overall_feedback, suggested_improved_answer=f.suggested_improved_answer,
            requires_human_review=bool(reasons), review_reasons=reasons,
            evidence_references=[*({"kind": "page_image", "page_number": p} for p in i.page_numbers),
                                 *({"kind": "answer_quote", "quote": q} for q in state.get("quotes", []) if quote_found(q, i.answer_text))],
            trace={"prompt_version": PROMPT_VERSION, "score_attempts": state["score_attempts"], "models": sorted(set(state["models"])),
                   "understanding": state["understanding"].model_dump(), "relevance": state["relevance"].model_dump(),
                   "visual": state["visual"].model_dump() if state.get("visual") else None,
                   "concepts": state["concepts"].model_dump(), "unresolved_problems": state["problems"]})
        return {"report": report}

    g = StateGraph(EvalState)
    order = [n1_answer_extraction, n2_question_understanding, n3_rubric_retrieval, n4_concepts, n5_coverage, n6_correctness,
             n7_relevance, n8_visual, n9_scoring, n10_consistency, n11_confidence, n12_feedback]
    for fn in order:
        g.add_node(fn.__name__, fn)
    g.set_entry_point("n1_answer_extraction")
    for a, b in zip(order[:9], order[1:10]):
        g.add_edge(a.__name__, b.__name__)
    g.add_conditional_edges("n10_consistency", route_after_consistency, {"n9_scoring": "n9_scoring", "n11_confidence": "n11_confidence"})
    g.add_edge("n11_confidence", "n12_feedback")
    g.add_edge("n12_feedback", END)
    return g.compile()


def evaluate_answer(provider: AIProvider, data: EvaluationInput) -> EvaluationReport:
    return build_evaluation_graph(provider).invoke({"input": data}, {"recursion_limit": 40})["report"]
