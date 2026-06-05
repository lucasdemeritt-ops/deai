"""
DAI Earnings Ledger
--------------------
Tracks token balances and earnings history for every node.

Token economy (interim — flat rate, tunable):
  BASE_REWARD      = 10 tokens per completed task
  TOKEN_PER_OUTPUT = +0.01 tokens per output token generated

Hardware (GPU/VRAM) is intentionally NOT rewarded. It is self-reported by
the node and unverified, so paying for it rewards an unprovable claim — the
same anti-pattern removed from mock_verify. Real capability will instead come
from measured, verified delivered work (the deferred benchmark/tier system —
see docs/VERIFICATION.md build-now #3 and docs/VERIFICATION_PROTOCOL.md §1).

Honest scoping note: `output_tokens` is itself a node self-report and is not
verified yet either. That is a work-claim (not a hardware-claim), tracked
separately, and deliberately out of scope for this change.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List


# ── Reward constants (easy to tune) ──────────────────────────────────────────

BASE_REWARD = 10.0        # tokens per completed task
TOKEN_PER_OUTPUT = 0.01   # tokens per output token generated


@dataclass
class EarningEvent:
    task_id: str
    tokens_earned: float
    output_tokens: int
    timestamp: float = field(default_factory=time.time)


@dataclass
class NodeBalance:
    node_id: str
    balance: float = 0.0
    total_earned: float = 0.0
    history: List[EarningEvent] = field(default_factory=list)

    def record(self, event: EarningEvent):
        self.balance += event.tokens_earned
        self.total_earned += event.tokens_earned
        self.history.append(event)

    def summary(self) -> dict:
        return {
            "node_id": self.node_id,
            "balance": round(self.balance, 4),
            "total_earned": round(self.total_earned, 4),
            "tasks_paid": len(self.history),
            "last_earning": round(self.history[-1].tokens_earned, 4) if self.history else None,
        }


class Ledger:
    def __init__(self):
        self._balances: Dict[str, NodeBalance] = {}

    def _ensure(self, node_id: str) -> NodeBalance:
        if node_id not in self._balances:
            self._balances[node_id] = NodeBalance(node_id=node_id)
        return self._balances[node_id]

    def record_completion(self, node_id: str, task_id: str, output_tokens: int) -> float:
        """Calculate and record earnings for a completed task. Returns tokens earned."""
        earned = BASE_REWARD + output_tokens * TOKEN_PER_OUTPUT

        event = EarningEvent(
            task_id=task_id,
            tokens_earned=earned,
            output_tokens=output_tokens,
        )
        self._ensure(node_id).record(event)
        return earned

    def balance(self, node_id: str) -> float:
        return self._balances.get(node_id, NodeBalance(node_id=node_id)).balance

    def summary(self, node_id: str) -> dict:
        return self._ensure(node_id).summary()

    def all_balances(self) -> List[dict]:
        return sorted(
            [b.summary() for b in self._balances.values()],
            key=lambda x: x["total_earned"],
            reverse=True,
        )

    def network_totals(self) -> dict:
        total_paid = sum(b.total_earned for b in self._balances.values())
        total_tasks = sum(len(b.history) for b in self._balances.values())
        return {
            "total_tokens_paid_out": round(total_paid, 4),
            "total_tasks_rewarded": total_tasks,
            "unique_nodes_paid": len(self._balances),
        }
