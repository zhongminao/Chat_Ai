from typing import Any

from .commands import SwitchModel
from .state import AgentState


def apply(state: AgentState, command: SwitchModel, target: dict[str, str]) -> AgentState:
    return {**state, "model": dict(target)}
