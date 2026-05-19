"""
ChainLedger — on-chain reward and reputation tracking.

Wraps the in-memory Ledger with real contract calls. When a task completes,
miners receive actual DEAI tokens minted to their wallet — not just an
in-memory number. The orchestrator wallet holds MINTER_ROLE on DeAIToken
(granted by deploy.js) so it can issue rewards directly.

Reward settlement (build-now #4): rewards are NOT minted per task. Earnings
accrue off-chain; once per epoch the orchestrator publishes a single
cumulative Merkle root and miners claim their own tokens from
MerkleDistributor. This removes the per-task hot MINTER_ROLE key, makes cost
O(epochs) not O(tasks), and decouples the reward path from the chain choice.

On-chain calls made by this module:
  MerkleDistributor.updateRoot(root)          — once per epoch (reward settle)
  SlashingContract.isEligible(wallet)         — gate before routing a task
  SlashingContract.recordCompletion(wallet)   — increment on-chain reputation
  SlashingContract.slash(wallet)              — burn stake on bad result

In-memory accounting (from Ledger) is still kept so /status and /earnings
endpoints continue to work without any extra RPC reads.

Usage:
    python protocol/orchestrator.py --chain \\
        --rpc-url http://localhost:8545 \\
        --token-contract 0x... \\
        --slashing-contract 0x... \\
        --payment-contract 0x... \\
        --orchestrator-key 0x...
"""

import json
import logging
from pathlib import Path

from web3 import Web3

from ledger import Ledger, BASE_REWARD, TOKEN_PER_OUTPUT
from merkle import build_tree, _norm as _norm_addr

log = logging.getLogger("chain_ledger")

_ABI_DIR = Path(__file__).parent.parent / "chain" / "abis"

# Reward amounts must match ledger.py exactly so on-chain and in-memory agree
_WEI = 10 ** 18


def _load_abi(name: str) -> list:
    with open(_ABI_DIR / f"{name}.json") as f:
        return json.load(f)


def _reward_wei(output_tokens: int) -> int:
    """Convert ledger reward formula to wei for on-chain minting. Must match
    ledger.record_completion exactly so on-chain and in-memory agree."""
    deai = BASE_REWARD + TOKEN_PER_OUTPUT * output_tokens
    return int(deai * _WEI)


