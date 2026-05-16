"""
DeAI Node Client
----------------
What a miner runs to join the network.

The node:
  1. Connects to the orchestrator over WebSocket
  2. Registers its capabilities (what models it supports, hardware info)
  3. Waits for task assignments
  4. Executes inference (mocked in Phase 1 — real model support in Phase 2)
  5. Returns results and waits for the next task
  6. Sends heartbeats to stay registered

Run:
    python compute/node.py
    python compute/node.py --models llama3,mistral --gpu
    python compute/node.py --orchestrator ws://somehost:8000/ws/node
"""

import asyncio
import json
import logging
import random
import socket
import time
import uuid
import argparse
import os
import sys

import websockets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.schemas import NodeInfo, WSMessage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("node")

HEARTBEAT_INTERVAL = 15  # seconds


# ── Mock inference engine ─────────────────────────────────────────────────────

async def run_inference(model: str, messages: list, max_tokens: int, temperature: float) -> tuple[str, int]:
    """
    Phase 1 mock: simulate processing time and return a plausible response.
    Phase 2: swap this for Ollama, llama.cpp, or any model runner.
    """
    # Simulate GPU/CPU processing time (0.5–2.5 seconds)
    processing_time = random.uniform(0.5, 2.5)
    await asyncio.sleep(processing_time)

    # Pull the last user message to make the response feel contextual
    last_user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_msg = m.get("content", "")
            break

    # Generate a mock response
    responses = [
        f"[{model} @ DeAI node] I've processed your request: \"{last_user_msg[:60]}{'...' if len(last_user_msg) > 60 else ''}\". This is a mock response — real inference coming in Phase 2.",
        f"[{model} @ DeAI node] Understood. You asked: \"{last_user_msg[:60]}{'...' if len(last_user_msg) > 60 else ''}\". In the full network, a real model would respond here.",
        f"[{model} @ DeAI node] Mock inference complete. Query received and processed in {processing_time:.2f}s. Real model integration arrives in Phase 2.",
    ]
    content = random.choice(responses)
    tokens_used = len(content.split()) + len(last_user_msg.split())

    return content, tokens_used


# ── Main node loop ────────────────────────────────────────────────────────────

async def run_node(orchestrator_url: str, node_info: NodeInfo):
    log.info(f"Connecting to orchestrator at {orchestrator_url}")
    log.info(f"Node ID: {node_info.node_id}")
    log.info(f"Models:  {node_info.models}")
    log.info(f"GPU:     {node_info.gpu}")

    backoff = 1
    while True:
        try:
            async with websockets.connect(orchestrator_url, ping_interval=None) as ws:
                backoff = 1  # reset on successful connect

                # Register with the orchestrator
                register_msg = WSMessage(type="register", payload=node_info.model_dump())
                await ws.send(register_msg.model_dump_json())

                raw = await ws.recv()
                ack = json.loads(raw)
                if ack.get("type") == "ack":
                    log.info(f"Registered successfully. {ack['payload'].get('message', '')}")
                else:
                    log.error(f"Unexpected registration response: {ack}")
                    return

                # Heartbeat task runs in parallel with main loop
                async def heartbeat():
                    while True:
                        await asyncio.sleep(HEARTBEAT_INTERVAL)
                        try:
                            hb = WSMessage(type="heartbeat", payload={"node_id": node_info.node_id})
                            await ws.send(hb.model_dump_json())
                        except Exception:
                            break

                heartbeat_task = asyncio.create_task(heartbeat())

                log.info("Waiting for tasks...")

                try:
                    async for raw in ws:
                        msg = json.loads(raw)

                        if msg.get("type") == "task":
                            payload = msg["payload"]
                            task_id = payload["task_id"]
                            model = payload["model"]
                            messages = payload["messages"]
                            max_tokens = payload.get("max_tokens", 512)
                            temperature = payload.get("temperature", 0.7)

                            log.info(f"Task received  id={task_id}  model={model}  messages={len(messages)}")

                            try:
                                content, tokens_used = await run_inference(
                                    model, messages, max_tokens, temperature
                                )
                                result_msg = WSMessage(
                                    type="task_complete",
                                    payload={
                                        "task_id": task_id,
                                        "node_id": node_info.node_id,
                                        "content": content,
                                        "tokens_used": tokens_used,
                                    }
                                )
                                await ws.send(result_msg.model_dump_json())
                                log.info(f"Task complete  id={task_id}  tokens={tokens_used}")

                            except Exception as e:
                                log.error(f"Inference error  id={task_id}  err={e}")
                                fail_msg = WSMessage(
                                    type="task_failed",
                                    payload={"task_id": task_id, "node_id": node_info.node_id, "error": str(e)}
                                )
                                await ws.send(fail_msg.model_dump_json())
                finally:
                    heartbeat_task.cancel()

        except (websockets.exceptions.ConnectionClosedError,
                websockets.exceptions.ConnectionClosedOK,
                ConnectionRefusedError,
                OSError) as e:
            log.warning(f"Connection lost: {e}. Reconnecting in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

        except Exception as e:
            log.exception(f"Unexpected error: {e}. Reconnecting in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


# ── CLI entry point ───────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="DeAI Node Client — join the network and earn by sharing compute.")
    parser.add_argument(
        "--orchestrator",
        default="ws://localhost:8000/ws/node",
        help="WebSocket URL of the orchestrator (default: ws://localhost:8000/ws/node)",
    )
    parser.add_argument(
        "--models",
        default="any",
        help="Comma-separated list of model names this node supports, or 'any' (default: any)",
    )
    parser.add_argument(
        "--gpu",
        action="store_true",
        help="Flag: this node has a GPU available",
    )
    parser.add_argument(
        "--vram",
        type=float,
        default=None,
        help="VRAM in GB (optional, informational)",
    )
    parser.add_argument(
        "--ram",
        type=float,
        default=None,
        help="RAM in GB (optional, informational)",
    )
    parser.add_argument(
        "--id",
        default=None,
        help="Custom node ID (default: auto-generated)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    node_id = args.id or f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}"

    node_info = NodeInfo(
        node_id=node_id,
        models=models,
        gpu=args.gpu,
        vram_gb=args.vram,
        ram_gb=args.ram,
    )

    try:
        asyncio.run(run_node(args.orchestrator, node_info))
    except KeyboardInterrupt:
        log.info("Node shutting down.")
