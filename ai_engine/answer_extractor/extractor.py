"""Page-by-page transcription followed by a deterministic stitching step."""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ai_engine.agents.prompting import GUARD
from ai_engine.handwriting.preprocess import enhance
from ai_engine.providers.base import AIError, AIProvider, AITransientError, ImageInput
from ai_engine.schemas import ExtractedAnswerOut, ExtractionOutput, PageReference, PageTranscription

log = logging.getLogger("evalai.ai")
UNATTRIBUTED = 0

SYSTEM = f"""You transcribe handwritten exam answer pages exactly as written, for any handwriting style: cursive, block,
uneven spacing, any pen colour. Rules:
- Never invent, complete, or correct what the student wrote. Keep their errors and spelling.
- Write [illegible] for any word you cannot read. Honest gaps are required.
- Omit text the student clearly struck out. If overwritten, keep the final version.
- Render equations in plain text or LaTeX; render tables as rows of cells.
- For a diagram or flowchart set contains_diagram and describe it factually with its labels; do not judge it.
- question_number is only the number the student wrote. If the page continues an earlier answer without a new number,
  set is_continuation. If you cannot tell, leave question_number null.
- confidence is your honest probability that the transcription of that block is accurate.
- If the page is sideways or upside down, set rotation_needed to the clockwise degrees required.
{GUARD}"""


@dataclass
class AssemblyPage:
    number: int
    transcription: PageTranscription


@dataclass
class _Draft:
    parts: list[str] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)
    refs: list[PageReference] = field(default_factory=list)
    conf: list[tuple[float, int]] = field(default_factory=list)
    diagram: bool = False
    equation: bool = False
    illegible: int = 0
    reasons: list[str] = field(default_factory=list)


def transcribe_page(provider: AIProvider, image: bytes, page: int, question_list: str, previous_tail: str) -> tuple[PageTranscription, str]:
    prompt = (f"This is page {page} of one student's answer booklet.\nQuestions on the paper:\n{question_list}\n\n"
              f"The previous page ended with: \"{previous_tail[-300:]}\"\nTranscribe this page.")
    res = provider.generate(system=SYSTEM, prompt=prompt, schema=PageTranscription, vision=True, temperature=0,
                            images=[ImageInput(enhance(image), "image/jpeg", f"Page {page}")], purpose="handwriting_transcription")
    if res.data.rotation_needed:
        turns = res.data.rotation_needed // 90
        res = provider.generate(system=SYSTEM, prompt=prompt, schema=PageTranscription, vision=True, temperature=0,
                                images=[ImageInput(enhance(image, turns), "image/jpeg", f"Page {page}")],
                                purpose="handwriting_transcription_rotated")
    return res.data, res.model


def assemble(submission_id: str, pages: list[AssemblyPage], valid_numbers: set[int], *, review_threshold: float,
             failed_pages: list[dict] | None = None) -> ExtractionOutput:
    """Join blocks into answers. Pure function: same pages in, same answers out."""
    drafts: dict[int, _Draft] = {}
    warnings: list[str] = []
    current: int | None = None
    failed = {f["page"] for f in failed_pages or []}

    for page in sorted(pages, key=lambda p: p.number):
        if page.number - 1 in failed:
            current = None  # the thread of the answer is lost across an unread page
        if page.transcription.is_blank:
            continue
        for block in page.transcription.blocks:
            reasons: list[str] = []
            if block.question_number is not None and block.question_number in valid_numbers:
                target = current = block.question_number
            elif block.question_number is not None:
                target = UNATTRIBUTED
                reasons.append(f"Page {page.number}: question number {block.question_number} is not on this paper")
            elif current is not None:
                target = current
                if not block.is_continuation:
                    reasons.append(f"Page {page.number}: no question number; assumed to continue Q{current}")
            else:
                target = UNATTRIBUTED
                reasons.append(f"Page {page.number}: text could not be matched to a question")
            d = drafts.setdefault(target, _Draft())
            d.parts.append(block.text.strip())
            d.diagram |= block.contains_diagram
            d.equation |= block.contains_equation
            if block.diagram_description:
                d.parts.append(f"[Diagram on page {page.number}: {block.diagram_description}]")
            if page.number not in d.pages:
                d.pages.append(page.number)
            d.refs.append(PageReference(page_number=page.number, region=block.region))
            d.conf.append((block.confidence, max(len(block.text), 1)))
            d.illegible += block.illegible_segments + len(re.findall(r"\[illegible\]", block.text))
            d.reasons.extend(reasons)

    answers: list[ExtractedAnswerOut] = []
    for number in sorted(drafts):
        d = drafts[number]
        weight = sum(w for _, w in d.conf)
        conf = round(sum(c * w for c, w in d.conf) / weight, 3) if weight else 0.0
        reasons = list(d.reasons)
        if conf < review_threshold:
            reasons.append(f"Low recognition confidence ({conf:.0%})")
        if d.illegible:
            reasons.append(f"{d.illegible} illegible segment(s)")
        if failed and number != UNATTRIBUTED and any(p + 1 in failed or p - 1 in failed for p in d.pages):
            reasons.append("Answer may continue on a page that failed to process")
        answers.append(ExtractedAnswerOut(
            question_number=number, pages=sorted(d.pages), recognized_text="\n".join(p for p in d.parts if p),
            ocr_confidence=conf, contains_diagram=d.diagram, contains_equation=d.equation,
            page_references=d.refs, needs_human_verification=bool(reasons), verification_reasons=reasons))

    labels = [p.transcription.written_page_number for p in sorted(pages, key=lambda p: p.number)
              if p.transcription.written_page_number is not None]
    missing = sorted(set(range(min(labels), max(labels) + 1)) - set(labels)) if len(labels) >= 2 else []
    if missing:
        warnings.append(f"Written page numbers skip {', '.join(map(str, missing))}; pages may be missing from the scan")
    if labels != sorted(labels):
        warnings.append("Written page numbers are out of order; check the scan")
    if UNATTRIBUTED in drafts:
        warnings.append("Some text could not be matched to a question and needs manual assignment")
    unanswered = sorted(valid_numbers - set(drafts))
    if unanswered:
        warnings.append(f"No answer found for: {', '.join(f'Q{n}' for n in unanswered)}")
    return ExtractionOutput(submission_id=submission_id, answers=answers, warnings=warnings, page_failures=failed_pages or [])


def extract_submission(provider: AIProvider, submission_id: str, images: list[bytes], questions: list[tuple[int, str]],
                       *, review_threshold: float, on_page: Callable[[int], None] | None = None) -> tuple[ExtractionOutput, str | None]:
    """Run all pages. One bad page is reported and does not lose the rest."""
    question_list = "\n".join(f"Q{n}: {t[:160]}" for n, t in questions)
    pages: list[AssemblyPage] = []
    failures: list[dict] = []
    tail, model = "", None
    for i, image in enumerate(images, start=1):
        try:
            t, model = transcribe_page(provider, image, i, question_list, tail)
            pages.append(AssemblyPage(i, t))
            if t.blocks:
                tail = t.blocks[-1].text
        except AITransientError:
            raise  # the whole job is retried, reusing nothing half-done
        except (AIError, ValueError) as exc:
            log.warning("page %s failed: %s", i, exc)
            failures.append({"page": i, "error": str(exc)[:300]})
            tail = ""
        if on_page:
            on_page(i)
    output = assemble(submission_id, pages, {n for n, _ in questions}, review_threshold=review_threshold, failed_pages=failures)
    return output, model
