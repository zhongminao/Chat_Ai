from copy import deepcopy
from dataclasses import dataclass
from threading import Lock
from uuid import uuid4

from .cancellation import CancellationToken


@dataclass
class Step:
    id: str
    phase: str
    token: CancellationToken
    tool: dict | None = None


class ExecutionControl:
    def __init__(self):
        self._signals: set[str] = set()
        self._active: CancellationToken | None = None
        self._lock = Lock()
        self._step: Step | None = None
        self._pending: list[dict] = []

    def mark_stopped(self) -> CancellationToken | None:
        with self._lock:
            self._signals.add("stop")
            return self._active

    @property
    def stopped(self) -> bool:
        with self._lock:
            return "stop" in self._signals

    def clear_stop(self) -> None:
        with self._lock:
            self._signals.discard("stop")

    def bind(self, token: CancellationToken) -> None:
        with self._lock:
            self._active = token
            stopped = "stop" in self._signals
        if stopped:
            token.cancel()

    def unbind(self, token: CancellationToken) -> None:
        with self._lock:
            if self._active is token:
                self._active = None

    def pending_tools(self, calls) -> None:
        with self._lock:
            self._pending = [{"call_id": call.id, "tool": call.name, "arguments": call.arguments} for call in calls]

    def start_step(self, phase: str) -> Step:
        with self._lock:
            tool = self._pending.pop(0) if phase == "tool" else None
            self._step = Step(uuid4().hex, phase, CancellationToken(), tool)
            return self._step

    def end_step(self, step: Step) -> None:
        with self._lock:
            if self._step is step:
                self._step = None

    def inspect(self) -> dict:
        with self._lock:
            step = self._step
            return deepcopy({"phase": step.phase if step else "between_steps",
                             "step_id": step.id if step else None,
                             "current_tool": step.tool if step else None,
                             "pending_tools": self._pending})

    def interrupt_target(self, expected: str | None) -> tuple[str, CancellationToken | None]:
        with self._lock:
            step = self._step
            if not step or (expected is not None and step.id != expected):
                return "at_boundary", None
            if step.tool and step.tool["tool"] == "watch":
                return "wake_watch", None
            return "interrupt_requested", step.token
