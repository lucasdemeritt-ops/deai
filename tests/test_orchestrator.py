"""
Orchestrator integration tests.

Uses Starlette's TestClient for sync HTTP tests and httpx AsyncClient with
ASGITransport for async round-trip tests. Mock nodes are injected directly
into the orchestrator's global `nodes` dict — their fake WS automatically
resolves the pending event when a task is dispatched, no real network needed.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock

from starlette.testclient import TestClient
import httpx
from httpx import ASGITransport

import orchestrator as orc
from orchestrator import app, nodes, results, pending_events, stats, ledger, model_registry
import orchestrator
from shared.schemas import NodeInfo, NodeStatus, TaskResult
from model_registry import ModelStack


# ── Mock node helpers ──────────────────────────────────────────────────────────

class _MockWS:
    """
    Fake WebSocket. When the orchestrator calls send_text with a 'task'
    dispatch, immediately schedules a result and sets the pending event.
    """
    def __init__(self, node_id: str, response: str):
        self._node_id = node_id
        self._response = response
        self.last_payload: dict | None = None  # captured on each task dispatch

    async def send_text(self, data: str):
        msg = json.loads(data)
        if msg.get("type") != "task":
            return
        self.last_payload = msg["payload"]
        task_id = msg["payload"]["task_id"]

        async def _resolve():
            await asyncio.sleep(0.02)
            # Mirror the real WS task_complete handler: go idle, record result, set event.
            if self._node_id in nodes:
                nodes[self._node_id].status = NodeStatus.idle
                nodes[self._node_id].tasks_completed += 1
            results[task_id] = TaskResult(
                task_id=task_id,
                node_id=self._node_id,
                content=self._response,
                tokens_used=len(self._response.split()),
            )
            if task_id in pending_events:
                pending_events[task_id].set()

        asyncio.create_task(_resolve())


def _add_node(node_id: str, models: list[str], response: str = "Test response.") -> orc.NodeConnection:
    ws = _MockWS(node_id, response)
    info = NodeInfo(node_id=node_id, models=models)
    conn = orc.NodeConnection(ws=ws, info=info)
    nodes[node_id] = conn
    return conn


# ── State reset ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset():
    nodes.clear()
    results.clear()
    pending_events.clear()
    stats["requests"] = 0
    stats["completed"] = 0
    stats["failed"] = 0
    ledger._balances.clear()
    model_registry._stacks.clear()
    orchestrator._api_key = None
    orchestrator.chain_ledger = None
    yield
    nodes.clear()
    results.clear()
    pending_events.clear()
    model_registry._stacks.clear()


# ── Sync HTTP: simple endpoints ────────────────────────────────────────────────

def test_root():
    with TestClient(app) as client:
        r = client.get("/")
    assert r.status_code == 200
    assert r.json()["service"] == "DAI Orchestrator"


def test_status_no_nodes():
    with TestClient(app) as client:
        r = client.get("/status")
    assert r.status_code == 200
    data = r.json()
    assert data["nodes_online"] == 0
    assert data["nodes"] == []


def test_status_shows_connected_node():
    _add_node("n1", ["llama3"])
    with TestClient(app) as client:
        r = client.get("/status")
    assert r.status_code == 200
    data = r.json()
    assert data["nodes_online"] == 1
    assert data["nodes"][0]["node_id"] == "n1"


def test_earnings_empty():
    with TestClient(app) as client:
        r = client.get("/earnings")
    assert r.status_code == 200
    assert r.json()["leaderboard"] == []


def test_node_earnings_unknown():
    with TestClient(app) as client:
        r = client.get("/earnings/nobody")
    assert r.status_code == 200
    assert r.json()["balance"] == 0.0


# ── API key auth (sync) ────────────────────────────────────────────────────────

def test_api_key_rejects_missing():
    orchestrator._api_key = "secret"
    with TestClient(app) as client:
        r = client.post("/v1/chat/completions", json={
            "model": "llama3",
            "messages": [{"role": "user", "content": "hi"}],
        })
    assert r.status_code == 401


def test_api_key_rejects_wrong_token():
    orchestrator._api_key = "secret"
    with TestClient(app) as client:
        r = client.post("/v1/chat/completions",
            json={"model": "llama3", "messages": [{"role": "user", "content": "hi"}]},
            headers={"Authorization": "Bearer wrongkey"},
        )
    assert r.status_code == 401


# ── Async round-trip tests ─────────────────────────────────────────────────────

async def _post(payload: dict, headers: dict = None) -> httpx.Response:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=35) as client:
        return await client.post("/v1/chat/completions", json=payload, headers=headers or {})


async def test_503_when_no_nodes():
    r = await _post({"model": "llama3", "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 503


async def test_full_round_trip():
    _add_node("n1", ["llama3"], "Paris is the capital of France.")
    r = await _post({"model": "llama3", "messages": [{"role": "user", "content": "Capital of France?"}]})
    assert r.status_code == 200
    data = r.json()
    assert data["choices"][0]["message"]["content"] == "Paris is the capital of France."
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert data["usage"]["total_tokens"] > 0


async def test_any_model_node_serves_any_request():
    _add_node("n-any", ["any"], "Sure thing.")
    r = await _post({"model": "mistral", "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "Sure thing."


async def test_exact_model_preferred_over_any():
    _add_node("n-any", ["any"], "From any-node.")
    _add_node("n-exact", ["llama3"], "From exact-node.")
    r = await _post({"model": "llama3", "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "From exact-node."


async def test_model_mismatch_gives_503():
    _add_node("n-mistral", ["mistral"], "I only run mistral.")
    r = await _post({"model": "llama3", "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 503


async def test_empty_result_gives_500():
    _add_node("bad-node", ["llama3"], "")
    r = await _post({"model": "llama3", "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 500


async def test_earnings_accrue_after_task():
    _add_node("earner", ["llama3"], "The answer is 42.")
    await _post({"model": "llama3", "messages": [{"role": "user", "content": "What is the answer?"}]})

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/earnings/earner")
    assert r.json()["balance"] > 0


async def test_stats_increment_on_success():
    _add_node("n1", ["llama3"], "Done.")
    await _post({"model": "llama3", "messages": [{"role": "user", "content": "ping"}]})
    assert stats["requests"] == 1
    assert stats["completed"] == 1
    assert stats["failed"] == 0


async def test_api_key_accepts_correct_bearer():
    orchestrator._api_key = "secret"
    _add_node("n1", ["llama3"], "Authenticated.")
    r = await _post(
        {"model": "llama3", "messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code == 200


async def test_node_goes_idle_after_task():
    conn = _add_node("n1", ["llama3"], "Done.")
    assert conn.status == NodeStatus.idle
    await _post({"model": "llama3", "messages": [{"role": "user", "content": "hi"}]})
    assert conn.status == NodeStatus.idle
    assert conn.tasks_completed == 1


# ── Registry-gated verifier / seed injection (§12) ───────────────────────────

def _register(model_id: str = "qwen3:8b", seed: int = 42):
    model_registry.register(ModelStack(
        model_id=model_id, runtime="ollama>=0.6.0",
        temperature=0.0, seed=seed,
    ))


async def test_seed_injected_when_stack_registered():
    """Dispatch payload must carry the registered seed when a stack is registered."""
    _register(seed=77)
    conn = _add_node("n1", ["qwen3:8b"], "Deterministic answer.")
    await _post({"model": "qwen3:8b", "messages": [{"role": "user", "content": "hi"}]})
    assert conn.ws.last_payload is not None
    assert conn.ws.last_payload["seed"] == 77
    assert conn.ws.last_payload["temperature"] == 0.0


async def test_no_seed_when_stack_not_registered():
    """Dispatch payload must carry seed=None for unregistered models."""
    conn = _add_node("n1", ["llama3"], "Generic answer.")
    await _post({"model": "llama3", "messages": [{"role": "user", "content": "hi"}]})
    assert conn.ws.last_payload is not None
    assert conn.ws.last_payload["seed"] is None


async def test_stack_overrides_request_temperature():
    """User-supplied temperature must be ignored when the model has a registered stack."""
    _register(seed=42)
    conn = _add_node("n1", ["qwen3:8b"], "Answer.")
    # Request explicitly sends temperature=0.9 — the stack should clamp it to 0.
    await _post({
        "model": "qwen3:8b",
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0.9,
    })
    assert conn.ws.last_payload["temperature"] == 0.0


async def test_round_trip_with_registered_stack():
    """End-to-end: a registered model still returns a valid 200 response."""
    _register(seed=42)
    _add_node("n1", ["qwen3:8b"], "Registry-verified response.")
    r = await _post({
        "model": "qwen3:8b",
        "messages": [{"role": "user", "content": "hello"}],
    })
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "Registry-verified response."


# ── Stack max_tokens floor ────────────────────────────────────────────────────

async def test_stack_max_tokens_overrides_low_request():
    """Stack's max_tokens acts as a floor — a low request value is raised to match."""
    model_registry.register(ModelStack(
        model_id="qwen3:8b", runtime="ollama>=0.6.0",
        temperature=0.0, seed=42, max_tokens=2048,
    ))
    conn = _add_node("n1", ["qwen3:8b"], "Answer.")
    await _post({
        "model": "qwen3:8b",
        "messages": [{"role": "user", "content": "write a haiku"}],
        "max_tokens": 64,  # caller undershoots; stack floor is 2048
    })
    assert conn.ws.last_payload["max_tokens"] == 2048


