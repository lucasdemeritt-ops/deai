"""
DeAI Orchestrator
-----------------
The network brain. Responsibilities:
  - Accept inference requests via HTTP (OpenAI-compatible API)
  - Maintain a registry of connected Worker Nodes
  - Dispatch tasks to the best available node (scored routing)
  - Collect results, run pluggable verification, return to caller
  - Track basic network stats and earnings

Routing score (higher = better candidate):
  +20  exact model match
  + 1  "any" model fallback
  + 5  idle longest (round-robin tiebreaker, max 5pts)

  Hardware (GPU / VRAM) is deliberately NOT scored: it is self-reported and
  unverified, so rewarding or prioritizing it pays for an unprovable claim —
  the same anti-pattern the verification work removed from `mock_verify`. A
  node's real capability will instead come from measured, verified delivered
  work (the deferred benchmark/tier system — see docs/VERIFICATION.md
  build-now #3 and docs/VERIFICATION_PROTOCOL.md §1).

Modes:
  Mock (default) — in-memory ledger, no blockchain required
    python protocol/orchestrator.py

  On-chain — real SlashingContract calls for reputation + eligibility
    python protocol/orchestrator.py --chain \\
        --rpc-url http://localhost:8545 \\
        --slashing-contract 0x... \\
        --payment-contract 0x... \\
        --orchestrator-key 0x...

  See docs/CHAIN_SETUP.md for full on-chain setup instructions.
"""

import argparse
import asyncio
import json
import logging
import sys
import time
import os
from typing import Dict, Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.schemas import (
    ChatRequest, ChatResponse, Choice, Message, Role, Usage,
    Task, TaskResult, TaskStatus,
    NodeInfo, NodeStatus,
    WSMessage,
)
from ledger import Ledger
from verification import Verifier, ContentVerifier, make_verifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("orchestrator")

app = FastAPI(title="DeAI Orchestrator", version="0.1.0")


# ── State ─────────────────────────────────────────────────────────────────────

# Set at startup from CLI args — None means mock/dev mode
chain_ledger = None

# Optional API key — None means open access (fine for local dev)
_api_key: Optional[str] = None
_bearer = HTTPBearer(auto_error=False)


def _check_api_key(creds: Optional[HTTPAuthorizationCredentials] = Security(_bearer)):
    if _api_key is None:
        return  # open access
    if creds is None or creds.credentials != _api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")

class NodeConnection:
    def __init__(self, ws: WebSocket, info: NodeInfo):
        self.ws = ws
        self.info = info
        self.status = NodeStatus.idle
        self.last_seen = time.time()
        self.last_task_time: float = 0.0  # for round-robin tiebreaking
        self.tasks_completed = 0


# node_id → NodeConnection
nodes: Dict[str, NodeConnection] = {}

# task_id → asyncio.Event  (set when result arrives)
pending_events: Dict[str, asyncio.Event] = {}

# task_id → TaskResult
results: Dict[str, TaskResult] = {}

# simple stats
stats = {"requests": 0, "completed": 0, "failed": 0}

# earnings ledger
ledger = Ledger()

# Verification policy. Default = ContentVerifier (legacy non-empty check, no
# recheck) so mock mode and CI are unchanged. --verify-sample-rate swaps in the
# optimistic redundant-execution verifier. See docs/VERIFICATION.md.
verifier: Verifier = ContentVerifier()


# ── Routing ───────────────────────────────────────────────────────────────────

def score_node(node: NodeConnection, model: str) -> int:
    """
    Score a node as a candidate for a given model request.
    Returns -1 if the node cannot handle the model at all.
    """
    can_run = model in node.info.models or "any" in node.info.models
    if not can_run:
        return -1

    score = 0

    # Exact model match strongly preferred over generic "any" nodes
    if model in node.info.models:
        score += 20
    else:
        score += 1

    # Hardware (gpu / vram_gb) intentionally not scored — self-reported and
    # unverified. See module docstring and docs/VERIFICATION.md build-now #3.

    # Round-robin tiebreaker: prefer the node that has been idle longest
    idle_seconds = time.time() - node.last_task_time
    score += min(int(idle_seconds / 10), 5)

    return score


