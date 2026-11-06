from __future__ import annotations

from ai_engine.agents.prompting import GUARD, untrusted
from ai_engine.providers.base import AIProvider
from ai_engine.schemas import BlueprintSlot, GeneratedQuestion, RubricCriterionDraft, RubricDraft

SYSTEM = f"""You are a senior examiner writing a marking rubric. Criteria must be independent, so no point can earn marks
twice. Expected evidence must describe what demonstrates understanding, not exact wording, so that equivalent valid
explanations score equally. Do not include criteria for handwriting, spelling or grammar. {GUARD}"""


def normalise(criteria: list[RubricCriterionDraft], total: float) -> tuple[list[RubricCriterionDraft], bool]:
    """Make criterion marks sum exactly to the question's marks, in 0.25 steps."""
    current = sum(c.max_marks for c in criteria)
    if abs(current - total) < 1e-6:
        return criteria, False
    scaled = [max(0.25, round(c.max_marks * total / current * 4) / 4) for c in criteria]
    scaled[scaled.index(max(scaled))] += total - sum(scaled)
    return [c.model_copy(update={"max_marks": m}) for c, m in zip(criteria, scaled)], True


def generate_rubric(provider: AIProvider, slot: BlueprintSlot, q: GeneratedQuestion) -> tuple[list[RubricCriterionDraft], str]:
    prompt = (f"Question ({slot.marks:g} marks, {slot.question_type}, {slot.difficulty}):\n{q.question_text}\n\n"
              f"Expected concepts: {'; '.join(q.expected_concepts)}\n\n"
              f"{untrusted('model_answer', q.expected_answer)}\n\n"
              f"Write 2-6 criteria whose max_marks sum to exactly {slot.marks:g}."
              + (" Include a 'diagram' category criterion." if slot.question_type == "diagram" else "")
              + (" Include a 'mathematical' category criterion." if slot.question_type == "derivation" else ""))
    res = provider.generate(system=SYSTEM, prompt=prompt, schema=RubricDraft, purpose="rubric_generation")
    criteria, _ = normalise(res.data.criteria, slot.marks)
    return criteria, res.model
