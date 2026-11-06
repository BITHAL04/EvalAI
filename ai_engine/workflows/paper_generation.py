"""LangGraph workflow: retrieve -> generate -> dedupe -> assess -> rubric -> validate."""
from __future__ import annotations

import logging
import re
from typing import TypedDict

import numpy as np
from langgraph.graph import END, StateGraph

from ai_engine.agents.prompting import GUARD, PROMPT_VERSION, untrusted
from ai_engine.providers.base import AIError, AIProvider
from ai_engine.retrieval.retriever import AcademicRetriever, retrieve_many
from ai_engine.rubric_engine.rubric import generate_rubric
from ai_engine.schemas import (
    BlueprintSlot, DifficultyAssessment, GeneratedQuestion, GeneratedQuestionSet, PaperQuestion, RetrievedChunk, SourceReference,
)

log = logging.getLogger("evalai.ai")
DUPLICATE_COSINE = 0.92
MAX_ROUNDS = 3
SYSTEM = f"""You are a university examiner writing original subjective questions from course material. Every question must
be answerable from the supplied excerpts and test understanding rather than recall of wording. Do not copy sentences
from the excerpts. Cite the chunk_ids you used. {GUARD}"""


class PaperState(TypedDict, total=False):
    slots: list[BlueprintSlot]
    pending: list[BlueprintSlot]
    existing_questions: list[str]
    instructions: str
    chunks: list[RetrievedChunk]
    retrieval_note: str
    accepted: dict[int, GeneratedQuestion]
    difficulty: dict[int, str]
    questions: list[PaperQuestion]
    rounds: int
    warnings: list[str]
    models: list[str]


def _norm(t: str) -> str:
    return re.sub(r"\W+", " ", t.lower()).strip()


