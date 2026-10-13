from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """可记录、可回放、可传输的核心状态。"""

    model: dict[str, str]
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    mcp_servers: list[dict[str, Any]]
    spill_enabled: bool
    status: str
