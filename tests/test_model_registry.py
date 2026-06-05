"""Unit and integration tests for the model registry (VERIFICATION_PROTOCOL.md §12)."""

import time
import pytest
from starlette.testclient import TestClient

from model_registry import ModelRegistry, ModelStack
import orchestrator as orc
from orchestrator import app, nodes, model_registry


# ── Helpers ────────────────────────────────────────────────────────────────────

def _stack(**kwargs) -> ModelStack:
    defaults = dict(model_id="qwen3:8b", runtime="ollama>=0.6.0", temperature=0.0, seed=42)
    return ModelStack(**{**defaults, **kwargs})


@pytest.fixture(autouse=True)
def reset_registry():
    model_registry._stacks.clear()
    yield
    model_registry._stacks.clear()


# ── ModelStack ─────────────────────────────────────────────────────────────────

class TestModelStack:
    def test_eligible_with_temp_zero_and_seed(self):
        assert _stack().is_eligible()

    def test_ineligible_without_seed(self):
        assert not _stack(seed=None).is_eligible()

    def test_ineligible_with_nonzero_temp(self):
        assert not _stack(temperature=0.7).is_eligible()

    def test_to_dict_includes_eligible_flag(self):
        d = _stack().to_dict()
        assert d["eligible"] is True
        assert d["model_id"] == "qwen3:8b"
        assert d["seed"] == 42
        assert d["temperature"] == 0.0

    def test_to_dict_ineligible_flag_false_without_seed(self):
        assert _stack(seed=None).to_dict()["eligible"] is False


# ── ModelRegistry ──────────────────────────────────────────────────────────────

class TestModelRegistry:
    def setup_method(self):
        self.registry = ModelRegistry()

    def test_empty_has_no_stacks(self):
        assert len(self.registry) == 0
        assert self.registry.all_stacks() == []

    def test_register_and_get(self):
        self.registry.register(_stack())
        s = self.registry.get("qwen3:8b")
        assert s is not None
        assert s.model_id == "qwen3:8b"
        assert s.seed == 42

    def test_get_unknown_returns_none(self):
        assert self.registry.get("unknown:model") is None

    def test_is_eligible_registered(self):
        self.registry.register(_stack())
        assert self.registry.is_eligible("qwen3:8b")

    def test_is_eligible_unregistered(self):
        assert not self.registry.is_eligible("not:registered")

    def test_register_rejects_nonzero_temperature(self):
        with pytest.raises(ValueError, match="temperature must be 0"):
            self.registry.register(_stack(temperature=0.5))

    def test_register_rejects_missing_seed(self):
        with pytest.raises(ValueError, match="seed is required"):
            self.registry.register(_stack(seed=None))

    def test_register_rejects_empty_model_id(self):
        with pytest.raises(ValueError, match="model_id is required"):
            self.registry.register(_stack(model_id=""))

    def test_register_rejects_empty_runtime(self):
        with pytest.raises(ValueError, match="runtime is required"):
            self.registry.register(_stack(runtime=""))

    def test_reregistration_overwrites(self):
        self.registry.register(_stack(seed=42))
        self.registry.register(_stack(seed=99))
        assert self.registry.get("qwen3:8b").seed == 99

    def test_reregistration_bumps_registered_at(self):
        self.registry.register(_stack())
        t1 = self.registry.get("qwen3:8b").registered_at
        time.sleep(0.01)
        self.registry.register(_stack())
        t2 = self.registry.get("qwen3:8b").registered_at
        assert t2 > t1

    def test_all_stacks_returns_all(self):
        self.registry.register(_stack(model_id="a:1b", runtime="ollama>=0.6.0", seed=1))
        self.registry.register(_stack(model_id="b:7b", runtime="ollama>=0.6.0", seed=2))
        ids = {s.model_id for s in self.registry.all_stacks()}
        assert ids == {"a:1b", "b:7b"}
        assert len(self.registry) == 2


# ── Admin HTTP endpoints ───────────────────────────────────────────────────────

class TestAdminEndpoints:
    def test_list_empty(self):
        with TestClient(app) as client:
            r = client.get("/admin/model-registry")
        assert r.status_code == 200
        assert r.json()["stacks"] == []

    def test_register_and_list(self):
        with TestClient(app) as client:
            r = client.post("/admin/model-registry", json={
                "model_id": "qwen3:8b",
                "runtime": "ollama>=0.6.0",
                "seed": 42,
            })
        assert r.status_code == 201
        body = r.json()["registered"]
        assert body["model_id"] == "qwen3:8b"
        assert body["seed"] == 42
        assert body["eligible"] is True

        with TestClient(app) as client:
            r = client.get("/admin/model-registry")
        assert len(r.json()["stacks"]) == 1

    def test_get_registered(self):
        with TestClient(app) as client:
            client.post("/admin/model-registry", json={
                "model_id": "qwen3:8b",
                "runtime": "ollama>=0.6.0",
                "seed": 42,
            })
            r = client.get("/admin/model-registry/qwen3:8b")
        assert r.status_code == 200
        assert r.json()["model_id"] == "qwen3:8b"

    def test_get_unknown_404(self):
        with TestClient(app) as client:
            r = client.get("/admin/model-registry/not:registered")
        assert r.status_code == 404

    def test_register_invalid_temperature_422(self):
        with TestClient(app) as client:
            r = client.post("/admin/model-registry", json={
                "model_id": "qwen3:8b",
                "runtime": "ollama>=0.6.0",
                "seed": 42,
                "temperature": 0.7,
            })
        assert r.status_code == 422
        assert "temperature must be 0" in r.json()["detail"]

    def test_register_missing_seed_422(self):
        with TestClient(app) as client:
            r = client.post("/admin/model-registry", json={
                "model_id": "qwen3:8b",
                "runtime": "ollama>=0.6.0",
            })
        assert r.status_code == 422  # seed is required field in request model

    def test_reregistration_overwrites(self):
        with TestClient(app) as client:
            client.post("/admin/model-registry", json={
                "model_id": "qwen3:8b", "runtime": "ollama>=0.6.0", "seed": 42,
            })
            client.post("/admin/model-registry", json={
                "model_id": "qwen3:8b", "runtime": "ollama>=0.6.0", "seed": 99,
            })
            r = client.get("/admin/model-registry/qwen3:8b")
        assert r.json()["seed"] == 99
