"""Deterministic scoring rules. These never call a model, so they are fully testable."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from ai_engine.schemas import CriterionAward, CriterionResult


@dataclass
class RubricItem:
    id: str
    criterion: str
    category: str
    max_marks: float
    expected_evidence: str


@dataclass
class ValidationOutcome:
    results: list[CriterionResult]
    problems: list[str] = field(default_factory=list)


def to_quarter(x: float) -> float:
    return round(x * 4) / 4


def validate_awards(awards: list[CriterionAward], rubric: list[RubricItem], max_marks: float) -> ValidationOutcome:
    """Node 10. Reports every violation; the marks returned always respect the limits."""
    problems: list[str] = []
    by_id = {r.id: r for r in rubric}
    seen: dict[str, CriterionAward] = {}
    for a in awards:
        if a.criterion_id not in by_id:
            problems.append(f"Award for unknown criterion {a.criterion_id}")
        elif a.criterion_id in seen:
            problems.append(f"Criterion '{by_id[a.criterion_id].criterion}' scored twice")
        else:
            seen[a.criterion_id] = a
    results: list[CriterionResult] = []
    for r in rubric:
        a = seen.get(r.id)
        if a is None:
            problems.append(f"Criterion '{r.criterion}' was not scored")
            results.append(CriterionResult(criterion_id=r.id, criterion=r.criterion, category=r.category, max_marks=r.max_marks,
                                           awarded_marks=0, reason="Not scored by the model; needs teacher review."))
            continue
        awarded = a.awarded_marks
        if awarded > r.max_marks:
            problems.append(f"Criterion '{r.criterion}' awarded {awarded:g} of {r.max_marks:g}")
            awarded = r.max_marks
        awarded = min(to_quarter(awarded), r.max_marks)
        if awarded < r.max_marks and len(a.reason.strip()) < 15:
            problems.append(f"Deduction on '{r.criterion}' has no explanation")
        results.append(CriterionResult(criterion_id=r.id, criterion=r.criterion, category=r.category, max_marks=r.max_marks,
                                       awarded_marks=awarded, reason=a.reason))
    if sum(x.awarded_marks for x in results) > max_marks:
        problems.append("Total exceeds the question's maximum")
    return ValidationOutcome(results, problems)


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t.lower()).strip()


def quote_found(quote: str, answer: str, threshold: float = 0.8) -> bool:
    """Is this quote really in the answer? Tolerates small transcription differences."""
    q, a = _norm(quote), _norm(answer)
    if not q:
        return False
    if q in a:
        return True
    m = SequenceMatcher(None, q, a, autojunk=False).find_longest_match(0, len(q), 0, len(a))
    window = a[max(0, m.b - m.a): m.b - m.a + len(q) + 8]
    return SequenceMatcher(None, q, window, autojunk=False).ratio() >= threshold


def confidence_score(*, ocr: float, evidence_ratio: float, rubric_clarity: float, agreement: float) -> float:
    """Node 11. A review signal built from observable facts, not a claim of correctness."""
    return round(0.35 * ocr + 0.30 * evidence_ratio + 0.15 * rubric_clarity + 0.20 * agreement, 3)
