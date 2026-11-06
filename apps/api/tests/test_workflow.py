"""The primary acceptance flow through the HTTP API, worker, database and AI pipeline.

AI calls go through the real Gemini SDK to the local test double (see scripts/dev_stubs), so
this proves integration and integrity rules, not grading quality.
"""
from sqlalchemy import create_engine, text

from tests.conftest import drain, handwritten_pdf, text_pdf, upload

NOTES = [
    "Chapter 1 Neural Networks\nA neural network is built from layers of neurons. Each neuron computes a weighted sum and applies an activation function. "
    "Backpropagation computes gradients of the loss with respect to weights. Gradient descent updates the weights using the learning rate.",
    "Chapter 2 Convolutional Neural Networks\nA convolutional neural network applies convolution filters to the input image to produce feature maps. "
    "Pooling layers downsample feature maps to reduce computation. A fully connected layer at the end produces class scores.",
]


def setup_exam(w):
    t = w.teacher
    sid = t.post("/subjects", json={"name": "Machine Learning", "code": "ML101"}).json()["id"]
    t.post(f"/subjects/{sid}/enrollments", json={"user_ids": [w.s1.id, w.s2.id]})
    info = t.post("/documents/upload-url", json={"filename": "notes.pdf", "size_bytes": 2000, "content_type": "application/pdf", "subject_id": sid}).json()
    upload(t.client, info, text_pdf(NOTES))
    doc = t.post("/documents", json={"upload_token": info["upload_token"], "title": "ML lecture notes", "kind": "notes"})
    assert doc.status_code == 201 and doc.json()["status"] == "uploaded"
    drain()
    d = t.get(f"/documents/{doc.json()['id']}").json()
    assert d["status"] == "indexed" and d["chunk_count"] >= 1
    assert "Chapter 2 Convolutional Neural Networks" in t.get(f"/subjects/{sid}/topics").json()["items"]

    bad = t.post("/examinations", json={"title": "Bad", "subject_id": sid, "topics": ["x"], "total_marks": 30, "duration_minutes": 60, "mark_distribution": [{"marks": 10, "count": 2}]})
    assert bad.status_code == 422
    exam = t.post("/examinations", json={"title": "ML Mid-term", "subject_id": sid, "topics": ["Neural Networks", "Convolutional Neural Networks"],
                                         "material_ids": [doc.json()["id"]], "total_marks": 20, "duration_minutes": 60,
                                         "mark_distribution": [{"marks": 10, "count": 1}, {"marks": 5, "count": 2}], "question_types": ["descriptive"]}).json()
    assert w.s1.get(f"/examinations/{exam['id']}").status_code == 404  # drafts are invisible to students
    assert t.post(f"/examinations/{exam['id']}/generate").status_code == 200
    drain()
    e = t.get(f"/examinations/{exam['id']}").json()
    assert e["status"] == "review", e.get("generation_error")
    assert len(e["questions"]) == 3 and e["computed_total"] == 20
    for q in e["questions"]:
        assert sum(c["max_marks"] for c in q["rubric"]["criteria"]) == q["marks"]
        assert q["source_references"] and q["source_references"][0]["material_title"] == "ML lecture notes"
    return sid, exam["id"], e


