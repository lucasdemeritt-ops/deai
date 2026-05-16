"""
DeAI Orchestrator
-----------------
The network brain. Responsibilities:
  - Accept inference requests via HTTP (OpenAI-compatible API)
  - Maintain a registry of connected Worker Nodes
  - Dispatch tasks to available nodes over WebSocket
  - Collect results, run mock verification, return to caller
  - Track basic network stats

Run:
    python protocol/orchestrator.py
    (defaults to http://localhost:8000)
"""

import asyncio
import json
import logging
import sys
import time
import os
from typing import Dict, Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.schemas import (
    ChatRequest, ChatResponse, Choice, Message, Role, Usage,
    Task, TaskResult, TaskStatus,
    NodeInfo, NodeStatus,
    WSMessage,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("orchestrator")

app = FastAPI(title="DeAI Orchestrator", version="0.1.0")


# ── In-memory state ───────────────────────────────────────────────────────────

class NodeConnection:
    def __init__(self, ws: WebSocket, info: NodeInfo):
        self.ws = ws
        self.info = info
        self.status = NodeStatus.idle
        self.last_seen = time.time()
        self.tasks_completed = 0


# node_id → NodeConnection
nodes: Dict[str, NodeConnection] = {}

# task_id → asyncio.Event  (set when result arrives)
pending_events: Dict[str, asyncio.Event] = {}

# task_id → TaskResult
results: Dict[str, TaskResult] = {}

# simple stats
stats = {"requests": 0, "completed": 0, "failed": 0}


# ── Helpers ───────────────────────────────────────────────────────────────────

def find_available_node(model: str) -> Optional[NodeConnection]:
    """Pick an idle node that supports the requested model."""
    for node in nodes.values():
        if node.status != NodeStatus.idle:
            continue
        supports = "any" in node.info.models or model in node.info.models
        if supports:
            return node
    return None


def mock_verify(result: TaskResult) -> bool:
    """
    Placeholder verification step.
    Phase 1: always passes. Later replaced with ZK-proof or TEE attestation.
    """
    return len(result.content) > 0


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
                result.verified = mock_verify(result)

                nodes[node_id].status = NodeStatus.idle
                nodes[node_id].tasks_completed += 1

                results[result.task_id] = result
                stats["completed"] += 1

                log.info(f"Task done    id={result.task_id}  node={node_id}  verified={result.verified}  tokens={result.tokens_used}")

                # Wake up the waiting HTTP request
                if result.task_id in pending_events:
                    pending_events[result.task_id].set()

            elif msg.type == "task_failed":
                task_id = msg.payload.get("task_id")
                nodes[node_id].status = NodeStatus.idle
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


# ── HTTP: OpenAI-compatible inference endpoint ────────────────────────────────

@app.post("/v1/chat/completions", response_model=ChatResponse)
async def chat_completions(req: ChatRequest):
    stats["requests"] += 1

    task = Task(
        model=req.model,
        messages=req.messages,
        max_tokens=req.max_tokens or 512,
        temperature=req.temperature or 0.7,
    )

    log.info(f"Request recv  id={task.task_id}  model={req.model}  nodes_online={len(nodes)}")

    # Find a node (retry for up to 30 seconds if all are busy)
    node = None
    deadline = time.time() + 30
    while time.time() < deadline:
        node = find_available_node(req.model)
        if node:
            break
        await asyncio.sleep(0.5)

    if node is None:
        stats["failed"] += 1
        raise HTTPException(
            status_code=503,
            detail=f"No nodes available for model '{req.model}'. Try again shortly or connect a node.",
        )

    # Dispatch to node
    node.status = NodeStatus.busy
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
    log.info(f"Dispatched   id={task.task_id}  to={node.info.node_id}")

    # Wait for result (60s timeout)
    try:
        await asyncio.wait_for(event.wait(), timeout=60.0)
    except asyncio.TimeoutError:
        del pending_events[task.task_id]
        node.status = NodeStatus.idle
        stats["failed"] += 1
        raise HTTPException(status_code=504, detail="Node did not respond in time.")

    del pending_events[task.task_id]
    result = results.pop(task.task_id, None)

    if result is None or not result.verified:
        raise HTTPException(status_code=500, detail="Task result failed verification.")

    prompt_tokens = sum(len(m.content.split()) for m in req.messages)
    completion_tokens = len(result.content.split())

    return ChatResponse(
        model=req.model,
        choices=[
            Choice(
                message=Message(role=Role.assistant, content=result.content),
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
    return {
        "nodes_online": len(nodes),
        "nodes": [
            {
                "node_id": n.info.node_id,
                "models": n.info.models,
                "gpu": n.info.gpu,
                "status": n.status.value,
                "tasks_completed": n.tasks_completed,
                "last_seen_ago_s": round(time.time() - n.last_seen, 1),
            }
            for n in nodes.values()
        ],
        "stats": stats,
    }


@app.get("/")
def root():
    return {"service": "DeAI Orchestrator", "version": "0.1.0", "docs": "/docs", "status": "/status"}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
