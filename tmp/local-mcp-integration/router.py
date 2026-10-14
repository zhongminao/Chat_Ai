from typing import Any

from ..core.cancellation import ExecutionContext, RunCancelled
from ..storage.images import ImageStore
from .executor import execute
from .images import read_image, show_image
from .result import ToolResult
from .mcp.client import McpRuntime
from .mcp.results import convert_result
from .schema import DELEGATE_SCHEMA, TOOL_SCHEMAS


class ToolRouter:
    def __init__(self, workspace, mcp: McpRuntime | None = None, delegate=None, images: ImageStore | None = None):
        self.workspace = workspace
        self.mcp = mcp
        self.delegate = delegate
        self.images = images
        self.vision = False
        self.image_limit: int | None = None
        self.model_images: set[str] = set()
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
    ) -> str | ToolResult:
        if name in {"show_image", "read_image"}:
            try:
                if self.images is None:
                    raise ValueError("session image store is unavailable")
                if name == "read_image":
                    if not self.vision:
                        raise ValueError("当前模型未声明支持视觉，请切换到支持视觉的模型")
                    return read_image(self.workspace, self.images, context=context,
                                      known_images=self.model_images, max_images=self.image_limit, **arguments)
                return show_image(self.workspace, self.images, context=context, **arguments)
            except RunCancelled:
                raise
            except Exception as exc:
                return f"[tool error] {type(exc).__name__}: {exc}"
        if name == "delegate":
            if not self.delegate:
                raise ValueError("delegate is unavailable")
            return self.delegate(arguments["agent"], arguments["task"], context)
        if self.mcp and name in self.mcp.tools:
            try:
                result = self.mcp.call(name, arguments, context)
                return convert_result(result, self.images, vision=self.vision,
                                      known_images=self.model_images, max_images=self.image_limit)
            except RunCancelled:
                raise
            except Exception as exc:
                return f"[mcp error] {type(exc).__name__}: {exc}"
        return execute(self.workspace, name, arguments, context)
