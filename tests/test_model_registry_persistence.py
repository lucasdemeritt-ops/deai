"""
Registry persistence (§12.6) — atomic save, load, autosave on register.
Pure I/O against tmp_path; no network, no orchestrator.
"""

import json

import pytest

from protocol.model_registry import ModelRegistry, ModelStack


def _stack(model_id: str, seed: int = 42) -> ModelStack:
    return ModelStack(
        model_id=model_id, runtime="ollama>=0.6.0", format="Q4_K_M",
        temperature=0.0, seed=seed, max_tokens=2048,
    )


# ── save / load round-trip ────────────────────────────────────────────────────

def test_save_then_load_preserves_stacks(tmp_path):
    p = tmp_path / "registry.json"
    a = ModelRegistry()
    a.register(_stack("llama3:8b", seed=1))
    a.register(_stack("qwen3:8b",  seed=2))
    a.save_to_file(p)

    b = ModelRegistry()
    assert b.load_from_file(p) == 2
    assert len(b) == 2
    assert b.is_eligible("llama3:8b") and b.is_eligible("qwen3:8b")
    assert b.get("llama3:8b").seed == 1
    assert b.get("qwen3:8b").seed == 2


def test_save_is_atomic_and_leaves_no_tmp_file(tmp_path):
    p = tmp_path / "r.json"
    reg = ModelRegistry()
    reg.register(_stack("m"))
    reg.save_to_file(p)
    assert p.exists()
    assert not p.with_suffix(p.suffix + ".tmp").exists()
    payload = json.loads(p.read_text())
    assert payload["version"] == 1
    assert payload["stacks"][0]["model_id"] == "m"


def test_load_missing_file_returns_zero(tmp_path):
    reg = ModelRegistry()
    assert reg.load_from_file(tmp_path / "nope.json") == 0
    assert len(reg) == 0


def test_load_skips_invalid_entries_without_crashing(tmp_path, caplog):
    p = tmp_path / "r.json"
    p.write_text(json.dumps({
        "version": 1,
        "stacks": [
            {"model_id": "good", "runtime": "ollama>=0.6.0", "temperature": 0.0,
             "seed": 1, "max_tokens": 2048},
            {"runtime": "missing model_id"},   # invalid → skipped
            "not a dict",                       # invalid → skipped
        ],
    }))
    reg = ModelRegistry()
    assert reg.load_from_file(p) == 1
    assert reg.is_eligible("good")


def test_load_replace_false_merges(tmp_path):
    p = tmp_path / "r.json"
    a = ModelRegistry()
    a.register(_stack("a"))
    a.save_to_file(p)
    b = ModelRegistry()
    b.register(_stack("b"))
    b.load_from_file(p, replace=False)
    assert {s.model_id for s in b.all_stacks()} == {"a", "b"}


def test_load_replace_true_replaces(tmp_path):
    p = tmp_path / "r.json"
    a = ModelRegistry()
    a.register(_stack("a"))
    a.save_to_file(p)
    b = ModelRegistry()
    b.register(_stack("b"))
    b.load_from_file(p)  # replace=True default
    assert {s.model_id for s in b.all_stacks()} == {"a"}


# ── autosave on register ──────────────────────────────────────────────────────

def test_autosave_persists_each_registration(tmp_path):
    p = tmp_path / "r.json"
    reg = ModelRegistry()
    reg.set_persistence(p)
    reg.register(_stack("m1"))
    assert p.exists()
    assert "m1" in p.read_text()
    reg.register(_stack("m2"))
    payload = json.loads(p.read_text())
    assert {s["model_id"] for s in payload["stacks"]} == {"m1", "m2"}


def test_autosave_can_be_disabled(tmp_path):
    p = tmp_path / "r.json"
    reg = ModelRegistry()
    reg.set_persistence(p)
    reg.register(_stack("a"))
    assert p.exists()

    reg.set_persistence(None)
    reg.register(_stack("b"))
    # Disabling autosave means the file is no longer updated for "b".
    payload = json.loads(p.read_text())
    assert {s["model_id"] for s in payload["stacks"]} == {"a"}


def test_autosave_creates_parent_directory(tmp_path):
    p = tmp_path / "nested" / "deep" / "r.json"
    reg = ModelRegistry()
    reg.set_persistence(p)
    reg.register(_stack("m"))
    assert p.exists()


# ── from_file classmethod ─────────────────────────────────────────────────────

def test_from_file_constructs_preloaded_registry(tmp_path):
    p = tmp_path / "r.json"
    a = ModelRegistry()
    a.register(_stack("preloaded"))
    a.save_to_file(p)

    b = ModelRegistry.from_file(p)
    assert b.is_eligible("preloaded")


def test_from_file_with_missing_file_is_empty_not_error(tmp_path):
    reg = ModelRegistry.from_file(tmp_path / "absent.json")
    assert len(reg) == 0
