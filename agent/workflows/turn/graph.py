"""Routes for one turn shared by main and child Agent sessions."""
from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.graph import START, StateGraph

from ...agentsessionstate import transitions
from ...agentsessionstate.input import UserInput
from ...core.cancellation import ExecutionContext
from .nodes import TurnContext, TurnState, finalize, model_round, prepare_turn, tool_batch

if TYPE_CHECKING:
    from ...core.agent_runtime import AgentRuntime


# Branch destinations are declared by each node's Command return type.
_TURN_GRAPH = (
    StateGraph(TurnState, context_schema=TurnContext)
    .add_node(prepare_turn)
    .add_node(model_round)
    .add_node(tool_batch)
    .add_node(finalize)
    .add_edge(START, "prepare_turn")
    .add_edge("prepare_turn", "model_round")
    .compile()
)


def run_turn(agent: AgentRuntime, prompt: str | UserInput, context: ExecutionContext) -> str:
    # Each round uses at most two nodes. Leave room for turn setup and the
    # explicit round-limit error; do not let LangGraph's default cap end the turn.
    _TURN_GRAPH.invoke(
        {"prompt": prompt},
        {"recursion_limit": 2 * agent.max_rounds + 4},
        context=TurnContext(agent, context),
    )
    return transitions.execution(agent.state)["answer"]
