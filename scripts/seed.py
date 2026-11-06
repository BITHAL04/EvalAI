"""Populate a database with clearly labelled demonstration data.

    cd apps/api && python ../../scripts/seed.py

Every seeded examination, evaluation and result has is_demo = true and the UI labels it
"Sample data". Seeded marks were written by hand for demonstration; none of them were produced
by the AI pipeline. Demo accounts are matched by email when that person first signs in with
Clerk, so set DEMO_*_EMAIL to addresses you can sign up with.
"""
from __future__ import annotations

import os
import random
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "apps" / "api")]

from sqlalchemy import select  # noqa: E402

from app.core.db import system_session  # noqa: E402
from app.models import (  # noqa: E402
    CriterionScore, Enrollment, Evaluation, EvaluationVersion, ExamStatus, Examination, ExaminationQuestion, ExaminationTopic, Institution,
    InstitutionMembership, QuestionBankItem, Result, RoleRow, StudentPerformanceSnapshot, Subject, Submission, TopicPerformance, User, UserProfile,
)
from app.services.exams import add_rubric  # noqa: E402
from ai_engine.analytics.insights import QuestionOutcome, recommendations, topic_breakdown  # noqa: E402

TEACHER = os.environ.get("DEMO_TEACHER_EMAIL", "teacher@demo.evalai.app")
ADMIN = os.environ.get("DEMO_ADMIN_EMAIL", "admin@demo.evalai.app")
STUDENTS = os.environ.get("DEMO_STUDENT_EMAILS", "student@demo.evalai.app,aarav@demo.evalai.app,meera@demo.evalai.app,kabir@demo.evalai.app,zoya@demo.evalai.app").split(",")
NAMES = ["Priya Sharma", "Aarav Mehta", "Meera Iyer", "Kabir Singh", "Zoya Khan"]

RUBRIC = lambda m: [  # noqa: E731
    {"criterion": "Conceptual correctness", "category": "conceptual_correctness", "max_marks": m * .4, "expected_evidence": "Explains the core mechanism accurately, in any wording."},
    {"criterion": "Coverage of key concepts", "category": "coverage", "max_marks": m * .4, "expected_evidence": "Addresses each expected concept listed for the question."},
    {"criterion": "Organisation and clarity", "category": "organization", "max_marks": m * .2, "expected_evidence": "Logical structure; a reader can follow the explanation."},
]

SUBJECTS = {
    "Machine Learning": ("ML301", [
        ("Supervised Learning", "Distinguish bias and variance, and explain how each affects model error.", 10, ["bias", "variance", "underfitting", "overfitting", "trade-off"]),
        ("Optimisation", "Explain gradient descent and the role of the learning rate.", 5, ["gradient", "loss function", "learning rate", "convergence"]),
        ("Model Evaluation", "Why is cross-validation preferred over a single train/test split?", 5, ["k folds", "variance of estimate", "data efficiency"]),
    ]),
    "Database Management Systems": ("DB201", [
        ("Normalisation", "Explain 3NF with an example of a transitive dependency.", 10, ["functional dependency", "transitive dependency", "decomposition", "2NF"]),
        ("Transactions", "Describe the ACID properties of a transaction.", 5, ["atomicity", "consistency", "isolation", "durability"]),
        ("Indexing", "When does a B+ tree index help a query, and when does it not?", 5, ["range queries", "selectivity", "write overhead"]),
    ]),
    "Deep Learning": ("DL401", [
        ("Convolutional Neural Networks", "Explain the working of a CNN for image classification.", 10, ["convolution", "feature maps", "pooling", "fully connected layer"]),
        ("Backpropagation", "Explain backpropagation and the vanishing gradient problem.", 5, ["chain rule", "gradients", "vanishing gradient", "activation choice"]),
        ("Regularisation", "How does dropout reduce overfitting?", 5, ["random deactivation", "ensemble effect", "inference scaling"]),
    ]),
}


def user(db, email, name, role, inst, roll=None):
    u = db.scalar(select(User).where(User.email == email))
    if u is None:
        u = User(email=email)
        u.profile = UserProfile(full_name=name, roll_number=roll)
        db.add(u)
        db.flush()
    r = db.scalar(select(RoleRow).where(RoleRow.name == role))
    if not db.scalar(select(InstitutionMembership).where(InstitutionMembership.user_id == u.id, InstitutionMembership.institution_id == inst.id)):
        db.add(InstitutionMembership(institution_id=inst.id, user_id=u.id, role_id=r.id))
    return u


