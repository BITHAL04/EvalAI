"""Exam-level checks that look across students for grading that does not line up."""
from __future__ import annotations

import statistics
from dataclasses import dataclass

BENCHMARK_TOLERANCE = 0.15  # of question max
SIMILAR_COSINE = 0.93
SIMILAR_GAP = 0.25


@dataclass
class GradedAnswer:
    evaluation_id: str
    question_id: str
    question_number: int
    fraction: float
    embedding: list[float] | None = None


def score_outliers(answers: list[GradedAnswer]) -> list[dict]:
    out = []
    byq: dict[str, list[GradedAnswer]] = {}
    for a in answers:
        byq.setdefault(a.question_id, []).append(a)
    for rows in byq.values():
        if len(rows) < 5:
            continue
        vals = [r.fraction for r in rows]
        sd = statistics.pstdev(vals)
        if sd < 0.05:
            continue
        mean = statistics.mean(vals)
        for r in rows:
            if abs(r.fraction - mean) / sd >= 2.5:
                out.append({"type": "outlier", "evaluation_id": r.evaluation_id, "question_number": r.question_number,
                            "detail": f"Score {r.fraction:.0%} is far from the class mean of {mean:.0%}"})
    return out


def similar_but_different(answers: list[GradedAnswer]) -> list[dict]:
    """Near-identical answers that received very different marks."""
    out = []
    rows = [a for a in answers if a.embedding]
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if a.question_id != b.question_id or abs(a.fraction - b.fraction) < SIMILAR_GAP:
                continue
            dot = sum(x * y for x, y in zip(a.embedding, b.embedding))
            norm = sum(x * x for x in a.embedding) ** .5 * sum(y * y for y in b.embedding) ** .5
            if norm and dot / norm >= SIMILAR_COSINE:
                out.append({"type": "similar_answers_diverge", "evaluation_id": a.evaluation_id, "other_evaluation_id": b.evaluation_id,
                            "question_number": a.question_number,
                            "detail": f"Very similar answers scored {a.fraction:.0%} and {b.fraction:.0%}"})
    return out


def benchmark_drift(rows: list[dict]) -> tuple[list[dict], dict]:
    """rows: {question_number, tier, expected, actual, max}. Detects systematic over- or under-grading."""
    if not rows:
        return [], {"benchmarks": 0, "mean_bias": None}
    bias = [(r["actual"] - r["expected"]) / r["max"] for r in rows]
    out = [{"type": "benchmark_miss", "question_number": r["question_number"],
            "detail": f"{r['tier']} benchmark expected {r['expected']:g}, AI gave {r['actual']:g}"}
           for r, b in zip(rows, bias) if abs(b) > BENCHMARK_TOLERANCE]
    mean = statistics.mean(bias)
    if abs(mean) > BENCHMARK_TOLERANCE / 2 and len(rows) >= 3:
        out.append({"type": "systematic_" + ("overgrading" if mean > 0 else "undergrading"), "question_number": None,
                    "detail": f"AI differs from benchmark marks by {mean:+.0%} of question marks on average"})
    return out, {"benchmarks": len(rows), "mean_bias": round(mean, 3)}
