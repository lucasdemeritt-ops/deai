"""
ChainLedger — on-chain reward and reputation tracking.

Wraps the in-memory Ledger with real contract calls to SlashingContract.
Token accounting still uses in-memory tracking until the full user-wallet
flow is implemented (PaymentContract requires users to hold and spend DEAI
tokens directly, which needs a front-end / wallet integration).

What this module does on-chain today:
  SlashingContract.isEligible(wallet)       — gate before routing a task
  SlashingContract.recordCompletion(wallet) — increment reputation on success
  SlashingContract.slash(wallet)            — burn stake on bad result

What stays in-memory (for now):
  Token earnings, leaderboard, per-node balance — unchanged from ledger.py
  PaymentContract calls — deferred until user wallets exist in the flow

Usage:
    python protocol/orchestrator.py --chain \\
        --rpc-url http://localhost:8545 \\
        --slashing-contract 0x... \\
        --payment-contract 0x... \\
        --orchestrator-key 0x...
"""

import json
import logging
from pathlib import Path

from web3 import Web3

from ledger import Ledger

log = logging.getLogger("chain_ledger")

_ABI_DIR = Path(__file__).parent.parent / "chain" / "abis"


def _load_abi(name: str) -> list:
    with open(_ABI_DIR / f"{name}.json") as f:
        return json.load(f)


class ChainLedger(Ledger):
    """
    Drop-in replacement for Ledger that adds live contract calls.
    Inherits all in-memory accounting so /status and /earnings
    endpoints work without any changes to the orchestrator's HTTP layer.
    """

    def __init__(
        self,
        rpc_url: str,
        orchestrator_key: str,
        slashing_addr: str,
        payment_addr: str,
    ):
        super().__init__()
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            raise RuntimeError(f"Cannot connect to RPC node at {rpc_url}")

        self.account = self.w3.eth.account.from_key(orchestrator_key)

        self.slashing = self.w3.eth.contract(
            address=Web3.to_checksum_address(slashing_addr),
            abi=_load_abi("SlashingContract"),
        )
        self.payment = self.w3.eth.contract(
            address=Web3.to_checksum_address(payment_addr),
            abi=_load_abi("PaymentContract"),
        )

        log.info(
            f"ChainLedger ready  rpc={rpc_url}  "
            f"orchestrator={self.account.address}  "
            f"slashing={slashing_addr}"
        )

    # ── Read calls (view functions — free, no gas) ────────────────────────────

    def is_eligible(self, wallet: str) -> bool:
        """
        Returns True if the miner's stake is above MIN_STAKE and they
        haven't been ejected. Fails open so a slow RPC doesn't kill routing.
        """
        try:
            return self.slashing.functions.isEligible(
                Web3.to_checksum_address(wallet)
            ).call()
        except Exception as e:
            log.warning(f"is_eligible RPC call failed  wallet={wallet}  err={e} — routing anyway")
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
        signed   = self.w3.eth.account.sign_transaction(tx, self.account.key)
        tx_hash  = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        return self.w3.to_hex(tx_hash)

    def record_completion_onchain(self, wallet: str) -> str:
        """
        Calls SlashingContract.recordCompletion — increments the miner's
        on-chain task counter and reputation score.

        Blocking — call via asyncio.to_thread from async code.
        """
        try:
            tx = self._send_tx(
                self.slashing.functions.recordCompletion(
                    Web3.to_checksum_address(wallet)
                )
            )
            log.info(f"recordCompletion  wallet={wallet[:10]}...  tx={tx[:18]}...")
            return tx
        except Exception as e:
            log.error(f"recordCompletion failed  wallet={wallet}  err={e}")
            return ""

    def slash_onchain(self, wallet: str) -> str:
        """
        Calls SlashingContract.slash — burns SLASH_AMOUNT (10 DEAI) from the
        miner's stake as a penalty for returning a bad/empty result.

        If the remaining stake falls below MIN_STAKE the miner is automatically
        ejected and will not receive further tasks.

        Blocking — call via asyncio.to_thread from async code.
        """
        try:
            tx = self._send_tx(
                self.slashing.functions.slash(
                    Web3.to_checksum_address(wallet)
                )
            )
            log.info(f"slash             wallet={wallet[:10]}...  tx={tx[:18]}...")
            return tx
        except Exception as e:
            log.error(f"slash failed  wallet={wallet}  err={e}")
            return ""
