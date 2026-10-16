"""Terminal presentation of shared tool resources."""
from ..tools.result import ToolResult


def render_context_event(event: dict) -> None:
    labels = {
        "context.compaction.started": "正在自动压缩上下文…",
        "context.compacted": "上下文已自动压缩",
        "context.compaction.cancelled": "上下文自动压缩已取消",
        "context.compaction.failed": "上下文自动压缩失败",
    }
    if label := labels.get(event["type"]):
        detail = f"：{event['reason']}" if event.get("reason") else ""
        print(f"\n[{label}{detail}]", flush=True)


def render_tool_result(result: ToolResult) -> None:
    if result.images:
        print(f"\n{result.text}", flush=True)
