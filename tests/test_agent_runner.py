"""
Unit tests for application/agent_runner.py.

All network calls and sleeps are mocked — tests run instantly with no
orchestrator or inference hardware required.
"""

import argparse
import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch, call

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "application"))

import agent_runner
from agent_runner import (
    load_prompts, run, send_task, send_with_retry, RETRY_BACKOFFS,
    ESTIMATED_COST_PER_TASK,
)


def _http_error(code: int) -> httpx.HTTPStatusError:
    resp = MagicMock()
    resp.status_code = code
    return httpx.HTTPStatusError(str(code), request=MagicMock(), response=resp)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _args(**kwargs) -> argparse.Namespace:
    defaults = dict(
        endpoint="http://localhost:8000",
        model="any",
        budget=None,
        interval=0.0,
        api_key=None,
        loop=False,
        prompt="Test prompt",
        prompt_file=None,
        output_file=None,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _response(content: str = "Mock response.", tokens: int = 5) -> dict:
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"total_tokens": tokens},
    }


# ── load_prompts ───────────────────────────────────────────────────────────────

def test_load_prompts_reads_lines(tmp_path):
    f = tmp_path / "prompts.txt"
    f.write_text("First prompt\nSecond prompt\n\nThird prompt\n")
    result = load_prompts(str(f))
    assert result == ["First prompt", "Second prompt", "Third prompt"]


def test_load_prompts_skips_blank_lines(tmp_path):
    f = tmp_path / "prompts.txt"
    f.write_text("\n\nOnly line\n\n")
    assert load_prompts(str(f)) == ["Only line"]


# ── send_task ──────────────────────────────────────────────────────────────────

def test_send_task_sets_content_type():
    with patch("agent_runner.httpx.Client") as MockClient:
        mock_resp = MagicMock()
        mock_resp.json.return_value = _response()
        MockClient.return_value.__enter__.return_value.post.return_value = mock_resp

        send_task("http://localhost:8000", "llama3", "hi", None)

        _, kwargs = MockClient.return_value.__enter__.return_value.post.call_args
        assert kwargs["headers"]["Content-Type"] == "application/json"


def test_send_task_adds_auth_header_when_key_provided():
    with patch("agent_runner.httpx.Client") as MockClient:
        mock_resp = MagicMock()
        mock_resp.json.return_value = _response()
        MockClient.return_value.__enter__.return_value.post.return_value = mock_resp

        send_task("http://localhost:8000", "llama3", "hi", "mykey")

        _, kwargs = MockClient.return_value.__enter__.return_value.post.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer mykey"


def test_send_task_no_auth_header_when_no_key():
    with patch("agent_runner.httpx.Client") as MockClient:
        mock_resp = MagicMock()
        mock_resp.json.return_value = _response()
        MockClient.return_value.__enter__.return_value.post.return_value = mock_resp

        send_task("http://localhost:8000", "llama3", "hi", None)

        _, kwargs = MockClient.return_value.__enter__.return_value.post.call_args
        assert "Authorization" not in kwargs["headers"]


# ── run() — single prompt, no loop ────────────────────────────────────────────

def test_run_single_prompt_completes_one_task():
    with patch("agent_runner.send_task", return_value=_response()) as mock_send, \
         patch("agent_runner.time.sleep"):
        run(_args(prompt="Hello", interval=0.0))

    mock_send.assert_called_once()
    _, kwargs = mock_send.call_args if mock_send.call_args.kwargs else (mock_send.call_args[0], {})
    args_pos = mock_send.call_args[0]
    assert args_pos[2] == "Hello"


def test_run_multiple_prompts_run_in_order(tmp_path):
    f = tmp_path / "p.txt"
    f.write_text("First\nSecond\nThird\n")
    calls = []

    def fake_send(endpoint, model, prompt, api_key):
        calls.append(prompt)
        return _response(prompt)

    with patch("agent_runner.send_task", side_effect=fake_send), \
         patch("agent_runner.time.sleep"):
        run(_args(prompt=None, prompt_file=str(f), interval=0.0))

    assert calls == ["First", "Second", "Third"]


# ── run() — loop mode ──────────────────────────────────────────────────────────

def test_run_loop_cycles_prompts_until_budget():
    call_count = {"n": 0}

    def fake_send(*a, **kw):
        call_count["n"] += 1
        return _response()

    # budget = 25, cost = 10 per task → pauses after 3rd task (30 >= 25)
    # mock sleep raises KeyboardInterrupt on first call (budget pause)
    with patch("agent_runner.send_task", side_effect=fake_send), \
         patch("agent_runner.time.sleep", side_effect=KeyboardInterrupt):
        run(_args(prompt="Hi", loop=True, budget=25.0, interval=0.0))

    assert call_count["n"] == 3


# ── run() — budget enforcement ────────────────────────────────────────────────

def test_run_stops_at_budget():
    sent = {"n": 0}

    def fake_send(*a, **kw):
        sent["n"] += 1
        return _response()

    # budget = 10 = exactly one task; second iteration hits budget pause
    with patch("agent_runner.send_task", side_effect=fake_send), \
         patch("agent_runner.time.sleep", side_effect=[None, KeyboardInterrupt]):
        run(_args(prompt="Hi", loop=True, budget=10.0, interval=1.0))

    assert sent["n"] == 1


