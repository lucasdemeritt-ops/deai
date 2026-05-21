"""
Unit tests for protocol/chain_ledger.py.

Web3 and all contract calls are mocked — no RPC node, no Sepolia, no keys.
Tests cover the pure business logic: accrual, Merkle settlement, claim info,
eligibility, and slash routing.
"""

import sys
import os
from unittest.mock import MagicMock, patch

import pytest

# Valid-looking EVM addresses (40 hex chars) — eth_utils validates format
ADDR_ORCH  = "0x" + "ff" * 20
ADDR_MINER = "0x" + "aa" * 20
ADDR_ALICE = "0x" + "bb" * 20
ADDR_BOB   = "0x" + "cc" * 20
ADDR_BAD   = "0x" + "dd" * 20


@pytest.fixture(autouse=True)
def mock_web3_cls():
    """Patch chain_ledger.Web3 for the entire test so class-level calls
    (Web3.to_checksum_address) go through the mock too."""
    with patch("chain_ledger.Web3") as MockWeb3:
        mock_w3 = MagicMock()
        MockWeb3.return_value = mock_w3
        MockWeb3.HTTPProvider.return_value = MagicMock()
        # Pass addresses through unchanged so Merkle logic works correctly
        MockWeb3.to_checksum_address.side_effect = lambda x: x

        mock_w3.is_connected.return_value = True
        mock_w3.eth.account.from_key.return_value = MagicMock(
            address=ADDR_ORCH, key=b"\x00" * 32
        )
        mock_contract = MagicMock()
        mock_w3.eth.contract.return_value = mock_contract
        # estimate_gas returns plain ints so int(gas_est * 1.3) works correctly
        mock_contract.functions.slash.return_value.estimate_gas.return_value = 50_000
        mock_contract.functions.recordCompletion.return_value.estimate_gas.return_value = 50_000
        mock_contract.functions.updateRoot.return_value.estimate_gas.return_value = 50_000
        mock_contract.functions.claim.return_value.estimate_gas.return_value = 100_000
        # claimed() returns 0 (nothing claimed yet)
        mock_contract.functions.claimed.return_value.call.return_value = 0
        # distributor contract address
        mock_contract.address = "0x" + "44" * 20
        mock_w3.eth.get_block.return_value = {"baseFeePerGas": 1_000_000_000}
        mock_w3.eth.get_transaction_count.return_value = 0
        mock_w3.eth.account.sign_transaction.return_value = MagicMock(
            raw_transaction=b"\x00"
        )
        mock_w3.eth.send_raw_transaction.return_value = b"\xab\xcd"
        mock_w3.to_hex.return_value = "0xabcd1234"
        mock_w3.to_wei.side_effect = lambda val, unit: int(val * 1e9) if unit == "gwei" else val
        # keccak used for calldata encoding in claim_info
        mock_w3.keccak.return_value = bytes(4)

        yield MockWeb3, mock_w3


def _make_ledger(accrued: dict | None = None):
    from chain_ledger import ChainLedger
    ledger = ChainLedger(
        rpc_url="http://localhost:8545",
        orchestrator_key="0x" + "aa" * 32,
        token_addr="0x" + "11" * 20,
        slashing_addr="0x" + "22" * 20,
        payment_addr="0x" + "33" * 20,
        distributor_addr="0x" + "44" * 20,
    )
    if accrued:
        ledger._accrued_wei.update(accrued)
    return ledger


# ── Construction ───────────────────────────────────────────────────────────────

def test_construction_succeeds():
    ledger = _make_ledger()
    assert ledger is not None
    assert ledger._accrued_wei == {}
    assert ledger.settled_epoch == 0


def test_construction_fails_if_rpc_unreachable(mock_web3_cls):
    _, mock_w3 = mock_web3_cls
    mock_w3.is_connected.return_value = False
    from chain_ledger import ChainLedger
    with pytest.raises(RuntimeError, match="Cannot connect"):
        ChainLedger(
            rpc_url="http://bad:9999",
            orchestrator_key="0x" + "aa" * 32,
            token_addr="0x" + "11" * 20,
            slashing_addr="0x" + "22" * 20,
            payment_addr="0x" + "33" * 20,
            distributor_addr="0x" + "44" * 20,
        )


# ── record_completion_onchain ──────────────────────────────────────────────────

def test_record_completion_accrues_wei():
    ledger = _make_ledger()
    ledger.record_completion_onchain(ADDR_MINER, output_tokens=100)
    assert ADDR_MINER in ledger._accrued_wei
    assert ledger._accrued_wei[ADDR_MINER] > 0


def test_record_completion_accumulates_across_calls():
    ledger = _make_ledger()
    ledger.record_completion_onchain(ADDR_MINER, output_tokens=10)
    first = ledger._accrued_wei[ADDR_MINER]
    ledger.record_completion_onchain(ADDR_MINER, output_tokens=10)
    assert ledger._accrued_wei[ADDR_MINER] == first * 2


