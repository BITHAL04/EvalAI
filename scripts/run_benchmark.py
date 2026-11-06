"""Measure the evaluation pipeline against benchmarks/evaluation_set.json with the configured model.

    cd apps/api && GEMINI_API_KEY=... GEMINI_MODEL=... GEMINI_EMBEDDING_MODEL=... python ../../scripts/run_benchmark.py

Reports mean absolute error, the share within 1 mark, and how uncertain answers were flagged.
Accuracy is only meaningful once a teacher has confirmed the expected marks (see the file's status).
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "apps" / "api")]

from ai_engine.evaluation.scoring import RubricItem  # noqa: E402
from ai_engine.workflows.evaluation import EvaluationInput, evaluate_answer  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.services.platform import get_ai  # noqa: E402


def main() -> None:
    data = json.loads((ROOT / "benchmarks" / "evaluation_set.json").read_text())
    s = get_settings()
    if s.gemini_base_url:
        print("WARNING: GEMINI_BASE_URL is set. If it points at the test double, these numbers mean nothing.\n")
    ai = get_ai()
    errors, rows = [], []
    for q in data["questions"]:
        rubric = [RubricItem(r["id"], r["criterion"], r["category"], r["max_marks"], r["expected_evidence"]) for r in q["rubric"]]
        for a in q["answers"]:
            illegible = "[illegible]" in a["text"]
            r = evaluate_answer(ai, EvaluationInput(question_number=1, question_text=q["question_text"], topic=q["topic"], difficulty=q["difficulty"], max_marks=q["max_marks"],
                                                    expected_answer=q["expected_answer"], expected_concepts=q["expected_concepts"], rubric=rubric, answer_text=a["text"],
                                                    ocr_confidence=0.5 if illegible else 0.97, ocr_flags=["Illegible segments"] if illegible else []))
            exp = a["expected_marks"]
            if exp is not None:
                errors.append(abs((r.marks_awarded or 0) - exp))
            rows.append((a["id"], a["kind"], exp, r.marks_awarded, r.confidence, r.requires_human_review))
            print(f"{a['id']:16} {a['kind']:26} expected {str(exp):>5}  got {str(r.marks_awarded):>5}  conf {r.confidence:.2f}  review {r.requires_human_review}")
    print(f"\nAnswers: {len(rows)}  MAE: {statistics.mean(errors):.2f}  within 1 mark: {sum(e <= 1 for e in errors) / len(errors):.0%}")
    print(f"Expected-mark status: {data['status']}")


if __name__ == "__main__":
    main()