def test_full_examination_lifecycle(world):
    t, s1 = world.teacher, world.s1
    sid, exam_id, e = setup_exam(world)
    q1 = e["questions"][0]

    # Teacher review: edits are validated, and nothing publishes without the explicit action.
    assert t.put(f"/examination-questions/{q1['id']}", json={"marks": 12}).status_code == 400
    crit = [{"criterion": c["criterion"], "category": c["category"], "max_marks": c["max_marks"], "expected_evidence": c["expected_evidence"]} for c in q1["rubric"]["criteria"]]
    r = t.put(f"/examination-questions/{q1['id']}", json={"question_text": "Explain how a convolutional neural network processes an image.",
                                                         "expected_concepts": ["convolution filters", "feature maps", "pooling", "fully connected layer"], "rubric": crit})
    assert r.status_code == 200 and r.json()["rubric"]["status"] == "draft"
    assert s1.get(f"/examinations/{exam_id}").status_code == 404
    assert t.post(f"/examinations/{exam_id}/publish").status_code == 200
    assert t.put(f"/examination-questions/{q1['id']}", json={"topic": "late edit"}).status_code == 409

    # Student sees the paper without answer keys.
    view = s1.get(f"/examinations/{exam_id}").json()
    assert "expected_answer" not in str(view) and "rubric" not in view["questions"][0]
    paper = s1.get(f"/examinations/{exam_id}/paper").json()["download_url"]
    pdf = t.client.get(paper.replace("http://testserver", ""))
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"

    # Student uploads a photographed, handwritten-style booklet.
    sub = s1.post("/submissions", json={"examination_id": exam_id, "filename": "answers.pdf", "size_bytes": 300000}).json()
    upload(t.client, sub, handwritten_pdf([
        "Page 1\nQ1. A convolutional neural network applies\nconvolution filters to the image to make feature\nmaps. Pooling layers downsample the feature maps.",
        "Page 2\nA fully connected layer then gives class scores.\nQ2. Neurons compute a weighted sum and an activation.",
    ]))
    assert s1.post(f"/submissions/{sub['id']}/upload").json()["page_count"] == 2
    assert len(s1.get(f"/submissions/{sub['id']}/pages").json()["items"]) == 2
    assert world.s2.get(f"/submissions/{sub['id']}").status_code == 404
    assert world.s2.get(f"/submissions/{sub['id']}/pages").status_code == 404
    assert s1.post(f"/submissions/{sub['id']}/process").json()["status"] == "submitted"
    drain()

    detail = t.get(f"/submissions/{sub['id']}").json()
    assert detail["status"] == "evaluated", detail
    answers = {a["question_number"]: a for a in detail["answers"]}
    assert answers[1]["pages"] == [1, 2] and "pooling" in answers[1]["recognized_text"].lower()
    evals = {ev["question_number"]: ev for ev in detail["evaluations"]}
    assert set(evals) == {1, 2, 3}
    assert evals[3]["marks_awarded"] == 0 and evals[3]["requires_human_review"]  # not answered: flagged, not silently zero
    for ev in evals.values():
        assert 0 <= ev["marks_awarded"] <= ev["max_marks"]
        assert ev["status"] in ("provisional", "needs_review")

    # Provisional marks are invisible to the student.
    assert s1.get(f"/results/{exam_id}").status_code == 404
    assert s1.get(f"/evaluations/{evals[1]['id']}").status_code == 404

    # Approval is blocked while anything is flagged; the teacher reviews each flagged answer.
    assert t.post(f"/evaluations/submission/{sub['id']}/approve").json()["detail"]["code"] == "needs_review"
    over = [{"criterion_id": c["criterion_id"], "awarded_marks": c["max_marks"] + 1, "reason": "too much"} for c in evals[3]["criteria"]]
    assert t.put(f"/evaluations/{evals[3]['id']}/teacher-review", json={"criteria": over, "reason": "Over the maximum"}).status_code == 400
    for n, ev in evals.items():
        if ev["requires_human_review"]:
            crit = [{"criterion_id": c["criterion_id"], "awarded_marks": c["awarded_marks"], "reason": c["reason"] or "Confirmed against the page"} for c in ev["criteria"]]
            r = t.put(f"/evaluations/{ev['id']}/teacher-review", json={"criteria": crit, "reason": "Checked against the original page"})
            assert r.status_code == 200 and r.json()["status"] == "teacher_reviewed"
    ok = t.post(f"/evaluations/submission/{sub['id']}/approve")
    assert ok.status_code == 200, ok.text
    assert t.post(f"/examinations/{exam_id}/publish-results").json()["published"] == 1

    # Student views the published result.
    res = s1.get(f"/results/{exam_id}").json()
    assert res["total_marks"] == ok.json()["total_marks"] and len(res["questions"]) == 3 and res["topics"]
    assert "confidence" not in res["questions"][0] and "trace" not in res["questions"][0]["report"]
    assert s1.get("/analytics/student").json()["exams_taken"] == 1
    assert world.s2.get(f"/results/{exam_id}").status_code == 404

    # Challenge -> AI recommendation -> teacher decision -> updated result and history.
    target = next(q for q in res["questions"] if q["marks_awarded"] < q["max_marks"])
    c = s1.post("/challenges", json={"evaluation_id": target["id"], "category": "incorrect_deduction", "rubric_criterion_id": target["criteria"][0]["criterion_id"],
                                     "explanation": "My answer explains this point in different words on page 1; please re-check."})
    assert c.status_code == 201, c.text
    assert s1.post("/challenges", json={"evaluation_id": target["id"], "category": "incorrect_deduction", "explanation": "Second challenge on the same question"}).status_code == 409
    drain()
    cd = t.get(f"/challenges/{c.json()['id']}").json()
    assert cd["status"] == "pending_teacher_review" and cd["ai_reviews"][0]["recommendation"] == "partially_accept"
    assert t.post(f"/challenges/{cd['id']}/decision", json={"decision": "accepted", "revised_marks": target["max_marks"] + 5, "reason": "too many"}).status_code == 400
    new = min(target["max_marks"], target["marks_awarded"] + 1)
    dec = t.post(f"/challenges/{cd['id']}/decision", json={"decision": "partially_accepted", "revised_marks": new, "reason": "Valid point found on page 1"})
    assert dec.status_code == 200 and dec.json()["revised_marks"] == new
    assert t.post(f"/challenges/{cd['id']}/finalize").json()["status"] == "resolved"

    after = s1.get(f"/results/{exam_id}").json()
    assert after["total_marks"] == res["total_marks"] - target["marks_awarded"] + new
    history = t.get(f"/evaluations/{target['id']}/history").json()["items"]
    assert [h["actor_type"] for h in history][0] == "ai" and history[-1]["actor_type"] == "challenge"
    student_view = s1.get(f"/challenges/{cd['id']}").json()
    assert student_view["status"] == "resolved" and "ai_reviews" not in student_view
    actions = [a["action"] for a in world.admin.get("/admin/audit-logs?limit=200").json()["items"]]
    for a in ("exam.published", "submission.approved", "results.published", "challenge.submitted", "challenge.decided", "challenge.resolved"):
        assert a in actions

    # Evaluation history is immutable even for the application role.
    eng = create_engine("postgresql+psycopg://evalai_app:test@127.0.0.1:54329/evalai_test")
    with eng.connect() as conn:
        conn.execute(text("select set_config('app.platform','on',false)"))
        try:
            conn.execute(text("delete from evaluation_versions"))
            raise AssertionError("history deleted")
        except Exception as exc:  # noqa: BLE001
            assert "permission denied" in str(exc) or "append-only" in str(exc)

    a = t.get(f"/analytics/examination/{exam_id}").json()
    assert a["submissions"] == 1 and a["approved"] == 1 and a["reevaluation"]["marks_changed"] == 1
    assert sum(b["count"] for b in a["score_distribution"]) == 1
    assert t.get("/analytics/teacher/overview").json()["total_students"] == 2


