"""
ChainLedger — on-chain reward and reputation tracking.

Wraps the in-memory Ledger with real contract calls. When a task completes,
miners receive actual DEAI tokens minted to their wallet — not just an
in-memory number. The orchestrator wallet holds MINTER_ROLE on DeAIToken
(granted by deploy.js) so it can issue rewards directly.

On-chain calls made by this module:
  DeAIToken.mint(wallet, amount)              — real tokens sent to miner
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

from ledger import Ledger, BASE_REWARD, GPU_BONUS, TOKEN_PER_OUTPUT

log = logging.getLogger("chain_ledger")

_ABI_DIR = Path(__file__).parent.parent / "chain" / "abis"

# Reward amounts must match ledger.py exactly so on-chain and in-memory agree
_WEI = 10 ** 18


def _load_abi(name: str) -> list:
    with open(_ABI_DIR / f"{name}.json") as f:
        return json.load(f)


def _reward_wei(output_tokens: int, had_gpu: bool) -> int:
    """Convert ledger reward formula to wei for on-chain minting."""
    deai = BASE_REWARD + (GPU_BONUS if had_gpu else 0) + TOKEN_PER_OUTPUT * output_tokens
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

        log.info(
            f"ChainLedger ready  rpc={rpc_url}  "
            f"orchestrator={self.account.address}  "
            f"token={token_addr}  slashing={slashing_addr}"
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

    def record_completion_onchain(self, wallet: str, output_tokens: int, had_gpu: bool) -> str:
        """
        Mints DEAI reward tokens to the miner's wallet and records the
        completion on SlashingContract.

        Two transactions:
          1. DeAIToken.mint(wallet, reward_wei)
          2. SlashingContract.recordCompletion(wallet)

        Blocking — call via asyncio.to_thread from async code.
        """
        try:
            addr = Web3.to_checksum_address(wallet)
            reward = _reward_wei(output_tokens, had_gpu)

            tx1 = self._send_tx(self.token.functions.mint(addr, reward))
            log.info(f"mint              wallet={wallet[:10]}...  deai={reward/_WEI:.2f}  tx={tx1[:18]}...")

            tx2 = self._send_tx(self.slashing.functions.recordCompletion(addr))
            log.info(f"recordCompletion  wallet={wallet[:10]}...  tx={tx2[:18]}...")

            return tx1
        except Exception as e:
            log.error(f"record_completion_onchain failed  wallet={wallet}  err={e}")
            return ""

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