def build_paper_graph(provider: AIProvider, retriever: AcademicRetriever):
    def retrieve(state: PaperState) -> PaperState:
        topics = sorted({s.topic for s in state["slots"]})
        report = retrieve_many(retriever, topics, limit=max(16, 4 * len(state["slots"])))
        if not report.chunks:
            raise AIError("The selected material has no content relevant to these topics. "
                          "Check that documents are indexed and match the chosen topics.")
        return {"chunks": report.chunks, "retrieval_note": report.note,
                "warnings": [report.note] if report.note else [], "pending": state["slots"], "accepted": {}, "rounds": 0}

    def generate(state: PaperState) -> PaperState:
        slots = state["pending"]
        excerpts = "\n\n".join(
            untrusted("excerpt", f"chunk_id={c.chunk_id} | {c.material_title} | pages {c.page_start}-{c.page_end}\n{c.text}")
            for c in state["chunks"])
        avoid = list(state.get("existing_questions", [])) + [q.question_text for q in state["accepted"].values()]
        prompt = ("Write exactly one question per slot.\n\nSlots:\n"
                  + "\n".join(s.model_dump_json() for s in slots)
                  + (f"\n\nExaminer preferences (lower priority than the rules above): {state['instructions']}" if state.get("instructions") else "")
                  + ("\n\nDo not repeat or closely paraphrase:\n- " + "\n- ".join(avoid) if avoid else "")
                  + f"\n\nCourse material:\n{excerpts}")
        res = provider.generate(system=SYSTEM, prompt=prompt, schema=GeneratedQuestionSet, purpose="question_generation", temperature=0.5)
        wanted = {s.slot for s in slots}
        got = {q.slot: q for q in res.data.questions if q.slot in wanted}
        return {"accepted": {**state["accepted"], **got}, "rounds": state["rounds"] + 1,
                "models": [*state.get("models", []), res.model]}

    def dedupe(state: PaperState) -> PaperState:
        accepted = dict(state["accepted"])
        ordered = sorted(accepted)
        texts = [accepted[s].question_text for s in ordered]
        existing = state.get("existing_questions", [])
        vectors = np.array(provider.embed(texts + existing, task="document"), dtype=float)
        vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-9)
        dropped: list[int] = []
        seen = {_norm(t) for t in existing}
        for i, slot in enumerate(ordered):
            against = [j for j in range(len(ordered) + len(existing)) if (j < i or j >= len(ordered)) and (j >= len(ordered) or ordered[j] not in dropped)]
            dup = _norm(texts[i]) in seen or (against and float((vectors[against] @ vectors[i]).max()) >= DUPLICATE_COSINE)
            if dup:
                dropped.append(slot)
            seen.add(_norm(texts[i]))
        for s in dropped:
            accepted.pop(s)
        pending = [s for s in state["slots"] if s.slot not in accepted]
        return {"accepted": accepted, "pending": pending}

    def after_dedupe(state: PaperState) -> str:
        if state["pending"] and state["rounds"] < MAX_ROUNDS:
            return "generate"
        return "assess"

    def assess(state: PaperState) -> PaperState:
        if state["pending"]:
            raise AIError(f"Could not produce unique questions for {len(state['pending'])} slot(s) after {MAX_ROUNDS} rounds.")
        body = "\n".join(f"slot {s}: {q.question_text}" for s, q in state["accepted"].items())
        res = provider.generate(system=f"Judge how hard each exam question is for the intended course level. {GUARD}",
                                prompt=f"Assess each question's difficulty as Easy, Medium or Hard:\n{body}",
                                schema=DifficultyAssessment, purpose="difficulty_assessment")
        return {"difficulty": {v.slot: v.assessed_difficulty for v in res.data.verdicts}}

    def rubrics(state: PaperState) -> PaperState:
        by_id = {c.chunk_id: c for c in state["chunks"]}
        warnings = list(state.get("warnings", []))
        out: list[PaperQuestion] = []
        for n, slot in enumerate(state["slots"], start=1):
            q = state["accepted"][slot.slot]
            criteria, _ = generate_rubric(provider, slot, q)
            refs = [SourceReference(**by_id[c].model_dump(exclude={"text"})) for c in q.source_chunk_ids if c in by_id]
            if not refs:
                warnings.append(f"Q{n}: the model cited no valid source excerpt; verify it against the material.")
            assessed = state["difficulty"].get(slot.slot, slot.difficulty)
            if assessed != slot.difficulty:
                warnings.append(f"Q{n}: requested {slot.difficulty}, assessed as {assessed}.")
            out.append(PaperQuestion(question_number=n, question_text=q.question_text, topic=q.topic or slot.topic,
                                     difficulty=assessed, question_type=slot.question_type, marks=slot.marks,
                                     expected_answer=q.expected_answer, expected_concepts=q.expected_concepts,
                                     rubric=criteria, source_references=refs))
        return {"questions": out, "warnings": warnings}

    def validate(state: PaperState) -> PaperState:
        total = sum(q.marks for q in state["questions"])
        expected = sum(s.marks for s in state["slots"])
        if abs(total - expected) > 1e-6:
            raise AIError(f"Paper totals {total:g} but {expected:g} was requested.")
        for q in state["questions"]:
            if abs(sum(c.max_marks for c in q.rubric) - q.marks) > 1e-6:
                raise AIError(f"Rubric for Q{q.question_number} does not sum to its marks.")
        log.info("paper generated questions=%s prompt=%s", len(state["questions"]), PROMPT_VERSION)
        return {}

    g = StateGraph(PaperState)
    for name, fn in [("retrieve", retrieve), ("generate", generate), ("dedupe", dedupe), ("assess", assess),
                     ("rubrics", rubrics), ("validate", validate)]:
        g.add_node(name, fn)
    g.set_entry_point("retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", "dedupe")
    g.add_conditional_edges("dedupe", after_dedupe, {"generate": "generate", "assess": "assess"})
    g.add_edge("assess", "rubrics")
    g.add_edge("rubrics", "validate")
    g.add_edge("validate", END)
    return g.compile()
