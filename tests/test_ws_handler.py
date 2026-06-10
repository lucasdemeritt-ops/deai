"""
WebSocket handler hardening: a node may only complete/fail the task it was
actually assigned. Late results are dropped (no orphan leak in `results`),
foreign completions never wake another task's waiter, and a failed task is
counted once (by the HTTP path), not twice.
"""

import asyncio
import json

from starlette.testclient import TestClient

import orchestrator as orc
from orchestrator import app, nodes, results, pending_events, stats


def _register(ws, node_id: str):
    ws.send_text(json.dumps({
        "type": "register",
        "payload": {"node_id": node_id, "models": ["llama3"]},
    }))
    ack = json.loads(ws.receive_text())
    assert ack["type"] == "ack"


def _complete(ws, task_id: str, node_id: str, content: str = "answer"):
    ws.send_text(json.dumps({
        "type": "task_complete",
        "payload": {
            "task_id": task_id, "node_id": node_id,
            "content": content, "tokens_used": 1,
        },
    }))


def setup_function(_):
    nodes.clear()
    results.clear()
    pending_events.clear()
    stats.update(requests=0, completed=0, failed=0)


def test_unassigned_completion_is_dropped_not_stored():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/node") as ws:
            _register(ws, "n1")
            # n1 was never dispatched anything; it claims a random task.
            _complete(ws, "task-i-was-never-given", "n1")
        # Socket closed → handler finished processing all prior messages.
    assert results == {}                       # no orphan stored
    assert nodes == {}                         # cleaned up on disconnect


def test_foreign_completion_does_not_wake_real_waiter():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/node") as ws:
            _register(ws, "intruder")
            # A real task is pending, assigned to some *other* node.
            event = asyncio.Event()
            pending_events["task-of-another-node"] = event
            _complete(ws, "task-of-another-node", "intruder", "forged result")
        assert not event.is_set()              # waiter untouched
        assert "task-of-another-node" not in results
        pending_events.clear()


def test_assigned_completion_still_works():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/node") as ws:
            _register(ws, "n1")
            event = asyncio.Event()
            pending_events["t1"] = event
            nodes["n1"].current_task_id = "t1"   # orchestrator assigned it
            _complete(ws, "t1", "n1", "real answer")
        assert event.is_set()
        assert results["t1"].content == "real answer"
        results.clear()
        pending_events.clear()


def test_completion_after_timeout_is_not_leaked():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/node") as ws:
            _register(ws, "n1")
            # Assigned, but the HTTP waiter already timed out and removed
            # its pending event.
            nodes["n1"].current_task_id = "t-timed-out"
            _complete(ws, "t-timed-out", "n1")
        assert results == {}                   # dropped, no leak


def test_task_failed_does_not_double_count():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/node") as ws:
            _register(ws, "n1")
            event = asyncio.Event()
            pending_events["t-fail"] = event
            nodes["n1"].current_task_id = "t-fail"
            ws.send_text(json.dumps({
                "type": "task_failed",
                "payload": {"task_id": "t-fail", "node_id": "n1"},
            }))
        assert event.is_set()                  # waiter woken (it counts the failure)
        assert stats["failed"] == 0            # WS side no longer increments
        pending_events.clear()


def test_stale_task_failed_is_ignored():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/node") as ws:
            _register(ws, "n1")
            event = asyncio.Event()
            pending_events["someone-elses-task"] = event
            ws.send_text(json.dumps({
                "type": "task_failed",
                "payload": {"task_id": "someone-elses-task", "node_id": "n1"},
            }))
        assert not event.is_set()
        pending_events.clear()
