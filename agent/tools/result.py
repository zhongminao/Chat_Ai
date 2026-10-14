"""Tool output before it is separated into model text and display resources."""
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    text: str
    images: list[dict[str, Any]] = field(default_factory=list)
    model_images: list[dict[str, Any]] = field(default_factory=list)


def normalize_result(value: str | ToolResult) -> ToolResult:
    return value if isinstance(value, ToolResult) else ToolResult(value)
