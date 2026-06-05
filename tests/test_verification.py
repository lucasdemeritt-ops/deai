"""
Unit tests for the verification seam (docs/VERIFICATION.md, build-now #2).
Pure logic — no network, no nodes, no test-token budget.
"""

import random

import pytest

from shared.schemas import Message, Role, Task, TaskResult
from protocol.verification import (
    ContentVerifier,
    RedundantExecutionVerifier,
    Verifier,
    VerificationOutcome,
    default_comparator,
    make_verifier,
)


def _task() -> Task:
    return Task(model="llama3", messages=[Message(role=Role.user, content="hi")])


def _result(content: str, node_id: str = "node-a") -> TaskResult:
    return TaskResult(
        task_id="t1", node_id=node_id, content=content, tokens_used=len(content.split())
    )


# ── default_comparator ────────────────────────────────────────────────────────

def test_comparator_identical_is_one():
    assert default_comparator("Paris is the capital.", "Paris is the capital.") == 1.0


def test_comparator_whitespace_and_case_insensitive():
    assert default_comparator("  Hello   World ", "hello world") == 1.0


def test_comparator_both_empty_is_one():
    assert default_comparator("", "   ") == 1.0


def test_comparator_one_empty_is_zero():
    assert default_comparator("a real answer", "") == 0.0


def test_comparator_garbage_is_low():
    score = default_comparator(
        "The capital of France is Paris.", "42 lkjsdf qwerty zzz"
    )
    assert score < 0.85


def test_comparator_range():
    s = default_comparator("the quick brown fox", "the quick red fox")
    assert 0.0 <= s <= 1.0


# ── ContentVerifier (legacy default) ──────────────────────────────────────────

def test_content_verifier_well_formed():
    v = ContentVerifier()
    assert v.well_formed(_result("something"))
    assert not v.well_formed(_result(""))
    assert not v.well_formed(_result("   \n\t "))


def test_content_verifier_never_rechecks():
    v = ContentVerifier()
    assert all(
        v.should_recheck(_task(), _result("x")) is False for _ in range(100)
    )


def test_make_verifier_zero_is_content_verifier():
    assert isinstance(make_verifier(0.0), ContentVerifier)
    assert isinstance(make_verifier(-1.0), ContentVerifier)
    assert isinstance(make_verifier(0.1), RedundantExecutionVerifier)


# ── RedundantExecutionVerifier ────────────────────────────────────────────────

def test_redundant_rejects_invalid_params():
    with pytest.raises(ValueError):
        RedundantExecutionVerifier(sample_rate=1.5)
    with pytest.raises(ValueError):
        RedundantExecutionVerifier(sample_rate=0.5, agreement_threshold=2.0)


def test_sample_rate_zero_never_rechecks():
    v = RedundantExecutionVerifier(sample_rate=0.0)
    assert all(not v.should_recheck(_task(), _result("x")) for _ in range(100))


def test_sample_rate_one_always_rechecks():
    v = RedundantExecutionVerifier(sample_rate=1.0)
    assert all(v.should_recheck(_task(), _result("x")) for _ in range(100))


def test_sample_rate_partial_is_mixed_and_seeded():
    v = RedundantExecutionVerifier(sample_rate=0.5, rng=random.Random(42))
    draws = [v.should_recheck(_task(), _result("x")) for _ in range(200)]
    assert any(draws) and not all(draws)
    # Same seed → identical sequence (deterministic for tests/replay).
    v2 = RedundantExecutionVerifier(sample_rate=0.5, rng=random.Random(42))
    assert draws == [v2.should_recheck(_task(), _result("x")) for _ in range(200)]


def test_two_honest_nodes_agree():
    """Two mock nodes return the same answer → accepted."""
    v = RedundantExecutionVerifier(sample_rate=1.0)
    answer = "The capital of France is Paris."
    outcome = v.compare(_task(), _result(answer, "node-a"), _result(answer, "node-b"))
    assert isinstance(outcome, VerificationOutcome)
    assert outcome.accepted
    assert outcome.method == "redundant_match"
    assert outcome.rechecked
    assert outcome.agreement == pytest.approx(1.0)
    assert outcome.escalation_required is False


