"""
DeAI Verification
-----------------
The keystone seam. Replaces the old `mock_verify` non-empty check with a
pluggable `Verifier` interface so the network can evolve from "accept any
non-empty string" toward real Proof-of-Useful-Inference without touching the
orchestrator's dispatch logic again.

This module implements the Standard tier from docs/VERIFICATION.md:

    optimistic redundant execution + economic slashing

Only the *seam* and the *Standard-tier base case* are built here. Per
docs/VERIFICATION.md, the following are deliberately NOT solved yet and are
left as explicit hooks rather than faked:

  - the empirical comparison method (semantic embedding vs. judge model vs.
    logprob agreement) — `default_comparator` is a labelled placeholder;
  - committee escalation and blame attribution when two samples disagree —
    a 2-sample mismatch sets `escalation_required` and does NOT auto-slash,
    because slashing an honest provider on a false positive is flagged
    existential in the design doc;
  - the per-model reference inference stack that makes "two nodes disagree"
    a well-defined statement.

The Attested (TEE) and Proven (zkML) tiers are intentionally absent — they
are future tiers, not stubs.
"""

from __future__ import annotations

import difflib
import random
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional

from shared.schemas import Task, TaskResult


# ── Comparison ────────────────────────────────────────────────────────────────

_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WS.sub(" ", text.strip().lower())


def default_comparator(a: str, b: str) -> float:
    """
    Deterministic, dependency-free similarity in [0, 1].

    PLACEHOLDER. docs/VERIFICATION.md lists the real comparison method as an
    open, empirically-decided question (semantic embedding cosine vs. judge
    model vs. logprob agreement). This whitespace/case-normalized sequence
    ratio is good enough to (a) prove the seam end-to-end and (b) catch a node
    that returns garbage or swapped in a different, much smaller model. It is
    NOT the final comparator and must not be relied on for mainnet economics.
    """
    na, nb = _normalize(a), _normalize(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


@dataclass
class VerificationOutcome:
    accepted: bool
    method: str
    rechecked: bool = False
    agreement: Optional[float] = None
    escalation_required: bool = False
    detail: str = ""


# ── Verifier interface ────────────────────────────────────────────────────────

class Verifier(ABC):
    """
    Decision policy for a task result. The orchestrator owns the mechanics
    (node registry, WS dispatch, re-dispatch); the Verifier owns the policy:
    is this result well-formed, should it be rechecked, and do two samples
    agree.
    """

    @abstractmethod
    def well_formed(self, result: TaskResult) -> bool:
        """Cheap local gate. A malformed result never reaches recheck."""

    @abstractmethod
    def should_recheck(self, task: Task, result: TaskResult) -> bool:
        """Sampling decision — the optimistic protocol's probability `p`."""

    @abstractmethod
    def compare(
        self, task: Task, primary: TaskResult, redundant: TaskResult
    ) -> VerificationOutcome:
        """Tolerance comparison of a primary result against a redundant one."""


class ContentVerifier(Verifier):
    """
    The pre-existing behaviour, preserved exactly: accept any non-empty result,
    never recheck. This is the default so mock mode and CI are unchanged until
    an operator explicitly opts into redundant verification.
    """

    def well_formed(self, result: TaskResult) -> bool:
        return bool(result.content and result.content.strip())

    def should_recheck(self, task: Task, result: TaskResult) -> bool:
        return False

    def compare(
        self, task: Task, primary: TaskResult, redundant: TaskResult
    ) -> VerificationOutcome:
        # Unreachable while should_recheck is False; defined for completeness.
        return VerificationOutcome(accepted=True, method="content_only")


class RedundantExecutionVerifier(Verifier):
    """
    Standard tier (docs/VERIFICATION.md, "Optimistic protocol sketch").

    With probability `sample_rate` the orchestrator silently re-runs the task
    on a different node and asks this verifier to compare. Security is
    economic, not cryptographic: the node does not know which tasks are
    checked, so cheating is deterred when stake_at_risk * p > gain_per_cheat.
    """

    def __init__(
        self,
        sample_rate: float,
        agreement_threshold: float = 0.85,
        comparator: Optional[Callable[[str, str], float]] = None,
        rng: Optional[random.Random] = None,
    ):
        if not 0.0 <= sample_rate <= 1.0:
            raise ValueError("sample_rate must be in [0, 1]")
        if not 0.0 <= agreement_threshold <= 1.0:
            raise ValueError("agreement_threshold must be in [0, 1]")
        self.sample_rate = sample_rate
        self.agreement_threshold = agreement_threshold
        self._comparator = comparator or default_comparator
        self._rng = rng or random.Random()

    def well_formed(self, result: TaskResult) -> bool:
        return bool(result.content and result.content.strip())

    def should_recheck(self, task: Task, result: TaskResult) -> bool:
        if self.sample_rate <= 0.0:
            return False
        if self.sample_rate >= 1.0:
            return True
        return self._rng.random() < self.sample_rate

    def compare(
        self, task: Task, primary: TaskResult, redundant: TaskResult
    ) -> VerificationOutcome:
        score = self._comparator(primary.content, redundant.content)
        if score >= self.agreement_threshold:
            return VerificationOutcome(
                accepted=True,
                method="redundant_match",
                rechecked=True,
                agreement=score,
                detail=f"agreement {score:.3f} >= {self.agreement_threshold:.3f}",
            )
        # Two samples disagree. We cannot attribute blame with only two
        # samples, and slashing an honest provider on a false positive is
        # flagged existential in docs/VERIFICATION.md. So: reject this result
        # and require committee escalation. Auto-slashing is intentionally NOT
        # done here.
        return VerificationOutcome(
            accepted=False,
            method="redundant_mismatch",
            rechecked=True,
            agreement=score,
            escalation_required=True,
            detail=(
                f"agreement {score:.3f} < {self.agreement_threshold:.3f}; "
                "committee escalation required (not yet implemented)"
            ),
        )


def make_verifier(sample_rate: float, agreement_threshold: float = 0.85) -> Verifier:
    """
    sample_rate <= 0  → ContentVerifier (unchanged legacy behaviour, default)
    sample_rate >  0  → RedundantExecutionVerifier (optimistic Standard tier)
    """
    if sample_rate <= 0.0:
        return ContentVerifier()
    return RedundantExecutionVerifier(
        sample_rate=sample_rate, agreement_threshold=agreement_threshold
    )
