"""Assemble agent state and resources; session lifecycle stays in the registry/runtime."""
from functools import partial

from .agent_runtime import AgentRuntime
from ..model.catalog import ModelCatalog
from ..tools.mcp.client import McpClient
from ..tools.router import ToolRouter
from ..agentsessionstate.message_replay import restore_model_messages
from ..agentsessionstate.state import AgentState


def build_state(config, metadata: dict, records: list[dict], catalog=None) -> AgentState:
    role = "child" if metadata.get("parent_session_id") else "main"
    catalog = catalog or ModelCatalog(config.providers_file)
    model = metadata.get("model") or catalog.default().as_dict()
    for event in records:
        if event["type"] == "model.changed":
            model = event["new"]
    target = catalog.resolve(model["provider"], model["name"])
    if "reasoning_effort" in model:
        from dataclasses import replace
        target = replace(target, reasoning_effort=model["reasoning_effort"])
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
    # Configured services load by default; previously enabled ad-hoc URLs are
    # recovered from durable events when this session is reconstructed.
    servers = {alias: server["url"] for alias, server in config.mcp.items()}
    for event in runtime.session.events.read():
        if event["type"] == "mcp.enabled" and event.get("url") and event["alias"] not in config.mcp:
            servers[event["alias"]] = event["url"]
    tools = ToolRouter(config.workspace, McpClient(servers),
                       read_file_config=config.read_file,
                       web_search_config=config.mcp.get("web", {}).get("search", {}),
                       delegate=partial(registry.delegate, runtime.session.id) if main else None,
                       watch=registry.monitor(runtime.session.id).watch,
                       approval=partial(runtime.approvals.request, session_id=runtime.session.id,
                                        workspace=str(config.workspace)),
                       registry=registry, session_id=runtime.session.id)
    return AgentRuntime(state=runtime.state, catalog=registry.catalog.fork(),
                        session_id=runtime.session.id, spill=config.spill,
                        workspace=config.workspace, log=runtime.session.events, images=runtime.session.images, max_rounds=config.max_rounds,
                        output=lambda text: None, tools=tools,
                        control=runtime.control, on_submit=runtime.submitted, context_config=config.context,
                        steering=runtime.steering, begin_submit=runtime.begin_submit,
                        release_submit=runtime.release_submit)
