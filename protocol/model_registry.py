"""
Model Registry — Reference Inference Stack (VERIFICATION_PROTOCOL.md §12)
---------------------------------------------------------------------------
Maps model_id → registered stack definition. A model with a registered stack
where temperature=0 and seed is set is eligible for Standard-tier
(RedundantExecutionVerifier) verification. All other models run under
ContentVerifier (accept any non-empty result, no recheck).

This is an in-memory registry. Persistence and on-chain commit are open items
(§12.6) — registrations are lost on orchestrator restart.
"""

import logging
import time
from dataclasses import dataclass, field
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
