"""JSON-serializable agent data; live resources belong to the runtimes."""
from typing import Any, Literal, TypedDict


class ExecutionState(TypedDict):
    id: str
    status: Literal['running', 'completed', 'cancelled', 'failed']
    phase: Literal['model', 'tools', 'done']
    round: int
    completion_reminders: int
    answer: str
    report: str | None
    report_path: str | None
    error: str | None


class AgentState(TypedDict):
    role: Literal['main', 'child']
    model: dict[str, str]
    messages: list[dict[str, Any]]
    execution: ExecutionState | None


class StateUpdate(TypedDict, total=False):
    model: dict[str, str]
    messages: list[dict[str, Any]]
    execution: ExecutionState | None
