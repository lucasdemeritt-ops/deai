"""
Ledger.slash (off-chain bond reduction — VERIFICATION_PROTOCOL.md §13.5).
Pure unit tests against the in-memory Ledger.
"""

import pytest

from protocol.ledger import Ledger


def test_slash_reduces_balance_by_fraction():
    led = Ledger()
    led.record_completion("n", "t1", output_tokens=1000)  # 10 + 10 = 20 DAI
    before = led.balance("n")
    burned = led.slash("n", 0.25, reason="test")
    assert burned == pytest.approx(before * 0.25)
    assert led.balance("n") == pytest.approx(before * 0.75)


def test_slash_full_takes_everything():
    led = Ledger()
    led.record_completion("n", "t", 500)
    bal = led.balance("n")
    assert led.slash("n", 1.0) == pytest.approx(bal)
    assert led.balance("n") == 0.0


def test_slash_unknown_node_burns_nothing():
    assert Ledger().slash("never-seen", 0.5) == 0.0


def test_slash_zero_balance_is_idempotent():
    led = Ledger()
    led.record_completion("n", "t", 0)
    led.slash("n", 1.0)
    assert led.slash("n", 1.0) == 0.0


def test_slash_invalid_fraction_raises():
    led = Ledger()
    with pytest.raises(ValueError):
        led.slash("n", 0.0)
    with pytest.raises(ValueError):
        led.slash("n", -0.1)
    with pytest.raises(ValueError):
        led.slash("n", 1.5)


def test_record_completion_after_slash_accumulates_normally():
    led = Ledger()
    led.record_completion("n", "t1", 1000)
    led.slash("n", 0.5)
    led.record_completion("n", "t2", 1000)
    # After slash to half plus a new completion, balance > 0 and history grows.
    assert led.balance("n") > 0
