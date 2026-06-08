"""
Committee verdict logic (VERIFICATION_PROTOCOL.md §13.4). Pure unit tests —
no orchestrator, no nodes, no network. Exercises every branch of §13.4 +
the §13.4 example.
"""

import pytest

from protocol.committee import (
    CommitteeOutcome, DEFAULT_COMMITTEE_SIZE, DEFAULT_SLASH_FRACTION,
    Verdict, quorum, tally_votes,
)


# Simple binary comparator: 1.0 if equal (after strip+lower), else 0.0. Lets
# us exactly control which side each committee member "agrees with."
def cmp(a: str, b: str) -> float:
    return 1.0 if a.strip().lower() == b.strip().lower() else 0.0


PRIMARY = "Paris."
CHECKER = "42."
GARBAGE = "qwerty"
T = 0.85


# ── quorum ────────────────────────────────────────────────────────────────────

def test_quorum_simple_majority():
    assert quorum(1) == 1
    assert quorum(3) == 2
    assert quorum(5) == 3
    assert quorum(7) == 4


# ── §13.4 example: 3-node, primary 2 / checker 1 → primary upheld ────────────

def test_primary_upheld_example_from_spec():
    out = tally_votes(PRIMARY, CHECKER, [PRIMARY, PRIMARY, CHECKER], cmp, T)
    assert out.verdict is Verdict.PRIMARY_UPHELD
    assert out.primary_votes == 2 and out.checker_votes == 1
    assert out.dishonest_role == "checker"
    assert out.ambiguous_indexes == []


def test_checker_upheld_primary_dishonest():
    out = tally_votes(PRIMARY, CHECKER, [CHECKER, CHECKER, PRIMARY], cmp, T)
    assert out.verdict is Verdict.CHECKER_UPHELD
    assert out.primary_votes == 1 and out.checker_votes == 2
    assert out.dishonest_role == "primary"


def test_unanimous_primary_upheld():
    out = tally_votes(PRIMARY, CHECKER, [PRIMARY] * 5, cmp, T)
    assert out.verdict is Verdict.PRIMARY_UPHELD
    assert out.primary_votes == 5 and out.checker_votes == 0


def test_unanimous_checker_upheld():
    out = tally_votes(PRIMARY, CHECKER, [CHECKER] * 5, cmp, T)
    assert out.verdict is Verdict.CHECKER_UPHELD


# ── ambiguous members (match neither side) — §13.4 note ──────────────────────

def test_ambiguous_member_counts_as_checker_vote_and_is_flagged():
    # Committee: one agrees with primary, one matches neither (ambiguous), one
    # agrees with checker. By binary rule, checker votes = 2, primary = 1 →
    # checker upheld. The ambiguous one is flagged separately.
    out = tally_votes(PRIMARY, CHECKER, [PRIMARY, GARBAGE, CHECKER], cmp, T)
    assert out.verdict is Verdict.CHECKER_UPHELD
    assert out.primary_votes == 1 and out.checker_votes == 2
    assert out.ambiguous_indexes == [1]


def test_all_committee_members_ambiguous():
    # All three match neither — checker votes = 3, all flagged.
    out = tally_votes(PRIMARY, CHECKER, [GARBAGE, GARBAGE, GARBAGE], cmp, T)
    assert out.verdict is Verdict.CHECKER_UPHELD
    assert out.ambiguous_indexes == [0, 1, 2]


# ── tie / unresolvable ───────────────────────────────────────────────────────

def test_even_committee_tie_is_unresolvable():
    out = tally_votes(PRIMARY, CHECKER, [PRIMARY, CHECKER], cmp, T)
    assert out.verdict is Verdict.UNRESOLVABLE
    assert out.dishonest_role is None


def test_empty_committee_is_unresolvable():
    out = tally_votes(PRIMARY, CHECKER, [], cmp, T)
    assert out.verdict is Verdict.UNRESOLVABLE
    assert "empty committee" in out.detail.lower()


# ── outcome surface ──────────────────────────────────────────────────────────

def test_outcome_detail_includes_vote_counts():
    out = tally_votes(PRIMARY, CHECKER, [PRIMARY, PRIMARY, CHECKER], cmp, T)
    assert "primary=2" in out.detail and "checker=1" in out.detail
    assert "quorum=2" in out.detail
    assert "N=3" in out.detail


def test_dishonest_role_none_on_unresolvable():
    out = tally_votes(PRIMARY, CHECKER, [], cmp, T)
    assert out.dishonest_role is None


# ── defaults exposed ─────────────────────────────────────────────────────────

def test_defaults_are_sensible():
    assert DEFAULT_COMMITTEE_SIZE % 2 == 1
    assert DEFAULT_COMMITTEE_SIZE >= 3
    assert 0.0 < DEFAULT_SLASH_FRACTION < 1.0
