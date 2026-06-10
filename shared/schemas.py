from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from enum import Enum
import uuid


class Role(str, Enum):
    system = "system"
    user = "user"
    assistant = "assistant"


class Message(BaseModel):
    role: Role
    content: str


# ── Inbound API request (OpenAI-compatible) ──────────────────────────────────

class ChatRequest(BaseModel):
    model: str
    messages: List[Message]
    max_tokens: Optional[int] = 512
    temperature: Optional[float] = 0.7
    stream: Optional[bool] = False
    project: Optional[str] = None  # route only to nodes dedicated to this project


# ── Internal task representation ──────────────────────────────────────────────

class Task(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    model: str
    messages: List[Message]
    max_tokens: int = 512
    temperature: float = 0.7
    seed: Optional[int] = None        # set by orchestrator when model has a registered stack
    submitted_at: float = Field(default_factory=lambda: __import__('time').time())
    project: Optional[str] = None  # inherited from ChatRequest.project


class TaskStatus(str, Enum):
    pending = "pending"
    dispatched = "dispatched"
    complete = "complete"
    failed = "failed"


# ── Node registration and status ──────────────────────────────────────────────

class NodeInfo(BaseModel):
    node_id: str
    models: List[str]          # e.g. ["llama3", "mistral", "any"]
    gpu: bool = False
    vram_gb: Optional[float] = None
    ram_gb: Optional[float] = None
    wallet: Optional[str] = None   # EVM wallet address; required for on-chain rewards
    project: Optional[str] = None  # if set, node only accepts tasks for this project


class NodeStatus(str, Enum):
    idle = "idle"
    busy = "busy"
    offline = "offline"


# ── WebSocket message envelope ────────────────────────────────────────────────

class WSMessage(BaseModel):
    type: str
    payload: Dict[str, Any] = {}


# ── Task result ───────────────────────────────────────────────────────────────

class TaskResult(BaseModel):
    task_id: str
    node_id: str
    content: str
    tokens_used: int
    verified: bool = False


# ── Batch fan-out (VISION.md Stage 1 — job parallelism) ──────────────────────

class BatchRequest(BaseModel):
    """One job decomposed into independent sub-tasks, fanned out across the
    network in parallel. Each prompt becomes one sub-task that runs through
    the full verified pipeline (stack params, verification sampling, accrual
    per sub-task — ECONOMICS.md §3 Stage 1)."""
    model: str
    prompts: List[str]
    max_tokens: Optional[int] = 512
    temperature: Optional[float] = 0.7
    project: Optional[str] = None
    max_parallel: Optional[int] = None  # cap concurrent dispatches (default: nodes online)


class BatchItem(BaseModel):
    index: int                       # position of the prompt in the request
    status: str                      # "ok" | "error"
    content: Optional[str] = None
    error: Optional[str] = None
    node_id: Optional[str] = None    # which node served this sub-task
    tokens: int = 0


class BatchResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"batch-{uuid.uuid4().hex[:12]}")
    object: str = "batch.completion"
    model: str
    items: List[BatchItem]
    completed: int
    failed: int


# ── OpenAI-compatible response shape ─────────────────────────────────────────

class Choice(BaseModel):
    index: int = 0
    message: Message
    finish_reason: str = "stop"


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion"
    model: str
    choices: List[Choice]
    usage: Usage
