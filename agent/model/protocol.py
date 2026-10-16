from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCallDelta:
    index: int = 0
    id: str = ""
    name: str = ""
    arguments: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "id": self.id,
            "function": {
                "name": self.name,
                "arguments": self.arguments,
            },
        }


@dataclass(frozen=True)
class ModelChunk:
    content: str = ""
    reasoning: str = ""
    tool_deltas: tuple[ToolCallDelta, ...] = ()
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None
