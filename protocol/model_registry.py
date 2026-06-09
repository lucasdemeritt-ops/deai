"""
Model Registry — Reference Inference Stack (VERIFICATION_PROTOCOL.md §12)
---------------------------------------------------------------------------
Maps model_id → registered stack definition. A model with a registered stack
where temperature=0 and seed is set is eligible for Standard-tier
(RedundantExecutionVerifier) verification. All other models run under
ContentVerifier (accept any non-empty result, no recheck).

Persistence: registrations are kept in-memory at runtime; an optional JSON
file (set via `set_persistence(path)` or the orchestrator's `--registry-file`
flag) loads existing stacks at startup and auto-saves on each register so
restarts don't lose them (closes §12.6 first bullet).
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger("model_registry")


@dataclass
class ModelStack:
    """Pinned configuration for one model (§12.2)."""
    model_id: str
    runtime: str                          # e.g. "ollama>=0.6.0"
    format: str = ""                      # e.g. "Q4_K_M" (GGUF quantization)
    temperature: float = 0.0             # must be 0 for Standard tier
    seed: Optional[int] = None            # must be set for Standard tier
    max_tokens: int = 2048
    stop_tokens: list = field(default_factory=list)
    system_prompt: str = ""
    digest: str = ""                      # SHA-256 of model weights file(s)
    registered_at: float = field(default_factory=time.time)
    registered_by: str = ""               # orchestrator wallet address

    def is_eligible(self) -> bool:
        """Standard-tier eligibility: temperature must be 0, seed must be set."""
        return self.temperature == 0.0 and self.seed is not None

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "runtime": self.runtime,
            "format": self.format,
            "temperature": self.temperature,
            "seed": self.seed,
            "max_tokens": self.max_tokens,
            "stop_tokens": self.stop_tokens,
            "system_prompt": self.system_prompt,
            "digest": self.digest,
            "registered_at": self.registered_at,
            "registered_by": self.registered_by,
            "eligible": self.is_eligible(),
        }


class ModelRegistry:
    """
    In-memory registry of per-model reference inference stacks (§12.3).

    Re-registration overwrites and bumps registered_at — old results under
    the previous stack are not retroactively invalidated.
    """

    def __init__(self):
        self._stacks: dict[str, ModelStack] = {}
        self._persistence_path: Optional[Path] = None

    def register(self, stack: ModelStack) -> None:
        """Validate and store a stack. Raises ValueError on invalid fields."""
        if not stack.model_id:
            raise ValueError("model_id is required")
        if not stack.runtime:
            raise ValueError("runtime is required")
        if stack.temperature != 0.0:
            raise ValueError(
                f"temperature must be 0 for Standard-tier registration; "
                f"got {stack.temperature}"
            )
        if stack.seed is None:
            raise ValueError("seed is required for Standard-tier registration")
        stack.registered_at = time.time()
        self._stacks[stack.model_id] = stack
        log.info(
            f"Stack registered  model={stack.model_id}  runtime={stack.runtime}  "
            f"format={stack.format or '(unset)'}  seed={stack.seed}"
        )
        if self._persistence_path:
            try:
                self.save_to_file(self._persistence_path)
            except OSError as e:
                log.error(f"Failed to persist registry to {self._persistence_path}: {e}")

    def get(self, model_id: str) -> Optional[ModelStack]:
        """Look up a stack by model_id. Returns None if not registered."""
        return self._stacks.get(model_id)

    def is_eligible(self, model_id: str) -> bool:
        """True if model is registered and meets Standard-tier criteria (§12.5)."""
        stack = self._stacks.get(model_id)
        return stack is not None and stack.is_eligible()

    def all_stacks(self) -> list[ModelStack]:
        return list(self._stacks.values())

    def __len__(self) -> int:
        return len(self._stacks)

    # ── Persistence (§12.6 — durable across orchestrator restarts) ────────────

    def set_persistence(self, path) -> None:
        """Subsequent ``register()`` calls will auto-save to this path. Pass
        ``None`` to disable autosave."""
        self._persistence_path = Path(path) if path else None

    def save_to_file(self, path) -> None:
        """Atomic write: serialize all stacks to ``path`` via a temp file and
        ``os.replace`` so a crash mid-write never leaves a partial file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        payload = {"version": 1, "stacks": [s.to_dict() for s in self._stacks.values()]}
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, p)

    def load_from_file(self, path, *, replace: bool = True) -> int:
        """Load stacks from ``path``. Missing file is a no-op (returns 0).
        Invalid entries are skipped with a warning; returns the count loaded."""
        p = Path(path)
        if not p.exists():
            return 0
        data = json.loads(p.read_text(encoding="utf-8"))
        if replace:
            self._stacks.clear()
        loaded = 0
        for raw in data.get("stacks", []):
            try:
                stack = ModelStack(
                    model_id=raw["model_id"],
                    runtime=raw["runtime"],
                    format=raw.get("format", ""),
                    temperature=float(raw.get("temperature", 0.0)),
                    seed=raw.get("seed"),
                    max_tokens=int(raw.get("max_tokens", 2048)),
                    stop_tokens=list(raw.get("stop_tokens", [])),
                    system_prompt=raw.get("system_prompt", ""),
                    digest=raw.get("digest", ""),
                    registered_at=float(raw.get("registered_at", time.time())),
                    registered_by=raw.get("registered_by", ""),
                )
                self._stacks[stack.model_id] = stack
                loaded += 1
            except (KeyError, TypeError, ValueError) as e:
                log.warning(f"Skipping invalid registry entry in {path}: {e}")
        log.info(f"Registry loaded  path={path}  stacks={loaded}")
        return loaded

    @classmethod
    def from_file(cls, path) -> "ModelRegistry":
        """Construct a registry pre-loaded from ``path`` (empty if missing)."""
        reg = cls()
        reg.load_from_file(path)
        return reg