def find_best_node(
    model: str, exclude: Optional[set] = None
) -> Optional[tuple[NodeConnection, int, str]]:
    """
    Return (best_node, score, reason) for the given model, or None if no node available.
    Only considers idle nodes. `exclude` is a set of node_ids to skip — used by
    redundant verification so the recheck lands on a *different* node than the
    one that produced the primary result. In chain mode, also skips miners that
    have been ejected from the SlashingContract (stake burned below minimum).
    """
    exclude = exclude or set()
    candidates = []
    for node in nodes.values():
        if node.status != NodeStatus.idle:
            continue
        if node.info.node_id in exclude:
            continue
        if chain_ledger is not None and node.info.wallet:
            if not chain_ledger.is_eligible(node.info.wallet):
                log.warning(f"Node ineligible (ejected on-chain)  id={node.info.node_id}  wallet={node.info.wallet[:10]}...")
                continue
        s = score_node(node, model)
        if s >= 0:
            candidates.append((s, node))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_node = candidates[0]

    parts = []
    if model in best_node.info.models:
        parts.append("exact-model")
    else:
        parts.append("any-model")
    if len(candidates) > 1:
        parts.append(f"{len(candidates)}-candidates")

    return best_node, best_score, "+".join(parts)


# ── WebSocket: Node registration & task loop ──────────────────────────────────

@app.websocket("/ws/node")
async def node_endpoint(ws: WebSocket):
    await ws.accept()
    node_id = None

    try:
        # First message must be a register payload
        raw = await asyncio.wait_for(ws.receive_text(), timeout=10.0)
        msg = WSMessage(**json.loads(raw))

        if msg.type != "register":
            await ws.send_text(json.dumps({"type": "error", "payload": {"detail": "First message must be 'register'"}}))
            await ws.close()
            return

        info = NodeInfo(**msg.payload)
        node_id = info.node_id
        nodes[node_id] = NodeConnection(ws=ws, info=info)

        log.info(f"Node joined  id={node_id}  models={info.models}  gpu={info.gpu}")
        await ws.send_text(json.dumps({"type": "ack", "payload": {"node_id": node_id, "message": "Registered. Waiting for tasks."}}))

        # Keep connection alive and handle incoming messages
        while True:
            raw = await ws.receive_text()
            msg = WSMessage(**json.loads(raw))

            if msg.type == "heartbeat":
                nodes[node_id].last_seen = time.time()

            elif msg.type == "task_complete":
                result = TaskResult(**msg.payload)

                node = nodes[node_id]
                node.status = NodeStatus.idle
                node.tasks_completed += 1
                results[result.task_id] = result

                log.info(f"Result in    id={result.task_id}  node={node_id}  tokens={result.tokens_used}")

                # Verification, ledger, and on-chain settlement happen in the
                # HTTP path — it owns the task context and can re-dispatch for
                # a redundant check before any reward is finalized. Here we
                # just hand the raw result back to the waiting request.
                if result.task_id in pending_events:
                    pending_events[result.task_id].set()

            elif msg.type == "task_failed":
                task_id = msg.payload.get("task_id")
                node = nodes[node_id]
                node.status = NodeStatus.idle
                stats["failed"] += 1
                log.warning(f"Task failed  id={task_id}  node={node_id}")
                if task_id and task_id in pending_events:
                    pending_events[task_id].set()

    except asyncio.TimeoutError:
        log.warning("Node timed out during registration")
    except WebSocketDisconnect:
        log.info(f"Node disconnected  id={node_id}")
    except Exception as e:
        log.exception(f"Node error  id={node_id}  err={e}")
    finally:
        if node_id and node_id in nodes:
            del nodes[node_id]
            log.info(f"Node removed  id={node_id}  remaining={len(nodes)}")


# ── Dispatch ──────────────────────────────────────────────────────────────────

async def _dispatch_and_wait(
    task: Task, exclude: Optional[set] = None
) -> tuple[Optional[TaskResult], Optional[NodeConnection], str]:
    """
    Find an idle node (skipping `exclude`), dispatch the task, await the result.
    Returns (result, node, status) where status is 'ok' | 'no_node' | 'timeout'.
    On anything other than 'ok', result and node are None.
    """
    match = None
    deadline = time.time() + 30
    while time.time() < deadline:
        match = find_best_node(task.model, exclude)
        if match:
            break
        await asyncio.sleep(0.5)

    if match is None:
        return None, None, "no_node"

    node, score, reason = match
    node.status = NodeStatus.busy
    node.last_task_time = time.time()
    event = asyncio.Event()
    pending_events[task.task_id] = event

    dispatch_msg = {
        "type": "task",
        "payload": {
            "task_id": task.task_id,
            "model": task.model,
            "messages": [m.model_dump() for m in task.messages],
            "max_tokens": task.max_tokens,
            "temperature": task.temperature,
        }
    }
    await node.ws.send_text(json.dumps(dispatch_msg))
    log.info(f"Dispatched   id={task.task_id}  to={node.info.node_id}  score={score}  reason={reason}")

    try:
        await asyncio.wait_for(event.wait(), timeout=60.0)
    except asyncio.TimeoutError:
        pending_events.pop(task.task_id, None)
        node.status = NodeStatus.idle
        return None, None, "timeout"

    pending_events.pop(task.task_id, None)
    result = results.pop(task.task_id, None)
    if result is None:
        return None, None, "timeout"
    return result, node, "ok"


