"""
Slash test helper — a deliberately bad node.

Connects to the orchestrator, registers with a given wallet address, waits for
one task, and returns an EMPTY content string. The orchestrator's
`verifier.well_formed()` check will reject the empty result and call
`_slash_for_bad_result`, which fires `SlashingContract.slash(wallet)` in chain
mode.

Usage:
    python tests/slash_test_node.py --wallet 0x<MINER_WALLET>
    python tests/slash_test_node.py  # generates a fresh throwaway wallet

The script exits after the first task completes (or times out after 60s).

Run alongside:
    python protocol/orchestrator.py --chain --settle-interval 15
"""

import asyncio
import json
import logging
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uuid
import websockets
from shared.schemas import NodeInfo, WSMessage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bad_node")


async def run_bad_node(orchestrator_url: str, wallet: str):
    node_info = NodeInfo(
        node_id=f"bad-node-{uuid.uuid4().hex[:8]}",
        models=["any"],
        gpu=False,
        wallet=wallet,
    )

    log.info(f"Bad node wallet:    {wallet}")
    log.info(f"Connecting to:      {orchestrator_url}")
    log.info("Will return EMPTY content on first task to trigger slash")

    async with websockets.connect(orchestrator_url, ping_interval=None) as ws:
        register_msg = WSMessage(type="register", payload=node_info.model_dump())
        await ws.send(register_msg.model_dump_json())

        raw = await ws.recv()
        ack = json.loads(raw)
        if ack.get("type") != "ack":
            log.error(f"Registration failed: {ack}")
            return

        log.info(f"Registered  node_id={node_info.node_id}")
        log.info("Waiting for a task (send a request to /v1/chat/completions)...")

        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=60.0)
        except asyncio.TimeoutError:
            log.error("No task received within 60s — did you send a request?")
            return

        msg = json.loads(raw)
        if msg.get("type") != "task":
            log.warning(f"Expected 'task', got: {msg.get('type')}")
            return

        task_id = msg["payload"]["task_id"]
        log.info(f"Task received  id={task_id}")
        log.info("Returning EMPTY content (deliberate bad result)...")

        # Empty content — `verifier.well_formed()` returns False → slash fires
        result_msg = WSMessage(
            type="task_complete",
            payload={
                "task_id": task_id,
                "node_id": node_info.node_id,
                "content": "",
                "tokens_used": 0,
            }
        )
        await ws.send(result_msg.model_dump_json())
        log.info("Empty result sent. Orchestrator should slash this wallet.")
        log.info("Check orchestrator logs for: 'slash  wallet=...'")
        await asyncio.sleep(2.0)  # give orchestrator time to fire the slash tx


def main():
    parser = argparse.ArgumentParser(description="Bad node for slash testing")
    parser.add_argument(
        "--wallet",
        default=None,
        help="Miner wallet address. If omitted, a fresh throwaway wallet is generated.",
    )
    parser.add_argument(
        "--orchestrator",
        default="ws://127.0.0.1:8000/ws/node",
        help="Orchestrator WebSocket URL",
    )
    args = parser.parse_args()

    wallet = args.wallet
    if wallet is None:
        try:
            from web3 import Web3
            acct = Web3().eth.account.create()
            wallet = acct.address
            log.info(f"Generated throwaway wallet: {wallet}")
            log.info("(This wallet has no stake — it will be ejected immediately)")
        except ImportError:
            wallet = "0x0000000000000000000000000000000000000BAD"
            log.info(f"web3 not available; using placeholder wallet: {wallet}")

    asyncio.run(run_bad_node(args.orchestrator, wallet))


if __name__ == "__main__":
    main()