def main() -> None:
    rnd = random.Random(7)
    with system_session() as db:
        if db.scalar(select(Institution).where(Institution.slug == "demo-university")):
            print("Demo data already present; nothing to do.")
            return
        inst = Institution(name="Demo Institute of Technology", slug="demo-university", settings={}, is_demo=True)
        db.add(inst)
        db.flush()
        teacher = user(db, TEACHER, "Dr. Anjali Rao", "teacher", inst)
        user(db, ADMIN, "Platform Admin", "admin", inst)
        students = [user(db, e.strip(), n, "student", inst, f"CS22{i:03d}") for i, (e, n) in enumerate(zip(STUDENTS, NAMES), start=1)]
        for sname, (code, items) in SUBJECTS.items():
            subj = Subject(institution_id=inst.id, name=sname, code=code, semester="6", created_by=teacher.id, description=f"Demo subject: {sname}")
            db.add(subj)
            db.flush()
            for s in students:
                db.add(Enrollment(institution_id=inst.id, subject_id=subj.id, user_id=s.id))
            for topic, text, marks, concepts in items:
                db.add(QuestionBankItem(institution_id=inst.id, subject_id=subj.id, question_text=text, topic=topic, marks=marks, difficulty="Medium",
                                        expected_concepts=concepts, rubric=RUBRIC(marks), origin="seed", created_by=teacher.id,
                                        expected_answer=f"A complete answer covers: {', '.join(concepts)}."))
            for n, when in ((1, 40), (2, 12)):
                exam = Examination(institution_id=inst.id, subject_id=subj.id, title=f"{sname} — Unit Test {n} (sample)", total_marks=sum(i[2] for i in items),
                                   duration_minutes=60, status=ExamStatus.results_published.value, is_demo=True, created_by=teacher.id,
                                   published_at=datetime.now(UTC) - timedelta(days=when + 7), results_published_at=datetime.now(UTC) - timedelta(days=when),
                                   published_by=teacher.id, instructions="Answer all questions.", config={"topics": [i[0] for i in items], "seeded": True})
                db.add(exam)
                db.flush()
                qs = []
                for k, (topic, text, marks, concepts) in enumerate(items, start=1):
                    q = ExaminationQuestion(institution_id=inst.id, examination_id=exam.id, question_number=k, question_text=text, topic=topic, difficulty="Medium",
                                            question_type="descriptive", marks=marks, expected_answer=f"Covers {', '.join(concepts)}.", expected_concepts=concepts, origin="seed")
                    db.add(q)
                    db.flush()
                    r = add_rubric(db, q, RUBRIC(marks), status="approved")
                    r.approved_by, r.approved_at = teacher.id, exam.published_at
                    db.add(ExaminationTopic(institution_id=inst.id, examination_id=exam.id, name=topic))
                    qs.append((q, r, concepts))
                db.flush()
                for s in students:
                    sub = Submission(institution_id=inst.id, examination_id=exam.id, student_id=s.id, status="approved", submitted_at=exam.published_at + timedelta(days=2), is_demo=True)
                    db.add(sub)
                    db.flush()
                    ability = rnd.uniform(.45, .92)
                    outcomes = []
                    for q, r, concepts in qs:
                        cut = max(0, min(len(concepts), round(len(concepts) * (ability + rnd.uniform(-.2, .15)))))
                        ev = Evaluation(institution_id=inst.id, submission_id=sub.id, question_id=q.id, rubric_id=r.id, max_marks=q.marks, status="approved",
                                        confidence=0, is_demo=True, report={"seeded": True, "covered_points": concepts[:cut], "missing_points": concepts[cut:],
                                                                            "overall_feedback": "Seeded sample record; not produced by AI evaluation."})
                        total = Decimal(0)
                        for c in r.criteria:
                            frac = min(1, max(0, ability + rnd.uniform(-.25, .15)))
                            got = Decimal(str(round(float(c.max_marks) * frac * 4) / 4))
                            total += got
                            ev.criterion_scores.append(CriterionScore(institution_id=inst.id, rubric_criterion_id=c.id, criterion=c.criterion, category=c.category,
                                                                      max_marks=c.max_marks, awarded_marks=got, reason="Seeded sample mark."))
                        ev.marks_awarded = total
                        db.add(ev)
                        db.flush()
                        db.add(EvaluationVersion(institution_id=inst.id, evaluation_id=ev.id, version=1, rubric_id=r.id, marks_awarded=total, snapshot={"seeded": True},
                                                 actor_type="teacher", actor_id=teacher.id, reason="Seeded sample record"))
                        outcomes.append(QuestionOutcome(q.question_number, q.topic, float(total), float(q.marks), concepts[cut:], [], 0,
                                                        [{"category": c.category, "awarded_marks": float(c.awarded_marks), "max_marks": float(c.max_marks)} for c in ev.criterion_scores]))
                    tops = topic_breakdown(outcomes)
                    tot, mx = sum(o.marks for o in outcomes), sum(o.max_marks for o in outcomes)
                    res = Result(institution_id=inst.id, submission_id=sub.id, examination_id=exam.id, student_id=s.id, total_marks=tot, max_marks=mx, percentage=round(tot / mx * 100, 2),
                                 status="published", published_at=exam.results_published_at, published_by=teacher.id, insights=recommendations(outcomes, tops), is_demo=True)
                    db.add(res)
                    db.flush()
                    for t in tops:
                        db.add(TopicPerformance(institution_id=inst.id, result_id=res.id, student_id=s.id, examination_id=exam.id, subject_id=subj.id, topic=t["name"],
                                                marks=t["marks"], max_marks=t["max_marks"], score=t["score"], status=t["status"]))
                    db.add(StudentPerformanceSnapshot(institution_id=inst.id, student_id=s.id, examination_id=exam.id, subject_id=subj.id, percentage=res.percentage, taken_at=exam.results_published_at))
        db.commit()
        print(f"Seeded '{inst.name}'. Sign in with {TEACHER} (teacher), {ADMIN} (admin) or {STUDENTS[0]} (student).")


if __name__ == "__main__":
    main()
