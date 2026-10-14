"""Terminal presentation of shared tool resources."""
from ..tools.result import ToolResult


def render_tool_result(result: ToolResult) -> None:
    if result.images:
        print(f"\n{result.text}", flush=True)
