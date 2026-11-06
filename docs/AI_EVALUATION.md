# AI evaluation

## What the model is and is not trusted with

The model reads, compares and explains. It never decides on its own what a student sees. Totals are computed in code from criterion scores, criterion scores are bounded by the approved rubric in code and in the database, and every result requires teacher approval.

All model calls go through `AIProvider.generate(schema=...)`: Gemini is asked for JSON matching a Pydantic schema, the response is validated, and invalid output is retried before failing the job. Student answers and uploaded documents are wrapped as `<untrusted_*>` data with an instruction that they carry no authority (prompt injection tests are in the benchmark set).

## Pipelines

**Indexing.** PyMuPDF (PDF), python-docx (DOCX) or plain text → per-page text with chapter detection (PDF outline, else headings) → LlamaIndex `SentenceSplitter` with exact page provenance → Gemini embeddings → `document_chunks`. Scanned PDFs without a text layer fail with an explanation (see limitations).

**Paper generation** (LangGraph, `workflows/paper_generation.py`): a deterministic blueprint fixes marks, difficulty and type per slot → retrieve chunks per topic (tenant-scoped pgvector search, weak-coverage report) → generate questions with cited chunk ids → de-duplicate (normalised text and embedding cosine ≥ 0.92, also against the bank) and regenerate missing slots → assess difficulty → per-question rubric with criteria normalised to sum exactly to the marks → attach only citations that were actually retrieved → validate totals. Warnings (e.g. no valid citation, difficulty mismatch) are shown to the teacher before publishing.

**Handwriting** (`answer_extractor`): pages rendered at 200 dpi and stored as originals → per page: deskew (Hough line angle), CLAHE contrast in colour → Gemini vision transcription with rules: never invent, mark `[illegible]`, drop struck-out text, describe diagrams, report rotation (the page is rotated and re-read). A deterministic assembler then stitches blocks across pages, follows continuations, refuses to carry an answer across a page that failed, flags unknown question numbers, unassigned text, low confidence, illegible segments, gaps in the written page numbers and unanswered questions. Teachers can correct any transcription or assign stray text.

**Evaluation** (LangGraph, 12 nodes, `workflows/evaluation.py`):
1 load answer and page references · 2 question understanding (cached per question, so every student is marked against the same reading) · 3 rubric, model answer, retrieved course material · 4 concepts demonstrated · 5 coverage: covered / partial / missing / valid alternatives · 6 errors (quotes are verified against the answer; invented quotes are dropped) · 7 relevance · 8 diagrams and equations from the **page images** · 9 per-criterion scoring in 0.25 steps · 10 consistency validation (bounds, double counting, unexplained deductions, high marks for off-topic answers, zero despite valid alternatives) with one corrective re-score · 11 confidence signal · 12 feedback that may not change the marks.

The grading model receives no student identity. Missing or illegible text is treated as a reading gap: such answers are flagged for review and pages that failed produce an unmarked evaluation rather than a zero.

**Confidence** = 0.35 × recognition confidence + 0.30 × share of evidence quotes found in the answer + 0.15 × rubric clarity + 0.20 × agreement between concept coverage and awarded fraction. It decides what goes to review; it is not a probability of correctness.

**Consistency engine.** One approved rubric version per question for every student, stored on each evaluation. After marking, the exam is checked for outliers (z ≥ 2.5), near-identical answers (cosine ≥ 0.93) whose marks differ by ≥ 25 %, and drift against teacher reference answers (per item > 15 % of marks; systematic bias > 7.5 % across ≥ 3 references).

**Challenges** (LangGraph): gather key, rubric, answer, evaluation and sources (and page images for handwriting or diagram disputes) → classify the claim → judge validity → recommend accept / partially accept / reject / escalate with suggested marks capped at the maximum. Low confidence, uncertainty, and disputes about the key, rubric or question always escalate. Only the teacher's decision changes marks, and it can add an accepted alternative to the rubric as a new version.

## Measuring accuracy

`benchmarks/evaluation_set.json` holds complete, alternative-wording, partial, incorrect, contradictory, off-topic, prompt-injection, empty and illegible answers. Its expected marks were written by the build team and **have not been reviewed by a teacher**. Run `scripts/run_benchmark.py` with real Gemini credentials after a teacher confirms them. No accuracy figure has been measured yet; the automated tests check orchestration rules only.

## Known limitations
- Scanned textbooks (no text layer) are not OCR'd during indexing.
- Region detection is model-reported text regions, not pixel bounding boxes.
- Gemini model ids change; check https://ai.google.dev/models and set `GEMINI_MODEL`/`GEMINI_EMBEDDING_MODEL`. Changing embedding dimensions requires a migration and re-indexing.
