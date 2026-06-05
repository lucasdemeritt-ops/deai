"""
Check a miner's on-chain status in SlashingContract.

Usage:
    python tests/check_miner_status.py 0x<WALLET_ADDRESS>

Reads from .env for RPC_URL and SLASHING_CONTRACT, or pass --rpc-url / --slashing-contract.
"""

import sys
import os
import argparse
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from web3 import Web3


_ABI_DIR = Path(__file__).parent.parent / "chain" / "abis"


def load_abi(name: str) -> list:
    with open(_ABI_DIR / f"{name}.json") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Check miner on-chain status")
    parser.add_argument("wallet", help="Miner wallet address (0x...)")
    parser.add_argument("--rpc-url", default=os.getenv("DAI_RPC_URL", "http://localhost:8545"))
    parser.add_argument("--slashing-contract", default=os.getenv("DAI_SLASHING_CONTRACT"))
    args = parser.parse_args()

    if not args.slashing_contract:
        print("ERROR: DAI_SLASHING_CONTRACT not set. Use --slashing-contract or set in .env")
        sys.exit(1)

    w3 = Web3(Web3.HTTPProvider(args.rpc_url))
    if not w3.is_connected():
        print(f"ERROR: Cannot connect to {args.rpc_url}")
        sys.exit(1)

    slashing = w3.eth.contract(
        address=Web3.to_checksum_address(args.slashing_contract),
        abi=load_abi("SlashingContract"),
    )

    wallet = Web3.to_checksum_address(args.wallet)
    record = slashing.functions.miners(wallet).call()
    eligible = slashing.functions.isEligible(wallet).call()

    stake, tasks_completed, times_slashed, ejected = record

    print(f"\nMiner: {wallet}")
    print(f"  stake:           {stake / 1e18:.4f} DAI")
    print(f"  tasks_completed: {tasks_completed}")
    print(f"  times_slashed:   {times_slashed}")
    print(f"  ejected:         {ejected}")
    print(f"  is_eligible:     {eligible}")


if __name__ == "__main__":
    main()