def _slash_for_bad_result(node: NodeConnection, reason: str) -> None:
    """
    Unambiguously bad result (e.g. empty). Preserves the prior on-chain slash.
    A redundant-verification *mismatch* does NOT come here — that path requires
    committee escalation and must not auto-slash (see chat_completions and
    docs/VERIFICATION.md on false-positive slashing).
    """
    log.warning(f"Bad result   node={node.info.node_id}  reason={reason}")
    if chain_ledger is not None and node.info.wallet:
        asyncio.create_task(asyncio.to_thread(chain_ledger.slash_onchain, node.info.wallet))


# ── HTTP: OpenAI-compatible inference endpoint ────────────────────────────────

@app.post("/v1/chat/completions", response_model=ChatResponse)
async def chat_completions(req: ChatRequest, _auth=Depends(_check_api_key)):
    stats["requests"] += 1

    task = Task(
        model=req.model,
        messages=req.messages,
        max_tokens=req.max_tokens or 512,
        temperature=req.temperature or 0.7,
    )

    log.info(f"Request recv  id={task.task_id}  model={req.model}  nodes_online={len(nodes)}")

    primary, primary_node, status = await _dispatch_and_wait(task)
    if status == "no_node":
        stats["failed"] += 1
        raise HTTPException(
            status_code=503,
            detail=f"No nodes available for model '{req.model}'. Try again shortly or connect a node.",
        )
    if status == "timeout":
        stats["failed"] += 1
        raise HTTPException(status_code=504, detail="Node did not respond in time.")

    # Cheap local gate — replaces the old mock_verify non-empty check.
    if not verifier.well_formed(primary):
        stats["failed"] += 1
        _slash_for_bad_result(primary_node, "malformed/empty result")
        raise HTTPException(status_code=500, detail="Task result failed verification.")

    # Optimistic redundant check (Standard tier, docs/VERIFICATION.md). Sampled
    # and silent: the node is not told it is being checked.
    if verifier.should_recheck(task, primary):
        shadow = Task(
            model=task.model,
            messages=task.messages,
            max_tokens=task.max_tokens,
            temperature=task.temperature,
        )
        r2, n2, s2 = await _dispatch_and_wait(
            shadow, exclude={primary_node.info.node_id}
        )
        if s2 != "ok" or not verifier.well_formed(r2):
            # No independent checker free — cannot verify. Accept optimistically
            # rather than punish a provider for a thin network; record that this
            # task went unverified.
            log.warning(f"VERIFY skip   id={task.task_id}  reason=no-checker-available")
        else:
            outcome = verifier.compare(task, primary, r2)
            log.info(
                f"VERIFY {'OK ' if outcome.accepted else 'MISMATCH'}  "
                f"id={task.task_id}  primary={primary_node.info.node_id}  "
                f"checker={n2.info.node_id}  {outcome.detail}"
            )
            if not outcome.accepted:
                stats["failed"] += 1
                # Escalation/committee not built yet. Do NOT auto-slash —
                # docs/VERIFICATION.md flags false-positive slashing of an
                # honest provider as existential.
                raise HTTPException(
                    status_code=502,
                    detail="Result failed redundant verification; committee escalation required.",
                )

    # Accepted → finalize the reward (off-chain ledger + optional on-chain mint).
    primary.verified = True
    stats["completed"] += 1
    earned = ledger.record_completion(
        node_id=primary_node.info.node_id,
        task_id=primary.task_id,
        output_tokens=primary.tokens_used,
    )
    log.info(
        f"Task done    id={primary.task_id}  node={primary_node.info.node_id}  "
        f"tokens={primary.tokens_used}  earned={earned:.2f}"
    )

    if chain_ledger is not None and primary_node.info.wallet:
        asyncio.create_task(
            asyncio.to_thread(
                chain_ledger.record_completion_onchain,
                primary_node.info.wallet,
                primary.tokens_used,
            )
        )

    prompt_tokens = sum(len(m.content.split()) for m in req.messages)
    completion_tokens = len(primary.content.split())

    return ChatResponse(
        model=req.model,
        choices=[
            Choice(
                message=Message(role=Role.assistant, content=primary.content),
                finish_reason="stop",
            )
        ],
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


# ── HTTP: Network status dashboard ───────────────────────────────────────────

@app.get("/status")
def network_status():
    now = time.time()
    return {
        "nodes_online": len(nodes),
        "nodes": [
            {
                "node_id": n.info.node_id,
                "models": n.info.models,
                "gpu": n.info.gpu,
                "vram_gb": n.info.vram_gb,
                "status": n.status.value,
                "tasks_completed": n.tasks_completed,
                "balance": ledger.balance(n.info.node_id),
                "score": score_node(n, n.info.models[0]) if n.status == NodeStatus.idle else "busy",
                "last_seen_ago_s": round(now - n.last_seen, 1),
                "last_task_ago_s": round(now - n.last_task_time, 1) if n.last_task_time else None,
            }
            for n in nodes.values()
        ],
        "stats": stats,
        "economy": ledger.network_totals(),
    }


@app.get("/earnings")
def earnings():
    """Leaderboard — all nodes ranked by total earnings."""
    return {
        "leaderboard": ledger.all_balances(),
        "economy": ledger.network_totals(),
    }


@app.get("/earnings/{node_id}")
def node_earnings(node_id: str):
    """Earnings detail for a specific node."""
    return ledger.summary(node_id)


@app.get("/")
def root():
    return {"service": "DeAI Orchestrator", "version": "0.1.0", "docs": "/docs", "status": "/status"}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DeAI Orchestrator")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--api-key", default=os.getenv("DEAI_API_KEY"),
                        help="Require this key on /v1/chat/completions requests (Bearer token). "
                             "Omit for open access (local dev default).")

    # On-chain mode (opt-in — mock mode is the default)
    parser.add_argument("--chain", action="store_true",
                        help="Enable on-chain mode (real DEAI rewards + SlashingContract)")
    parser.add_argument("--rpc-url",
                        default=os.getenv("DEAI_RPC_URL", "http://localhost:8545"),
                        help="RPC endpoint for the chain (default: localhost Hardhat node)")
    parser.add_argument("--token-contract",
                        default=os.getenv("DEAI_TOKEN_CONTRACT"),
                        help="Deployed DeAIToken address")
    parser.add_argument("--slashing-contract",
                        default=os.getenv("DEAI_SLASHING_CONTRACT"),
                        help="Deployed SlashingContract address")
    parser.add_argument("--payment-contract",
                        default=os.getenv("DEAI_PAYMENT_CONTRACT"),
                        help="Deployed PaymentContract address")
    parser.add_argument("--orchestrator-key",
                        default=os.getenv("DEAI_ORCHESTRATOR_KEY"),
                        help="Orchestrator wallet private key (needs MINTER_ROLE + ORCHESTRATOR_ROLE)")

    # Verification (Standard tier — docs/VERIFICATION.md)
    parser.add_argument("--verify-sample-rate", type=float,
                        default=float(os.getenv("DEAI_VERIFY_SAMPLE_RATE", "0.0")),
                        help="Fraction of tasks [0..1] silently re-run on a second "
                             "node for redundant verification. 0 = legacy non-empty "
                             "check only, no rechecks (default).")
    parser.add_argument("--verify-threshold", type=float,
                        default=float(os.getenv("DEAI_VERIFY_THRESHOLD", "0.85")),
                        help="Agreement threshold [0..1] for redundant verification "
                             "(default 0.85). Only used when --verify-sample-rate > 0.")

    args = parser.parse_args()

    if args.api_key:
        _api_key = args.api_key
        log.info("API key authentication enabled on /v1/chat/completions")
    else:
        log.info("Running in open-access mode (no API key required)")

    verifier = make_verifier(args.verify_sample_rate, args.verify_threshold)
    if args.verify_sample_rate > 0:
        log.info(
            f"Verification: redundant execution ENABLED  "
            f"sample_rate={args.verify_sample_rate}  threshold={args.verify_threshold}"
        )
    else:
        log.info("Verification: content-only (legacy non-empty check; no redundant rechecks)")

    if args.chain:
        missing = [n for n, v in [
            ("--token-contract",    args.token_contract),
            ("--slashing-contract", args.slashing_contract),
            ("--payment-contract",  args.payment_contract),
            ("--orchestrator-key",  args.orchestrator_key),
        ] if not v]
        if missing:
            parser.error(f"--chain requires: {', '.join(missing)}")

        from chain_ledger import ChainLedger
        chain_ledger = ChainLedger(
            rpc_url=args.rpc_url,
            orchestrator_key=args.orchestrator_key,
            token_addr=args.token_contract,
            slashing_addr=args.slashing_contract,
            payment_addr=args.payment_contract,
        )
        log.info("Running in ON-CHAIN mode — SlashingContract wired")
    else:
        log.info("Running in MOCK mode — in-memory ledger only (no blockchain required)")

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
