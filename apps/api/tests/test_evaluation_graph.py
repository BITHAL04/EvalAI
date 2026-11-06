"""Orchestration rules of the LangGraph evaluator, driven by a scripted provider.

These check what EvalAI does with model output (clamping, retries, review flags, feedback
assembly). They do not and cannot measure grading accuracy; see benchmarks/README.md for that.
"""
from ai_engine.evaluation.scoring import RubricItem
from ai_engine.providers.base import AIProvider, StructuredResult
from ai_engine.schemas import (
    ArgumentAnalysis, AlternativeValidity, ChallengeRecommendation, CorrectnessAssessment, CoverageAssessment, IdentifiedConcepts,
    QuestionUnderstanding, RelevanceAssessment, RubricScoring, StudentFeedback, VisualAssessment,
)
from ai_engine.workflows.challenge import ChallengeInput, assess_challenge
from ai_engine.workflows.evaluation import EvaluationInput, evaluate_answer


class Scripted(AIProvider):
    def __init__(self, **responses):
        self.responses, self.calls = responses, []

    def generate(self, *, system, prompt, schema, images=None, purpose, temperature=0.1, vision=False):
        self.calls.append(purpose)
        r = self.responses[schema.__name__]
        r = r.pop(0) if isinstance(r, list) else r
        return StructuredResult(data=schema.model_validate(r), model="scripted")

    def embed(self, texts, *, task):
        return [[1.0, 0.0] for _ in texts]

    @property
    def embedding_model(self):
        return "scripted"


RUBRIC = [RubricItem("c1", "Explains convolution", "conceptual_correctness", 3, "Describes filters sliding over input to make feature maps"),
          RubricItem("c2", "Covers pooling", "coverage", 2, "States pooling downsamples feature maps")]
ANSWER = "A CNN slides learned filters over the image to build feature maps. Max pooling then shrinks the maps."


def base(**over):
    d = dict(QuestionUnderstanding={"asks_for": "how a CNN works", "learning_outcomes": ["explain CNN layers"]},
             IdentifiedConcepts={"concepts": ["convolution", "pooling"]},
             CoverageAssessment={"items": [{"concept": "convolution", "status": "covered", "evidence_quote": "slides learned filters over the image"},
                                           {"concept": "pooling", "status": "covered", "evidence_quote": "Max pooling then shrinks the maps"}]},
             CorrectnessAssessment={"incorrect_statements": []},
             RelevanceAssessment={"answers_the_question": True, "relevance": .9},
             RubricScoring={"awards": [{"criterion_id": "c1", "awarded_marks": 3, "reason": "Filters and feature maps explained", "evidence_quotes": ["slides learned filters over the image to build feature maps"]},
                                       {"criterion_id": "c2", "awarded_marks": 2, "reason": "Pooling explained", "evidence_quotes": ["Max pooling then shrinks the maps"]}]},
             StudentFeedback={"strengths": ["Clear"], "improvements": [], "overall_feedback": "Good."},
             VisualAssessment={"readable": True, "correctness": .8})
    d.update(over)
    return d


def inp(**over):
    d = dict(question_number=1, question_text="Explain how a CNN works.", topic="CNN", difficulty="Medium", max_marks=5, expected_answer="...",
             expected_concepts=["convolution", "pooling"], rubric=RUBRIC, answer_text=ANSWER, ocr_confidence=.95)
    d.update(over)
    return EvaluationInput(**d)


def test_alternative_wording_full_marks_and_twelve_nodes_run():
    p = Scripted(**base())
    r = evaluate_answer(p, inp())
    assert r.marks_awarded == 5 and not r.requires_human_review
    assert r.confidence > .7
    assert p.calls == ["eval_question_understanding", "eval_concepts", "eval_coverage", "eval_correctness", "eval_relevance", "eval_scoring", "eval_feedback"]


def test_overscoring_is_retried_then_clamped_and_flagged():
    bad = {"awards": [{"criterion_id": "c1", "awarded_marks": 7, "reason": "Too generous"}, {"criterion_id": "c2", "awarded_marks": 2, "reason": "ok pooling"}]}
    p = Scripted(**base(RubricScoring=[bad, bad]))
    r = evaluate_answer(p, inp())
    assert p.calls.count("eval_scoring") == 2
    assert r.marks_awarded == 5 and r.requires_human_review and any("awarded 7" in x for x in r.review_reasons)


def test_partial_answer_and_hallucinated_error_quotes_are_dropped():
    p = Scripted(**base(
        CoverageAssessment={"items": [{"concept": "convolution", "status": "covered"}, {"concept": "pooling", "status": "missing"}]},
        CorrectnessAssessment={"incorrect_statements": [{"quote": "CNNs are recurrent", "issue": "incorrect_fact", "explanation": "not in answer"}]},
        RubricScoring={"awards": [{"criterion_id": "c1", "awarded_marks": 3, "reason": "Convolution correct"}, {"criterion_id": "c2", "awarded_marks": 0, "reason": "Pooling is not mentioned at all"}]}))
    r = evaluate_answer(p, inp(answer_text="A CNN slides learned filters over the image to build feature maps."))
    assert r.marks_awarded == 3 and r.missing_points == ["pooling"]
    assert r.incorrect_statements == []  # the quoted error does not exist in the answer


def test_low_ocr_is_a_review_signal_not_missing_knowledge():
    p = Scripted(**base())
    r = evaluate_answer(p, inp(answer_text=ANSWER + " [illegible] [illegible]", ocr_confidence=.4, ocr_flags=["Low recognition confidence (40%)"]))
    assert r.requires_human_review and "Low recognition confidence (40%)" in r.review_reasons


def test_off_topic_high_score_is_challenged():
    p = Scripted(**base(RelevanceAssessment={"answers_the_question": False, "relevance": .1}))
    r = evaluate_answer(p, inp())
    assert p.calls.count("eval_scoring") == 2 and r.requires_human_review


def test_diagram_questions_use_page_images():
    from ai_engine.providers.base import ImageInput
    p = Scripted(**base())
    evaluate_answer(p, inp(contains_diagram=True, page_images=[ImageInput(b"x", "image/jpeg")]))
    assert "eval_visual" in p.calls
    r = evaluate_answer(Scripted(**base()), inp(contains_diagram=True))
    assert any("no page image" in x for x in r.review_reasons)


def test_challenge_recommendation_is_capped_and_escalates_when_unsure():
    p = Scripted(ArgumentAnalysis={"claim_summary": "valid alternative", "claim_type": "alternative_answer", "student_answer_supports_claim": True},
                 AlternativeValidity={"is_valid": True, "supported_by_sources": True, "reasoning": "fine"},
                 ChallengeRecommendation={"recommendation": "accept", "suggested_marks": 99, "reasoning": "The answer is valid and complete.", "confidence": .55})
    s = assess_challenge(p, ChallengeInput(category="missed_concept", disputed_criterion=None, explanation="I covered pooling", evidence=[], question_text="q",
                                           expected_answer="a", rubric_text="r", answer_text=ANSWER, evaluation_summary="", original_marks=3, max_marks=5))
    assert s["recommendation"].suggested_marks == 5 and s["escalated"]
