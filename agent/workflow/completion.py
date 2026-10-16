"""Pure completion rules, independent of sessions, models and I/O."""
from typing import Literal

from .state import AgentState
from .transitions import execution


REMINDER = (
    "Your final report has not been submitted. Ordinary text does not complete this child task. "
    "Call submit alone with the complete final Markdown report, including any deliverable paths."
)
MISSING_SUBMIT = "Child ended without calling submit."


def decide(state: AgentState, max_rounds: int) -> Literal["end", "remind", "fail"]:
    current = execution(state)
    if state["role"] == "main" or current["report"] is not None:
        return "end"
    if current["completion_reminders"] == 0 and current["round"] + 1 < max_rounds:
        return "remind"
    return "fail"
