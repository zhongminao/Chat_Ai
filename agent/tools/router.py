from typing import Any

from ..core.cancellation import ExecutionContext
from .executor import execute
from .mcp.client import McpRuntime
from .schema import DELEGATE_SCHEMA, TOOL_SCHEMAS


class ToolRouter:
    def __init__(self, workspace, mcp: McpRuntime | None = None, delegate=None):
        self.workspace = workspace
        self.mcp = mcp
        self.delegate = delegate
        self.schemas = TOOL_SCHEMAS + (mcp.schemas if mcp else [])
        if delegate:
            self.schemas.append(DELEGATE_SCHEMA)

    @property
    def mcp_servers(self) -> dict[str, str]:
        return self.mcp.servers if self.mcp else {}

    def call(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ExecutionContext | None = None,
    ) -> str:
        if name == "delegate":
            if not self.delegate:
                raise ValueError("delegate is unavailable")
            return self.delegate(arguments["agent"], arguments["task"], context)
        if self.mcp and name in self.mcp.tools:
            return self.mcp.call(name, arguments, context)
        return execute(self.workspace, name, arguments, context)
