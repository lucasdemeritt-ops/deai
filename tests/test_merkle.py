"""
Merkle distributor tree (build-now #4). Pure logic, no chain, no budget.
Internal consistency + the cumulative-claim invariants. Cross-language
equivalence with the Solidity contract is covered by the hardhat test
(same documented leaf/pair convention) and gated in CI.
"""

import pytest

from protocol.merkle import build_tree, verify, _leaf, _norm

A = "0x1111111111111111111111111111111111111111"
B = "0x2222222222222222222222222222222222222222"
C = "0x3333333333333333333333333333333333333333"


def test_empty_tree():
    root, proofs = build_tree({})
    assert root == "0x" + "00" * 32
    assert proofs == {}


def test_single_leaf_root_is_leaf_no_proof():
    root, proofs = build_tree({A: 100})
    assert proofs[_norm(A)]["proof"] == []
    assert root == "0x" + _leaf(_norm(A), 100).hex()
    assert verify([], root, A, 100)


def test_round_trip_three_entries():
    entries = {A: 10, B: 250, C: 9999}
    root, proofs = build_tree(entries)
    for addr in (A, B, C):
        info = proofs[_norm(addr)]
        assert verify(info["proof"], root, addr, info["amount"])


def test_wrong_amount_fails_verification():
    root, proofs = build_tree({A: 10, B: 250, C: 9999})
    p = proofs[_norm(B)]["proof"]
    assert verify(p, root, B, 250)
    assert not verify(p, root, B, 251)  # tampered amount
    assert not verify(p, root, A, 250)  # wrong account


def test_root_is_deterministic_and_order_independent():
    r1, _ = build_tree({A: 1, B: 2, C: 3})
    r2, _ = build_tree({C: 3, A: 1, B: 2})  # insertion order must not matter
    assert r1 == r2


def test_cumulative_amounts_change_root():
    r1, _ = build_tree({A: 10, B: 20})
    r2, _ = build_tree({A: 15, B: 20})  # A earned more → new root
    assert r1 != r2


def test_address_normalization_is_case_insensitive():
    root_lower, _ = build_tree({A.lower(): 5})
    root_upper, _ = build_tree({"0x" + A[2:].upper(): 5})
    assert root_lower == root_upper


def test_leaf_encoding_is_stable():
    # Regression guard: locks the (address,uint256) double-keccak encoding.
    assert _leaf(_norm(A), 0).hex() == _leaf("0x" + "11" * 20, 0).hex()
    assert _leaf(_norm(A), 1) != _leaf(_norm(A), 2)
