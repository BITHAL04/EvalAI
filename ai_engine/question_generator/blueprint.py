"""Deterministic paper plan: the model fills slots, it does not decide marks."""
from __future__ import annotations

import math

from ai_engine.schemas import BlueprintSlot


class BlueprintError(ValueError):
    pass


def apportion(weights: dict[str, float], n: int) -> list[str]:
    """Largest-remainder allocation of n items by weight."""
    total = sum(weights.values())
    if total <= 0:
        raise BlueprintError("Difficulty distribution must have a positive total")
    exact = {k: v / total * n for k, v in weights.items()}
    counts = {k: math.floor(v) for k, v in exact.items()}
    for k in sorted(exact, key=lambda k: exact[k] - counts[k], reverse=True)[: n - sum(counts.values())]:
        counts[k] += 1
    return [k for k, c in counts.items() for _ in range(c)]


def build_blueprint(*, total_marks: float, mark_distribution: list[dict], difficulty: dict[str, float],
                    question_types: list[str], topics: list[str]) -> list[BlueprintSlot]:
    marks = [float(row["marks"]) for row in mark_distribution for _ in range(int(row["count"]))]
    if not marks:
        raise BlueprintError("Add at least one question to the mark distribution")
    if abs(sum(marks) - float(total_marks)) > 1e-6:
        raise BlueprintError(f"Mark distribution sums to {sum(marks):g} but total marks is {float(total_marks):g}")
    if not topics:
        raise BlueprintError("Select at least one topic")
    if not question_types:
        raise BlueprintError("Select at least one question type")
    marks.sort(reverse=True)
    # Hardest questions go to the highest marks, as in a conventional paper.
    levels = sorted(apportion(difficulty, len(marks)), key=["Hard", "Medium", "Easy"].index)
    return [BlueprintSlot(slot=i + 1, marks=m, difficulty=levels[i], question_type=question_types[i % len(question_types)],
                          topic=topics[i % len(topics)]) for i, m in enumerate(marks)]