def test_resubmission_policy_and_deadline(world):
    t, s1 = world.teacher, world.s1
    _, exam_id, _ = setup_exam(world)
    t.put(f"/examinations/{exam_id}", json={"duplicate_policy": "reject"})
    t.post(f"/examinations/{exam_id}/publish")
    first = s1.post("/submissions", json={"examination_id": exam_id, "filename": "a.pdf", "size_bytes": 10}).json()
    upload(t.client, first, handwritten_pdf(["Q1. hello world"]))
    s1.post(f"/submissions/{first['id']}/upload")
    # Re-uploading before confirming is always allowed.
    again = s1.post("/submissions", json={"examination_id": exam_id, "filename": "b.pdf", "size_bytes": 10})
    assert again.status_code == 201 and again.json()["version"] == 2
    upload(t.client, again.json(), handwritten_pdf(["Q1. hello again"]))
    s1.post(f"/submissions/{again.json()['id']}/upload")
    s1.post(f"/submissions/{again.json()['id']}/process")
    third = s1.post("/submissions", json={"examination_id": exam_id, "filename": "c.pdf", "size_bytes": 10})
    assert third.status_code == 409 and third.json()["detail"]["code"] == "duplicate_submission"
    t.put(f"/examinations/{exam_id}", json={"submission_deadline": "2020-01-01T00:00:00Z"})
    assert world.s2.post("/submissions", json={"examination_id": exam_id, "filename": "c.pdf", "size_bytes": 10}).json()["detail"]["code"] == "deadline_passed"


def test_upload_validation_of_answer_sheets(world):
    t, s1 = world.teacher, world.s1
    _, exam_id, _ = setup_exam(world)
    t.post(f"/examinations/{exam_id}/publish")
    assert s1.post("/submissions", json={"examination_id": exam_id, "filename": "a.png", "size_bytes": 10}).status_code == 400
    sub = s1.post("/submissions", json={"examination_id": exam_id, "filename": "a.pdf", "size_bytes": 10}).json()
    assert s1.post(f"/submissions/{sub['id']}/process").status_code == 409  # nothing uploaded yet
    upload(t.client, sub, b"MZ\x90 not a pdf")
    assert s1.post(f"/submissions/{sub['id']}/upload").json()["detail"]["code"] == "unsupported_file"


def test_failed_document_is_reported_and_retryable(world):
    t = world.teacher
    sid = t.post("/subjects", json={"name": "Deep Learning", "code": "DL1"}).json()["id"]
    info = t.post("/documents/upload-url", json={"filename": "scan.pdf", "size_bytes": 100, "subject_id": sid}).json()
    import fitz
    blank = fitz.open(); blank.new_page()
    upload(t.client, info, blank.tobytes())
    doc = t.post("/documents", json={"upload_token": info["upload_token"], "title": "Scanned"}).json()
    drain()
    d = t.get(f"/documents/{doc['id']}").json()
    assert d["status"] == "failed" and "No text" in d["error"]
    assert t.post(f"/documents/{doc['id']}/retry").json()["status"] == "uploaded"
    assert any(n["kind"] == "document_failed" for n in t.get("/notifications").json()["items"])
