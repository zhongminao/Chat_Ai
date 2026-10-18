"""Assemble agent state and resources; session lifecycle stays in the registry/runtime."""
from functools import partial

from .agent_runtime import AgentRuntime
from ..model.catalog import ModelCatalog
from ..tools.mcp.client import McpClient
from ..tools.router import ToolRouter
from ..workflow.message_replay import restore_model_messages
from ..workflow.state import AgentState


def build_state(config, metadata: dict, records: list[dict]) -> AgentState:
    role = "child" if metadata.get("parent_session_id") else "main"
    catalog = ModelCatalog(config.providers_file)
    model = metadata.get("model") or catalog.default().as_dict()
    for event in records:
        if event["type"] == "model.changed":
            model = event["new"]
    target = catalog.resolve(model["provider"], model["name"])
    prompt = config.child_system_prompt if role == "child" else config.system_prompt
    return {
        "role": role,
        "model": target.as_dict(),
        "messages": restore_model_messages(records, {
            "role": "system", "content": prompt.replace("{workspace}", str(config.workspace.resolve())),
        }),
        "execution": None,
    }


def build_agent(runtime) -> AgentRuntime:
    registry = runtime.registry
    config = registry.config
    main = runtime.state["role"] == "main"
    tools = ToolRouter(config.workspace, McpClient(config.mcp) if config.mcp else None,
                       delegate=partial(registry.delegate, runtime.session.id) if main else None,
                       watch=registry.monitor(runtime.session.id).watch if main else None,
                       approval=partial(runtime.approvals.request, session_id=runtime.session.id,
                                        workspace=str(config.workspace)))
    return AgentRuntime(state=runtime.state, catalog=ModelCatalog(config.providers_file),
                        session_id=runtime.session.id, spill=config.spill,
                        workspace=config.workspace, log=runtime.session.events, images=runtime.session.images, max_rounds=config.max_rounds,
                        output=lambda text: None, tools=tools,
                        control=runtime.control, on_submit=runtime.submitted, context_config=config.context,
                        steering=runtime.steering)
