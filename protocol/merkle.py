"""
Merkle distributor tree — Python side of build-now #4.

Produces the cumulative-earnings Merkle root the orchestrator publishes once
per epoch, and the per-wallet proofs miners use to claim. The hashing MUST
match chain/contracts/MerkleDistributor.sol exactly:

  leaf  = keccak256( keccak256( abi.encode(address, uint256) ) )   (double hash)
  node  = keccak256( sorted(a, b) )                                (OZ sorted pair)

OpenZeppelin's MerkleProof.verify is agnostic to tree construction as long as
proofs are generated from the same tree and the pair hash is the sorted-pair
keccak — which is what this module does.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from eth_abi import encode as abi_encode
from eth_utils import keccak, to_canonical_address


def _leaf(address: str, amount: int) -> bytes:
    inner = keccak(abi_encode(["address", "uint256"], [address, int(amount)]))
    return keccak(inner)  # bytes.concat of one bytes32 == that bytes32


def _hash_pair(a: bytes, b: bytes) -> bytes:
    return keccak(a + b) if a <= b else keccak(b + a)


def _norm(address: str) -> str:
    # Canonical lowercase 0x address — stable sort key and stable leaf input.
    return "0x" + to_canonical_address(address).hex()


def build_tree(entries: Dict[str, int]) -> Tuple[str, Dict[str, dict]]:
    """
    entries: {wallet_address: cumulative_amount_wei}
    Returns (root_hex, {wallet: {"amount": int, "proof": [hex,...]}}).
    Empty input → ("0x" + 32 zero bytes, {}).
    """
    if not entries:
        return "0x" + ("00" * 32), {}

    # Canonical, deterministic leaf order (sorted by address).
    items = sorted(((_norm(a), int(v)) for a, v in entries.items()), key=lambda x: x[0])
    leaves = [_leaf(a, v) for a, v in items]

    # Build levels; track each leaf's path so we can emit proofs.
    levels: List[List[bytes]] = [leaves]
    while len(levels[-1]) > 1:
        cur = levels[-1]
        nxt: List[bytes] = []
        for i in range(0, len(cur), 2):
            if i + 1 < len(cur):
                nxt.append(_hash_pair(cur[i], cur[i + 1]))
            else:
                nxt.append(cur[i])  # lone node promoted unchanged
        levels.append(nxt)

    root = levels[-1][0]

    out: Dict[str, dict] = {}
    for idx, (addr, amount) in enumerate(items):
        proof: List[str] = []
        pos = idx
        for level in levels[:-1]:
            sib = pos ^ 1
            if sib < len(level):
                proof.append("0x" + level[sib].hex())
            pos //= 2
        out[addr] = {"amount": amount, "proof": proof}

    return "0x" + root.hex(), out


def verify(proof: List[str], root: str, address: str, amount: int) -> bool:
    """Mirror of MerkleProof.verify (sorted-pair) for tests / sanity checks."""
    h = _leaf(_norm(address), int(amount))
    for p in proof:
        h = _hash_pair(h, bytes.fromhex(p[2:] if p.startswith("0x") else p))
    return ("0x" + h.hex()) == (root if root.startswith("0x") else "0x" + root)
