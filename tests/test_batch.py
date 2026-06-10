"""
/v1/batch fan-out (VISION.md Stage 1 — job parallelism). One job's sub-tasks
spread across many mock nodes in parallel, results aggregated in order, each
sub-task running through the same verified pipeline as single requests.
"""

import asyncio
import json

import httpx
import pytest
from httpx import ASGITransport

import orchestrator as orc
from orchestrator import app, nodes, results, pending_events, stats, ledger, model_registry
from shared.schemas import NodeInfo, NodeStatus, TaskResult
from model_registry import ModelStack


class _EchoWS:
    """Fake node that echoes the prompt back, so result order is checkable."""

    def __init__(self, node_id: str, transform=None):
        self._node_id = node_id
        self._transform = transform or (lambda p: f"echo:{p}")
        self.dispatched: list[dict] = []

    async def send_text(self, data: str):
        msg = json.loads(data)
        if msg.get("type") != "task":
            return
        payload = msg["payload"]
        self.dispatched.append(payload)
        task_id = payload["task_id"]
        prompt = payload["messages"][-1]["content"]
        content = self._transform(prompt)

        async def _resolve():
            await asyncio.sleep(0.02)
            if self._node_id in nodes:
                nodes[self._node_id].status = NodeStatus.idle
                nodes[self._node_id].tasks_completed += 1
            results[task_id] = TaskResult(
                task_id=task_id, node_id=self._node_id,
                content=content, tokens_used=max(len(content.split()), 1),
            )
            if task_id in pending_events:
                pending_events[task_id].set()

        asyncio.create_task(_resolve())


def _add_node(node_id: str, models=("llama3",), transform=None):
    ws = _EchoWS(node_id, transform)
    conn = orc.NodeConnection(ws=ws, info=NodeInfo(node_id=node_id, models=list(models)))
    nodes[node_id] = conn
    return conn


@pytest.fixture(autouse=True)
def reset():
    nodes.clear()
    results.clear()
    pending_events.clear()
    stats.update(requests=0, completed=0, failed=0)
    ledger._balances.clear()
    model_registry._stacks.clear()
    yield
    nodes.clear()
    results.clear()
    pending_events.clear()
    model_registry._stacks.clear()


async def _post_batch(payload: dict) -> httpx.Response:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as client:
        return await client.post("/v1/batch", json=payload)


# ── Fan-out across nodes ──────────────────────────────────────────────────────

async def test_batch_spreads_subtasks_across_nodes_in_order():
    for nid in ("n1", "n2", "n3"):
        _add_node(nid)
    prompts = [f"prompt-{i}" for i in range(6)]
    r = await _post_batch({"model": "llama3", "prompts": prompts})
    assert r.status_code == 200
    data = r.json()
    assert data["completed"] == 6 and data["failed"] == 0
    # Results come back in request order regardless of which node ran them.
    for i, item in enumerate(data["items"]):
        assert item["index"] == i
        assert item["status"] == "ok"
        assert item["content"] == f"echo:prompt-{i}"
    # Work was genuinely distributed: every node served at least one sub-task.
    served = [nodes[n].tasks_completed for n in ("n1", "n2", "n3")]
    assert sum(served) == 6
    assert all(c >= 1 for c in served)


async def test_batch_single_node_processes_all_sequentially():
    _add_node("only")
    r = await _post_batch({"model": "llama3", "prompts": ["a", "b", "c"]})
    assert r.status_code == 200
    data = r.json()
    assert data["completed"] == 3
    assert nodes["only"].tasks_completed == 3


# ── Validation & failure semantics ───────────────────────────────────────────

async def test_batch_empty_prompts_rejected():
    _add_node("n1")
    r = await _post_batch({"model": "llama3", "prompts": []})
    assert r.status_code == 422


async def test_batch_no_nodes_503():
    r = await _post_batch({"model": "llama3", "prompts": ["a", "b"]})
    assert r.status_code == 503


async def test_batch_partial_failure_is_per_item():
    # The only node returns empty content → every item fails verification,
    # but the batch itself still returns 200 with per-item errors.
    _add_node("bad", transform=lambda p: "")
    r = await _post_batch({"model": "llama3", "prompts": ["x", "y"]})
    assert r.status_code == 200
    data = r.json()
    assert data["completed"] == 0 and data["failed"] == 2
    assert all(it["status"] == "error" for it in data["items"])


# ── Same verified pipeline as single requests ────────────────────────────────

async def test_batch_subtasks_accrue_earnings_per_subtask():
    _add_node("earner")
    await _post_batch({"model": "llama3", "prompts": ["a", "b", "c"]})
    summary = ledger.summary("earner")
    assert summary["tasks_paid"] == 3
    assert summary["balance"] > 0


async def test_batch_applies_registered_stack_seed():
    model_registry.register(ModelStack(
        model_id="qwen3:8b", runtime="ollama>=0.6.0", temperature=0.0, seed=99,
    ))
    conn = _add_node("n1", models=("qwen3:8b",))
    r = await _post_batch({"model": "qwen3:8b", "prompts": ["hello"]})
    assert r.status_code == 200
    assert conn.ws.dispatched[0]["seed"] == 99
    assert conn.ws.dispatched[0]["temperature"] == 0.0


async def test_batch_runs_verification_per_subtask():
    from verification import RedundantExecutionVerifier
    model_registry.register(ModelStack(
        model_id="qwen3:8b", runtime="ollama>=0.6.0", temperature=0.0, seed=1,
    ))
    # Two agreeing nodes (identical echo transform) so the recheck passes.
    n1 = _add_node("n1", models=("qwen3:8b",))
    n2 = _add_node("n2", models=("qwen3:8b",))

    old = orc.verifier
    orc.verifier = RedundantExecutionVerifier(sample_rate=1.0)
    try:
        r = await _post_batch({"model": "qwen3:8b", "prompts": ["check me"]})
    finally:
        orc.verifier = old

    assert r.status_code == 200
    assert r.json()["completed"] == 1
    # Primary + silent checker dispatch = two dispatches for one sub-task.
    total_dispatches = len(n1.ws.dispatched) + len(n2.ws.dispatched)
    assert total_dispatches == 2


async def test_batch_stats_count_each_subtask_as_request():
    for nid in ("n1", "n2"):
        _add_node(nid)
    await _post_batch({"model": "llama3", "prompts": ["a", "b", "c", "d"]})
    assert stats["requests"] == 4
    assert stats["completed"] == 4
