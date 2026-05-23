"""
Verification instrumentation (#10): prompt-hash logging helper and the
mismatch-rate counters exposed at /status. Pure, no network.
"""

import orchestrator
from shared.schemas import Task, Message, Role


def _task(text: str) -> Task:
    return Task(model="m", messages=[Message(role=Role.user, content=text)])


def test_prompt_hash_is_deterministic():
    assert orchestrator._prompt_hash(_task("hello")) == orchestrator._prompt_hash(_task("hello"))


def test_prompt_hash_differs_by_content():
    assert orchestrator._prompt_hash(_task("a")) != orchestrator._prompt_hash(_task("b"))


def test_prompt_hash_is_short_and_not_the_raw_prompt():
    h = orchestrator._prompt_hash(_task("a secret prompt"))
    assert len(h) == 12
    assert "secret" not in h


def test_stats_exposes_verification_counters():
    for key in ("verify_checks", "verify_mismatches", "verify_skipped"):
        assert key in orchestrator.stats
