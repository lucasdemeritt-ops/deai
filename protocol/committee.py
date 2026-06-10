"""
Committee Escalation — verdict and parameters (VERIFICATION_PROTOCOL.md §13)
-----------------------------------------------------------------------------
Pure decision logic. The orchestrator owns the I/O (selecting nodes,
dispatching the same task, collecting responses, scheduling delayed slashes);
this module owns *what the verdict is* given primary, checker, and N
committee responses.

Tally rule (§13.4):
  - A committee response is a *primary vote* if it agrees with the primary
    (similarity >= threshold), else a *checker vote* if it agrees with the
    checker, else **ambiguous** — it counts toward *neither* side.
  - A side wins only with a quorum (``⌊N/2⌋ + 1``) of affirmative votes.
    Disagreement with the primary is NOT evidence for the checker: slashing
    requires the committee to actively corroborate the accusing side. If
    ambiguity (non-determinism, a degraded comparator, an outage) erodes
    either side below quorum, the verdict is UNRESOLVABLE — no pay, no slash.
    This keeps an infrastructure failure from ever slashing an honest node.
  - A response that clears the threshold against *both* sides counts as a
    primary vote (benefit of the doubt goes to the accused).
  - Ambiguous members are flagged for elevated ``p`` on their future tasks,
    but never slashed from a single event.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

# §13.8 defaults — "starting points; testnet-calibrated."
DEFAULT_COMMITTEE_SIZE = 3
DEFAULT_COMMITTEE_TIMEOUT_S = 120.0
DEFAULT_APPEAL_WINDOW_S = 3600.0
# §13.8 lists this as TBD per ECONOMICS.md §5. 0.10 = 10% of the node's
# unvested accrual; placeholder until empirical work sets it.
DEFAULT_SLASH_FRACTION = 0.10


class Verdict(str, Enum):
    PRIMARY_UPHELD = "primary_upheld"     # checker is the dishonest side
    CHECKER_UPHELD = "checker_upheld"     # primary is the dishonest side
    UNRESOLVABLE = "unresolvable"         # tie / no majority — no slash, no pay


@dataclass
class CommitteeOutcome:
    verdict: Verdict
    primary_votes: int
    checker_votes: int
    ambiguous_indexes: list = field(default_factory=list)
    detail: str = ""

    @property
    def dishonest_role(self) -> str | None:
        if self.verdict is Verdict.PRIMARY_UPHELD:
            return "checker"
        if self.verdict is Verdict.CHECKER_UPHELD:
            return "primary"
        return None


def quorum(committee_size: int) -> int:
    """Simple majority required for a verdict (§13.2)."""
    return committee_size // 2 + 1


def tally_votes(
    primary_content: str,
    checker_content: str,
    committee_contents: list[str],
    comparator: Callable[[str, str], float],
    threshold: float,
) -> CommitteeOutcome:
    """Compute the committee verdict per §13.4."""
    n = len(committee_contents)
    if n == 0:
        return CommitteeOutcome(
            verdict=Verdict.UNRESOLVABLE,
            primary_votes=0, checker_votes=0,
            detail="empty committee — no quorum",
        )

    primary_votes = 0
    checker_votes = 0
    ambiguous: list[int] = []
    for i, c in enumerate(committee_contents):
        if comparator(c, primary_content) >= threshold:
            primary_votes += 1          # agree-with-both also lands here:
        elif comparator(c, checker_content) >= threshold:  # doubt favours accused
            checker_votes += 1
        else:
            ambiguous.append(i)  # matches neither side — counts toward no one

    q = quorum(n)
    if primary_votes >= q and primary_votes > checker_votes:
        v = Verdict.PRIMARY_UPHELD
    elif checker_votes >= q and checker_votes > primary_votes:
        v = Verdict.CHECKER_UPHELD
    else:
        v = Verdict.UNRESOLVABLE

    return CommitteeOutcome(
        verdict=v,
        primary_votes=primary_votes,
        checker_votes=checker_votes,
        ambiguous_indexes=ambiguous,
        detail=f"votes primary={primary_votes} checker={checker_votes} quorum={q} N={n}",
    )