def test_cheating_node_is_caught_and_escalates():
    """Primary node returns garbage, honest checker disagrees → not accepted."""
    v = RedundantExecutionVerifier(sample_rate=1.0)
    primary = _result("42", "cheater")
    checker = _result("The capital of France is Paris.", "honest")
    outcome = v.compare(_task(), primary, checker)
    assert outcome.accepted is False
    assert outcome.method == "redundant_mismatch"
    assert outcome.escalation_required is True
    # 2-sample mismatch must not blame/slash a specific node here.
    assert "escalation" in outcome.detail.lower()


def test_verifier_is_abstract():
    with pytest.raises(TypeError):
        Verifier()  # cannot instantiate the interface directly


# ── Threshold boundary calibration (#10, default threshold = 0.85) ────────────
#
# Static string pairs that bracket the 0.85 boundary. Acts as a canary if the
# threshold or comparator algorithm changes without intent.

_THRESHOLD = 0.85


class TestThresholdBoundary:
    def setup_method(self):
        self.v = RedundantExecutionVerifier(sample_rate=1.0, agreement_threshold=_THRESHOLD)

    # ── Pairs that should PASS (score >= 0.85) ────────────────────────────────

    def test_identical_strings_pass(self):
        a = "The capital of France is Paris."
        outcome = self.v.compare(_task(), _result(a, "n1"), _result(a, "n2"))
        assert outcome.accepted
        assert outcome.agreement == pytest.approx(1.0)

    def test_minor_punctuation_difference_passes(self):
        a = "The capital of France is Paris."
        b = "The capital of France is Paris"   # no trailing period
        score = default_comparator(a, b)
        assert score >= _THRESHOLD, f"Expected >= {_THRESHOLD}, got {score:.3f}"
        outcome = self.v.compare(_task(), _result(a, "n1"), _result(b, "n2"))
        assert outcome.accepted

    def test_trivial_capitalisation_difference_passes(self):
        a = "Python was created in 1991 by Guido van Rossum."
        b = "Python was created in 1991 by Guido Van Rossum."
        score = default_comparator(a, b)
        assert score >= _THRESHOLD, f"Expected >= {_THRESHOLD}, got {score:.3f}"
        outcome = self.v.compare(_task(), _result(a, "n1"), _result(b, "n2"))
        assert outcome.accepted

    # ── Pairs that should FAIL (score < 0.85) ────────────────────────────────

    def test_completely_different_content_fails(self):
        a = "The capital of France is Paris."
        b = "Machine learning is a subset of artificial intelligence."
        score = default_comparator(a, b)
        assert score < _THRESHOLD, f"Expected < {_THRESHOLD}, got {score:.3f}"
        outcome = self.v.compare(_task(), _result(a, "n1"), _result(b, "n2"))
        assert not outcome.accepted
        assert outcome.escalation_required

    def test_partial_answer_vs_full_answer_fails(self):
        a = "Python is a high-level, interpreted programming language known for its readability."
        b = "Python."
        score = default_comparator(a, b)
        assert score < _THRESHOLD, f"Expected < {_THRESHOLD}, got {score:.3f}"
        outcome = self.v.compare(_task(), _result(a, "n1"), _result(b, "n2"))
        assert not outcome.accepted

    def test_empty_vs_nonempty_fails(self):
        a = "The answer is 42."
        outcome = self.v.compare(_task(), _result(a, "n1"), _result("", "n2"))
        assert not outcome.accepted

    # ── Threshold is configurable ─────────────────────────────────────────────

    def test_custom_threshold_lower_accepts_more(self):
        a = "The capital of France is Paris."
        b = "Paris is the capital city of France, located in northern Europe."
        permissive = RedundantExecutionVerifier(sample_rate=1.0, agreement_threshold=0.3)
        assert permissive.compare(_task(), _result(a, "n1"), _result(b, "n2")).accepted

    def test_strict_threshold_rejects_near_matches(self):
        a = "The capital of France is Paris."
        b = "The capital of France is Paris"   # no period
        strict = RedundantExecutionVerifier(sample_rate=1.0, agreement_threshold=1.0)
        outcome = strict.compare(_task(), _result(a, "n1"), _result(b, "n2"))
        assert not outcome.accepted