async def test_stack_max_tokens_does_not_lower_high_request():
    """If the caller requests more tokens than the stack floor, honour the caller."""
    model_registry.register(ModelStack(
        model_id="qwen3:8b", runtime="ollama>=0.6.0",
        temperature=0.0, seed=42, max_tokens=2048,
    ))
    conn = _add_node("n1", ["qwen3:8b"], "Answer.")
    await _post({
        "model": "qwen3:8b",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 4096,  # caller requests more than stack floor
    })
    assert conn.ws.last_payload["max_tokens"] == 4096


async def test_unregistered_model_uses_request_max_tokens():
    """Without a stack, max_tokens comes straight from the request."""
    conn = _add_node("n1", ["llama3"], "Answer.")
    await _post({
        "model": "llama3",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 128,
    })
    assert conn.ws.last_payload["max_tokens"] == 128


# ── temperature=0.0 regression (#11) ─────────────────────────────────────────

async def test_temperature_zero_not_coerced_to_default():
    """temperature=0.0 must reach the node as 0.0, not be silently replaced by 0.7."""
    conn = _add_node("n1", ["llama3"], "Deterministic.")
    await _post({
        "model": "llama3",
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0.0,
    })
    assert conn.ws.last_payload["temperature"] == 0.0


async def test_temperature_none_uses_default():
    """When temperature is omitted, the default 0.7 is used."""
    conn = _add_node("n1", ["llama3"], "Normal.")
    await _post({
        "model": "llama3",
        "messages": [{"role": "user", "content": "hi"}],
    })
    assert conn.ws.last_payload["temperature"] == 0.7


