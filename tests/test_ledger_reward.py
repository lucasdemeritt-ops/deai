"""
Reward must not depend on self-reported hardware (build-now #3).
The GPU bonus is gone; pay = BASE_REWARD + output_tokens * TOKEN_PER_OUTPUT.
"""

import inspect

import pytest

from protocol.ledger import BASE_REWARD, TOKEN_PER_OUTPUT, Ledger


def test_reward_formula_has_no_hardware_term():
    led = Ledger()
    earned = led.record_completion(node_id="n1", task_id="t1", output_tokens=100)
    assert earned == pytest.approx(BASE_REWARD + 100 * TOKEN_PER_OUTPUT)
    assert led.balance("n1") == pytest.approx(earned)


def test_record_completion_no_longer_accepts_had_gpu():
    """The unverified hardware input is removed from the API, not just ignored."""
    led = Ledger()
    sig = inspect.signature(led.record_completion)
    assert "had_gpu" not in sig.parameters
    with pytest.raises(TypeError):
        led.record_completion(node_id="n", task_id="t", output_tokens=1, had_gpu=True)


def test_two_nodes_same_work_earn_identically():
    led = Ledger()
    a = led.record_completion(node_id="gpu-claimer", task_id="t1", output_tokens=50)
    b = led.record_completion(node_id="cpu-only", task_id="t2", output_tokens=50)
    assert a == b  # hardware claims can no longer change pay


def test_no_gpu_bonus_symbol_exported():
    import protocol.ledger as L
    assert not hasattr(L, "GPU_BONUS")
