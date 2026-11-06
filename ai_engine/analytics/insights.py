"""Topic analysis and recommendations, computed from recorded marks rather than generated."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

STRONG = 75.0
ADEQUATE = 50.0
EXPRESSION_CATEGORIES = {"organization", "explanation_depth"}
CONCEPT_CATEGORIES = {"conceptual_correctness", "coverage", "technical_accuracy", "logical_reasoning"}


def topic_status(score: float) -> str:
    return "Strong" if score >= STRONG else "Adequate" if score >= ADEQUATE else "Needs Improvement"


@dataclass
class QuestionOutcome:
    question_number: int
    topic: str
    marks: float
    max_marks: float
    missing: list[str]
    partial: list[str]
    incorrect: int
    criteria: list[dict]  # {category, awarded_marks, max_marks}


def topic_breakdown(outcomes: list[QuestionOutcome]) -> list[dict]:
    agg: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for o in outcomes:
        agg[o.topic][0] += o.marks
        agg[o.topic][1] += o.max_marks
    rows = [{"name": t, "marks": m, "max_marks": x, "score": round(m / x * 100, 1) if x else 0} for t, (m, x) in agg.items()]
    for r in rows:
        r["status"] = topic_status(r["score"])
    return sorted(rows, key=lambda r: r["score"], reverse=True)


def _rate(criteria: list[dict], cats: set[str]) -> float | None:
    rows = [c for c in criteria if c["category"] in cats]
    total = sum(c["max_marks"] for c in rows)
    return sum(c["awarded_marks"] for c in rows) / total if total else None


def weakness_type(o: QuestionOutcome) -> str | None:
    """Separate 'does not know it' from 'knows it but did not write it up well'."""
    concept, expression = _rate(o.criteria, CONCEPT_CATEGORIES), _rate(o.criteria, EXPRESSION_CATEGORIES)
    if concept is not None and concept < 0.6:
        return "conceptual"
    if expression is not None and expression < 0.6:
        return "explanation"
    return None


def recommendations(outcomes: list[QuestionOutcome], topics: list[dict]) -> dict:
    items: list[dict] = []
    for t in [t for t in topics if t["status"] == "Needs Improvement"]:
        qs = [o for o in outcomes if o.topic == t["name"]]
        concepts = list(dict.fromkeys(c for o in qs for c in o.missing + o.partial))[:5]
        kinds = {weakness_type(o) for o in qs}
        kind = "conceptual" if "conceptual" in kinds else "explanation" if "explanation" in kinds else "conceptual"
        text = (f"Revise {t['name']}" + (f", especially {', '.join(concepts)}." if concepts else ".")) if kind == "conceptual" \
            else f"You know {t['name']} but lost marks on how you explained it. Practise structured, step-by-step answers."
        items.append({"topic": t["name"], "type": kind, "text": text, "evidence_questions": [o.question_number for o in qs]})
    for cat, label in (("diagram", "Practise labelled diagrams"), ("mathematical", "Practise mathematical derivations step by step"),
                       ("examples", "Practise application-based questions with worked examples")):
        crit = [o for o in outcomes if (r := _rate(o.criteria, {cat})) is not None and r < 0.6]
        if crit:
            items.append({"topic": crit[0].topic, "type": "skill", "text": f"{label}.",
                          "evidence_questions": [o.question_number for o in crit]})
    return {"strengths": [t["name"] for t in topics if t["status"] == "Strong"],
            "weaknesses": [t["name"] for t in topics if t["status"] == "Needs Improvement"], "recommendations": items}