def test_run_unlimited_budget_runs_all_prompts(tmp_path):
    f = tmp_path / "p.txt"
    f.write_text("A\nB\nC\n")
    sent = []

    def fake_send(ep, model, prompt, key):
        sent.append(prompt)
        return _response()

    with patch("agent_runner.send_task", side_effect=fake_send), \
         patch("agent_runner.time.sleep"):
        run(_args(prompt=None, prompt_file=str(f), budget=None, interval=0.0))

    assert sent == ["A", "B", "C"]


# ── run() — output file ───────────────────────────────────────────────────────

def test_run_writes_output_file(tmp_path):
    out = tmp_path / "out.jsonl"

    with patch("agent_runner.send_task", return_value=_response("Answer.", 7)), \
         patch("agent_runner.time.sleep"):
        run(_args(prompt="Question?", output_file=str(out), interval=0.0))

    lines = out.read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["prompt"] == "Question?"
    assert record["response"] == "Answer."
    assert record["tokens"] == 7
    assert record["task"] == 1


def test_run_appends_multiple_records(tmp_path):
    f = tmp_path / "p.txt"
    f.write_text("A\nB\n")
    out = tmp_path / "out.jsonl"

    with patch("agent_runner.send_task", return_value=_response()), \
         patch("agent_runner.time.sleep"):
        run(_args(prompt=None, prompt_file=str(f), output_file=str(out), interval=0.0))

    lines = out.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["task"] == 1
    assert json.loads(lines[1])["task"] == 2


# ── run() — error handling ────────────────────────────────────────────────────

def test_run_handles_503_without_crashing():
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    err = httpx.HTTPStatusError("503", request=MagicMock(), response=mock_resp)

    call_count = {"n": 0}

    def fake_send(*a, **kw):
        call_count["n"] += 1
        raise err

    with patch("agent_runner.send_task", side_effect=fake_send), \
         patch("agent_runner.time.sleep"):
        run(_args(prompt="Hi", interval=0.0))

    assert call_count["n"] == 1  # tried once, failed, moved on


def test_run_handles_generic_error_without_crashing():
    with patch("agent_runner.send_task", side_effect=Exception("network down")), \
         patch("agent_runner.time.sleep"):
        run(_args(prompt="Hi", interval=0.0))  # should not raise


# ── load_prompts encoding (#9) ────────────────────────────────────────────────

def test_load_prompts_handles_utf16_bom(tmp_path):
    f = tmp_path / "ps16.txt"
    f.write_bytes("What year was Python created?\nSecond\n".encode("utf-16"))
    assert load_prompts(str(f)) == ["What year was Python created?", "Second"]


def test_load_prompts_handles_utf8_bom(tmp_path):
    f = tmp_path / "ps8.txt"
    f.write_bytes("﻿First\nSecond\n".encode("utf-8"))
    assert load_prompts(str(f)) == ["First", "Second"]


# ── send_with_retry (#7) ──────────────────────────────────────────────────────

def test_send_with_retry_returns_on_success():
    with patch("agent_runner.send_task", return_value=_response("ok")) as m:
        assert send_with_retry("http://x", "any", "hi", None) == _response("ok")
    assert m.call_count == 1


def test_send_with_retry_retries_504_then_succeeds():
    seq = [_http_error(504), _http_error(504), _response("recovered")]
    with patch("agent_runner.send_task", side_effect=seq) as m, \
         patch("agent_runner.time.sleep") as sleep:
        out = send_with_retry("http://x", "any", "hi", None)
    assert out == _response("recovered")
    assert m.call_count == 3
    assert sleep.call_count == 2  # one sleep before each retry


def test_send_with_retry_raises_after_exhausting_504():
    seq = [_http_error(504)] * (len(RETRY_BACKOFFS) + 1)
    with patch("agent_runner.send_task", side_effect=seq) as m, \
         patch("agent_runner.time.sleep"):
        with pytest.raises(httpx.HTTPStatusError):
            send_with_retry("http://x", "any", "hi", None)
    assert m.call_count == len(RETRY_BACKOFFS) + 1


def test_send_with_retry_does_not_retry_503():
    with patch("agent_runner.send_task", side_effect=_http_error(503)) as m, \
         patch("agent_runner.time.sleep"):
        with pytest.raises(httpx.HTTPStatusError):
            send_with_retry("http://x", "any", "hi", None)
    assert m.call_count == 1  # 503 is not retried


def test_run_records_failed_task_to_output(tmp_path):
    out = tmp_path / "out.jsonl"
    with patch("agent_runner.send_task", side_effect=Exception("boom")), \
         patch("agent_runner.time.sleep"):
        run(_args(prompt="Q", output_file=str(out), interval=0.0))
    rec = json.loads(out.read_text().strip())
    assert rec["status"] == "failed"
    assert "boom" in rec["error"]
