"""TEST DOUBLE for the Gemini REST API. Never used by the application in any environment.

It exists so the automated tests and the local acceptance run can drive the *real* Gemini SDK,
the real LangGraph workflows and the real database end to end without network access to Google.
Its answers are produced by simple, transparent rules (word overlap, Tesseract OCR for page
images), so results from a run against this stub say nothing about model accuracy.

Run: python scripts/dev_stubs/gemini_stub.py --port 8787
Point the API at it with GEMINI_BASE_URL=http://127.0.0.1:8787 (any GEMINI_API_KEY).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import re
import subprocess
import tempfile
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STOP = set("""the a an and or of to in on for with by is are was were be been this that these those it its as at from into
which what how why when where who whom their there them they you your we our can may must should would will each than then also
explain describe discuss briefly write about using between give example examples""".split())


def words(t: str) -> list[str]:
    return [w for w in re.findall(r"[a-z][a-z\-]+", t.lower()) if w not in STOP and len(w) > 2]


def embed(text: str, dims: int) -> list[float]:
    v = [0.0] * dims
    for w in words(text):
        h = int(hashlib.md5(w.encode()).hexdigest(), 16)
        v[h % dims] += 1.0 if (h >> 8) & 1 else -1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def tag(prompt: str, name: str) -> str:
    m = re.search(rf"<untrusted_{name}>\n(.*?)\n</untrusted_{name}>", prompt, re.S)
    return m.group(1) if m else ""


def sentences(t: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", t) if len(s.strip()) > 8]


def concept_hit(concept: str, answer: str) -> float:
    cw = set(words(concept))
    return len(cw & set(words(answer))) / len(cw) if cw else 0.0


def expected_concepts(prompt: str) -> list[str]:
    m = re.search(r"Expected concepts: (.*)", prompt)
    return [c.strip() for c in m.group(1).split(";") if c.strip()] if m else []


def ocr(image_b64: str) -> tuple[str, float]:
    with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
        f.write(base64.urlsafe_b64decode(image_b64.replace("+", "-").replace("/", "_") + "=" * (-len(image_b64) % 4))); f.flush()
        tsv = subprocess.run(["tesseract", f.name, "-", "--psm", "4", "tsv"], capture_output=True, text=True, timeout=60).stdout
    lines: dict[tuple, list[str]] = {}
    confs = []
    for row in tsv.splitlines()[1:]:
        c = row.split("\t")
        if len(c) == 12 and c[11].strip() and float(c[10]) >= 0:
            lines.setdefault((c[2], c[3], c[4]), []).append(c[11]); confs.append(float(c[10]))
    return "\n".join(" ".join(v) for v in lines.values()), (sum(confs) / len(confs) / 100 if confs else 0.0)


def page_transcription(prompt: str, image: str | None) -> dict:
    text, conf = ocr(image) if image else ("", 0.0)
    if not text.strip():
        return {"rotation_needed": 0, "is_blank": True, "blocks": []}
    blocks, current = [], {"question_number": None, "is_continuation": True, "lines": []}
    page_no = None
    for line in text.splitlines():
        if m := re.match(r"^\s*page\s+(\d+)\s*$", line, re.I):
            page_no = int(m.group(1)); continue
        m = re.match(r"^\s*(?:Q|Ans(?:wer)?\.?)\s*(\d+)\s*[).:\-]?\s*(.*)$", line, re.I)
        if m:
            if current["lines"]:
                blocks.append(current)
            current = {"question_number": int(m.group(1)), "is_continuation": False, "lines": [m.group(2)] if m.group(2) else []}
        else:
            current["lines"].append(line)
    if current["lines"]:
        blocks.append(current)
    return {"rotation_needed": 0, "is_blank": False, "written_page_number": page_no, "blocks": [
        {"question_number": b["question_number"], "is_continuation": b["is_continuation"], "text": "\n".join(b["lines"]).strip(),
         "confidence": round(min(max(conf, 0.0), 1.0), 3), "contains_diagram": False, "contains_equation": "=" in "".join(b["lines"]),
         "region": "page", "illegible_segments": 0} for b in blocks]}


def respond(title: str, prompt: str, image: str | None) -> dict:
    answer = tag(prompt, "student_answer")
    if title == "GeneratedQuestionSet":
        slots = [json.loads(s) for s in re.findall(r"^\{\"slot\".*\}$", prompt, re.M)]
        chunks = re.findall(r"chunk_id=(\S+) \| [^\n]*\n(.*?)\n</untrusted_excerpt>", prompt, re.S)
        avoid = prompt.count("Do not repeat")
        out = []
        for i, s in enumerate(slots):
            ranked = sorted(chunks, key=lambda c: -len(set(words(s["topic"])) & set(words(c[1])))) or [("", s["topic"])]
            cid, text = ranked[(i + avoid) % len(ranked)]
            keys = [w for w, _ in Counter(words(text)).most_common(12) if w not in words(s["topic"])][:4] or ["definition"]
            first = (sentences(text) or [text])[0][:160]
            out.append({"slot": s["slot"], "topic": s["topic"], "source_chunk_ids": [cid] if cid else [],
                        "question_text": f"[{s['difficulty']}] Explain {s['topic']} and discuss {', '.join(keys[:3])}. Refer to: \"{first}\" (variant {avoid + i + 1})",
                        "expected_answer": text[:600], "expected_concepts": keys})
        return {"questions": out}
    if title == "DifficultyAssessment":
        return {"verdicts": [{"slot": int(s), "assessed_difficulty": d} for s, d in re.findall(r"slot (\d+): \[(Easy|Medium|Hard)\]", prompt)]}
    if title == "RubricDraft":
        total = float(re.search(r"sum to exactly ([\d.]+)", prompt).group(1))
        parts = [("Conceptual explanation", "conceptual_correctness", .4), ("Coverage of key points", "coverage", .4), ("Organisation and clarity", "organization", .2)]
        crit = [{"criterion": n, "category": c, "max_marks": round(total * w * 4) / 4 or .25, "expected_evidence": f"Answer demonstrates {n.lower()} for this question."} for n, c, w in parts]
        crit[0]["max_marks"] += total - sum(c["max_marks"] for c in crit)
        return {"criteria": crit}
    if title == "PageTranscription":
        return page_transcription(prompt, image)
    if title == "QuestionUnderstanding":
        q = re.search(r"\n(.*)\n\nState what", prompt)
        return {"asks_for": (q.group(1) if q else "the explanation requested")[:200], "learning_outcomes": ["Explain the core idea accurately"], "command_verb": "explain"}
    if title == "IdentifiedConcepts":
        return {"concepts": [w for w, _ in Counter(words(answer)).most_common(6)], "misconceptions": []}
    if title == "CoverageAssessment":
        items = []
        for c in expected_concepts(prompt):
            hit = concept_hit(c, answer)
            quote = next((s for s in sentences(answer) if set(words(c)) & set(words(s))), "")
            items.append({"concept": c, "status": "covered" if hit >= .99 else "partial" if hit > 0 else "missing", "evidence_quote": quote[:200]})
        return {"items": items, "valid_alternatives": []}
    if title == "CorrectnessAssessment":
        return {"incorrect_statements": []}
    if title == "RelevanceAssessment":
        q = re.search(r"Question: (.*)", prompt)
        overlap = len(set(words(q.group(1) if q else "")) & set(words(answer)))
        return {"answers_the_question": overlap > 0, "relevance": min(1.0, overlap / 4), "off_topic_portion": 0.0}
    if title == "VisualAssessment":
        return {"readable": True, "diagram_findings": "Stub: not assessed", "equation_findings": "", "correctness": .5}
    if title == "RubricScoring":
        concepts = expected_concepts(prompt)
        frac = sum(concept_hit(c, answer) for c in concepts) / len(concepts) if concepts else 0
        if not answer.strip():
            frac = 0
        quote = (sentences(answer) or [""])[0][:200]
        awards = []
        for cid, crit, mx in re.findall(r"^- \[([0-9a-f\-]{36})\] (.*?) \(\w+, max ([\d.]+)\)", prompt, re.M):
            mx = float(mx)
            got = round(mx * (min(1, frac + .25) if "Organisation" in crit and frac > 0 else frac) * 4) / 4
            awards.append({"criterion_id": cid, "awarded_marks": got, "evidence_quotes": [quote] if quote else [],
                           "reason": f"Stub rule: {frac:.0%} of expected concepts found in the answer" + ("." if got == mx else "; marks withheld for concepts not found.")})
        return {"awards": awards}
    if title == "StudentFeedback":
        return {"strengths": ["Addresses the question directly"], "improvements": ["Cover every expected concept explicitly"],
                "overall_feedback": "Generated by the test stub from word overlap; not a real assessment.", "suggested_improved_answer": ""}
    if title == "ArgumentAnalysis":
        return {"claim_summary": "Student argues the deduction was too harsh", "claim_type": "marking_error", "student_answer_supports_claim": True}
    if title == "AlternativeValidity":
        return {"is_valid": True, "supported_by_sources": True, "reasoning": "Stub: claim mentions concepts present in sources", "uncertain": False}
    if title == "ChallengeRecommendation":
        m = re.search(r"Original evaluation \(([\d.]+)/([\d.]+)\)", prompt)
        orig, mx = (float(m.group(1)), float(m.group(2))) if m else (0, 0)
        return {"recommendation": "partially_accept", "suggested_marks": min(mx, orig + 1), "reasoning": "Stub recommendation: one additional mark for the disputed point.", "confidence": 0.6}
    raise ValueError(f"stub has no rule for schema {title}")


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        if self.path.endswith(":batchEmbedContents"):
            out = {"embeddings": [{"values": embed(" ".join(p.get("text", "") for p in r["content"]["parts"]), r.get("outputDimensionality", 768))} for r in body["requests"]]}
        else:
            parts = body["contents"][0]["parts"]
            prompt = "\n".join(p["text"] for p in parts if "text" in p)
            image = next((p["inlineData"]["data"] for p in parts if "inlineData" in p), None)
            title = body["generationConfig"]["responseJsonSchema"].get("title", "")
            try:
                payload = respond(title, prompt, image)
            except Exception as exc:  # noqa: BLE001
                self._send(400, {"error": {"code": 400, "message": f"stub: {exc}", "status": "INVALID_ARGUMENT"}}); return
            out = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}], "role": "model"}, "finishReason": "STOP"}], "modelVersion": "stub"}
        self._send(200, out)

    def _send(self, code: int, obj: dict):
        data = json.dumps(obj).encode()
        self.send_response(code); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(data)))
        self.send_header("x-evalai-test-double", "gemini-stub"); self.end_headers(); self.wfile.write(data)

    def log_message(self, *a):
        pass


def serve(port: int = 0) -> ThreadingHTTPServer:
    s = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    s = serve(ap.parse_args().port)
    print(f"gemini test double on :{s.server_port}")
    threading.Event().wait()