class ChainLedger(Ledger):
    """
    Drop-in replacement for Ledger that adds live contract calls.
    Inherits all in-memory accounting so /status and /earnings
    endpoints work without extra RPC reads.
    """

    def __init__(
        self,
        rpc_url: str,
        orchestrator_key: str,
        token_addr: str,
        slashing_addr: str,
        payment_addr: str,
        distributor_addr: str,
    ):
        super().__init__()
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            raise RuntimeError(f"Cannot connect to RPC node at {rpc_url}")

        self.account = self.w3.eth.account.from_key(orchestrator_key)

        self.token = self.w3.eth.contract(
            address=Web3.to_checksum_address(token_addr),
            abi=_load_abi("DeAIToken"),
        )
        self.slashing = self.w3.eth.contract(
            address=Web3.to_checksum_address(slashing_addr),
            abi=_load_abi("SlashingContract"),
        )
        self.payment = self.w3.eth.contract(
            address=Web3.to_checksum_address(payment_addr),
            abi=_load_abi("PaymentContract"),
        )
        self.distributor = self.w3.eth.contract(
            address=Web3.to_checksum_address(distributor_addr),
            abi=_load_abi("MerkleDistributor"),
        )

        # Off-chain cumulative accrual: wallet -> total earned (wei).
        # Settled to chain as a Merkle root once per epoch (settle_epoch).
        self._accrued_wei: dict[str, int] = {}
        self.latest_root: str = "0x" + "00" * 32
        self.settled_epoch: int = 0
        self._latest_proofs: dict[str, dict] = {}

        log.info(
            f"ChainLedger ready  rpc={rpc_url}  "
            f"orchestrator={self.account.address}  "
            f"token={token_addr}  slashing={slashing_addr}  "
            f"distributor={distributor_addr}"
        )

    # ── Read calls (view functions — free, no gas) ────────────────────────────

    def is_eligible(self, wallet: str) -> bool:
        """
        Returns True if the miner is eligible to receive tasks.
        Fails open so a slow RPC doesn't kill routing.
        """
        try:
            return self.slashing.functions.isEligible(
                Web3.to_checksum_address(wallet)
            ).call()
        except Exception as e:
            log.warning(f"is_eligible RPC failed  wallet={wallet}  err={e} — routing anyway")
            return True

    # ── Write calls (state-changing — cost gas) ───────────────────────────────

    def _send_tx(self, fn) -> str:
        """Build, sign, and broadcast a transaction. Returns hex tx hash. Blocking."""
        tx = fn.build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "gas": 200_000,
            "gasPrice": self.w3.eth.gas_price,
        })
        signed  = self.w3.eth.account.sign_transaction(tx, self.account.key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        return self.w3.to_hex(tx_hash)

    def record_completion_onchain(self, wallet: str, output_tokens: int) -> str:
        """
        Accrue the reward OFF-CHAIN (no per-task mint) and record the
        completion on SlashingContract for reputation.

        The reward is added to the wallet's cumulative accrual and is settled
        on-chain later via settle_epoch() as a single Merkle root. This is the
        whole point of build-now #4: no hot MINTER_ROLE key, O(epochs) cost.

        Blocking — call via asyncio.to_thread from async code.
        """
        try:
            addr = Web3.to_checksum_address(wallet)
            self._accrued_wei[addr] = self._accrued_wei.get(addr, 0) + _reward_wei(output_tokens)
            log.info(
                f"accrue            wallet={wallet[:10]}...  "
                f"+{_reward_wei(output_tokens)/_WEI:.2f}  "
                f"cumulative={self._accrued_wei[addr]/_WEI:.2f}"
            )

            tx = self._send_tx(self.slashing.functions.recordCompletion(addr))
            log.info(f"recordCompletion  wallet={wallet[:10]}...  tx={tx[:18]}...")
            return tx
        except Exception as e:
            log.error(f"record_completion_onchain failed  wallet={wallet}  err={e}")
            return ""

    def settle_epoch(self) -> str:
        """
        Publish the current cumulative accrual as a single Merkle root on
        MerkleDistributor (one transaction for the whole network). Miners
        then claim their own tokens with the proof from claim_info().

        Idempotent when nothing changed (skips if the root is unchanged).
        Blocking — call via asyncio.to_thread from async code.
        """
        if not self._accrued_wei:
            return ""
        root, proofs = build_tree(self._accrued_wei)
        if root == self.latest_root:
            return ""
        try:
            tx = self._send_tx(
                self.distributor.functions.updateRoot(bytes.fromhex(root[2:]))
            )
            self.latest_root = root
            self._latest_proofs = proofs
            self.settled_epoch += 1
            log.info(
                f"settle epoch={self.settled_epoch}  wallets={len(proofs)}  "
                f"root={root[:18]}...  tx={tx[:18]}..."
            )
            return tx
        except Exception as e:
            log.error(f"settle_epoch failed  err={e}")
            return ""

    def claim_info(self, wallet: str) -> dict | None:
        """
        Everything a miner needs to claim from MerkleDistributor:
        cumulative amount (wei), Merkle proof, the settled root and epoch.
        None if this wallet has nothing in the latest settled root.
        """
        addr = _norm_addr(wallet)
        entry = self._latest_proofs.get(addr)
        if entry is None:
            return None
        return {
            "wallet": addr,
            "cumulative_wei": str(entry["amount"]),
            "cumulative_deai": entry["amount"] / _WEI,
            "proof": entry["proof"],
            "root": self.latest_root,
            "epoch": self.settled_epoch,
        }

    def slash_onchain(self, wallet: str) -> str:
        """
        Calls SlashingContract.slash — burns SLASH_AMOUNT from the miner's
        stake (or ejects if stake is zero).

        Blocking — call via asyncio.to_thread from async code.
        """
        try:
            tx = self._send_tx(
                self.slashing.functions.slash(Web3.to_checksum_address(wallet))
            )
            log.info(f"slash             wallet={wallet[:10]}...  tx={tx[:18]}...")
            return tx
        except Exception as e:
            log.error(f"slash_onchain failed  wallet={wallet}  err={e}")
            return ""
