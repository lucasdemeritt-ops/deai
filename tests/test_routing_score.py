"""
Routing must not give a score advantage for self-reported GPU/VRAM
(build-now #3). Model match and the idle round-robin tiebreaker stay.
"""

from types import SimpleNamespace

import orchestrator


def _node(models, gpu=False, vram_gb=None, last_task_time=0.0):
    return SimpleNamespace(
        info=SimpleNamespace(models=models, gpu=gpu, vram_gb=vram_gb),
        last_task_time=last_task_time,
    )


def test_gpu_claim_gives_no_score_advantage():
    cpu = _node(["llama3"], gpu=False, vram_gb=None, last_task_time=0.0)
    gpu = _node(["llama3"], gpu=True, vram_gb=80, last_task_time=0.0)
    assert orchestrator.score_node(cpu, "llama3") == orchestrator.score_node(gpu, "llama3")


def test_exact_model_still_beats_any():
    exact = _node(["llama3"], last_task_time=0.0)
    generic = _node(["any"], last_task_time=0.0)
    assert orchestrator.score_node(exact, "llama3") > orchestrator.score_node(generic, "llama3")


def test_unrunnable_model_rejected():
    n = _node(["mistral"], gpu=True, vram_gb=80)
    assert orchestrator.score_node(n, "llama3") == -1


def test_vram_does_not_change_score():
    lo = _node(["any"], gpu=True, vram_gb=4, last_task_time=0.0)
    hi = _node(["any"], gpu=True, vram_gb=80, last_task_time=0.0)
    assert orchestrator.score_node(lo, "llama3") == orchestrator.score_node(hi, "llama3")