def test_record_completion_tracks_multiple_wallets():
    ledger = _make_ledger()
    ledger.record_completion_onchain(ADDR_ALICE, output_tokens=50)
    ledger.record_completion_onchain(ADDR_BOB, output_tokens=50)
    assert ADDR_ALICE in ledger._accrued_wei
    assert ADDR_BOB in ledger._accrued_wei
    assert ledger._accrued_wei[ADDR_ALICE] == ledger._accrued_wei[ADDR_BOB]


# ── settle_epoch ───────────────────────────────────────────────────────────────

def test_settle_epoch_skips_when_nothing_accrued():
    ledger = _make_ledger()
    assert ledger.settle_epoch() == ""
    assert ledger.settled_epoch == 0


def test_settle_epoch_publishes_root_and_increments_epoch():
    ledger = _make_ledger(accrued={ADDR_MINER: 10 ** 18})
    result = ledger.settle_epoch()
    assert result != ""
    assert ledger.settled_epoch == 1
    assert ledger.latest_root != "0x" + "00" * 32


def test_settle_epoch_skips_if_root_unchanged():
    ledger = _make_ledger(accrued={ADDR_MINER: 10 ** 18})
    ledger.settle_epoch()
    result = ledger.settle_epoch()
    assert result == ""
    assert ledger.settled_epoch == 1


def test_settle_epoch_updates_when_new_accrual():
    ledger = _make_ledger(accrued={ADDR_MINER: 10 ** 18})
    ledger.settle_epoch()
    first_root = ledger.latest_root

    ledger._accrued_wei[ADDR_MINER] += 5 * 10 ** 18
    ledger.settle_epoch()

    assert ledger.settled_epoch == 2
    assert ledger.latest_root != first_root


# ── claim_info ─────────────────────────────────────────────────────────────────

def test_claim_info_returns_none_before_settlement():
    ledger = _make_ledger()
    assert ledger.claim_info(ADDR_MINER) is None


def test_claim_info_returns_none_for_unknown_wallet():
    ledger = _make_ledger(accrued={ADDR_ALICE: 10 ** 18})
    ledger.settle_epoch()
    assert ledger.claim_info(ADDR_BOB) is None


def test_claim_info_returns_correct_structure():
    ledger = _make_ledger(accrued={ADDR_MINER: 10 ** 18})
    ledger.settle_epoch()
    info = ledger.claim_info(ADDR_MINER)
    assert info is not None
    assert info["wallet"] == ADDR_MINER
    assert info["cumulative_deai"] == pytest.approx(1.0)
    assert info["epoch"] == 1
    assert "proof" in info
    assert "root" in info
    assert "already_claimed_wei" in info
    assert "unclaimed_wei" in info
    assert "distributor_contract" in info
    assert "calldata" in info
    assert "gas_limit" in info
    # unclaimed == cumulative when nothing has been claimed yet
    assert int(info["unclaimed_wei"]) == int(info["cumulative_wei"])


# ── is_eligible ────────────────────────────────────────────────────────────────

def test_is_eligible_returns_true():
    ledger = _make_ledger()
    ledger.slashing.functions.isEligible.return_value.call.return_value = True
    assert ledger.is_eligible(ADDR_MINER) is True


def test_is_eligible_returns_false_for_ejected():
    ledger = _make_ledger()
    ledger.slashing.functions.isEligible.return_value.call.return_value = False
    assert ledger.is_eligible(ADDR_MINER) is False


def test_is_eligible_fails_open_on_rpc_error():
    ledger = _make_ledger()
    ledger.slashing.functions.isEligible.return_value.call.side_effect = Exception("timeout")
    assert ledger.is_eligible(ADDR_MINER) is True


# ── slash_onchain ──────────────────────────────────────────────────────────────

def test_slash_onchain_calls_contract():
    ledger = _make_ledger()
    result = ledger.slash_onchain(ADDR_BAD)
    assert result != ""
    ledger.slashing.functions.slash.assert_called_once()


def test_slash_onchain_returns_empty_on_error():
    ledger = _make_ledger()
    ledger.slashing.functions.slash.side_effect = Exception("revert")
    assert ledger.slash_onchain(ADDR_BAD) == ""


# ── broadcast_tx ───────────────────────────────────────────────────────────────

def test_broadcast_tx_returns_hash():
    ledger = _make_ledger()
    result = ledger.broadcast_tx("0xdeadbeef")
    assert result == "0xabcd1234"
    ledger.w3.eth.send_raw_transaction.assert_called_once_with(bytes.fromhex("deadbeef"))


def test_broadcast_tx_strips_0x_prefix():
    ledger = _make_ledger()
    ledger.broadcast_tx("deadbeef")
    ledger.w3.eth.send_raw_transaction.assert_called_once_with(bytes.fromhex("deadbeef"))