# ── Shadow task seed propagation ──────────────────────────────────────────────

async def test_shadow_task_inherits_seed():
    """Checker (shadow) task must carry the same seed as the primary task."""
    from verification import RedundantExecutionVerifier
    import orchestrator as orc_mod

    _register(seed=55)

    dispatched: list[dict] = []

    class _CapturingWS:
        def __init__(self, node_id: str, response: str):
            self._node_id = node_id
            self._response = response
            self.last_payload = None

        async def send_text(self, data: str):
            import json as _json
            msg = _json.loads(data)
            if msg.get("type") != "task":
                return
            self.last_payload = msg["payload"]
            dispatched.append(msg["payload"])
            task_id = msg["payload"]["task_id"]

            async def _resolve():
                import asyncio
                await asyncio.sleep(0.02)
                if self._node_id in nodes:
                    nodes[self._node_id].status = NodeStatus.idle
                    nodes[self._node_id].tasks_completed += 1
                results[task_id] = TaskResult(
                    task_id=task_id,
                    node_id=self._node_id,
                    content=self._response,
                    tokens_used=3,
                )
                if task_id in pending_events:
                    pending_events[task_id].set()

            asyncio.create_task(_resolve())

    # Two nodes so the checker can be dispatched to the second
    for nid, resp in [("n1", "The answer."), ("n2", "The answer.")]:
        ws = _CapturingWS(nid, resp)
        info = NodeInfo(node_id=nid, models=["qwen3:8b"])
        conn = orc.NodeConnection(ws=ws, info=info)
        nodes[nid] = conn

    # Swap in a verifier that always rechecks
    old_verifier = orc_mod.verifier
    orc_mod.verifier = RedundantExecutionVerifier(sample_rate=1.0)
    try:
        r = await _post({
            "model": "qwen3:8b",
            "messages": [{"role": "user", "content": "hello"}],
        })
    finally:
        orc_mod.verifier = old_verifier

    assert r.status_code == 200
    assert len(dispatched) == 2, "Expected primary + shadow dispatch"
    seeds = [d["seed"] for d in dispatched]
    assert seeds[0] == 55, f"Primary seed wrong: {seeds[0]}"
    assert seeds[1] == 55, f"Shadow seed wrong: {seeds[1]}"
