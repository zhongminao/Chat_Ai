from dataclasses import dataclass
from typing import Any

from ..openai_compatible import parse_chunk
from ..protocol import ModelChunk


@dataclass(frozen=True)
class DeepSeekProvider:
    thinking: str = "disabled"

    def request_options(self) -> dict[str, Any]:
        return {"extra_body": {"thinking": {"type": self.thinking}}}

    def parse_chunk(self, raw: Any) -> ModelChunk:
        return parse_chunk(raw, reasoning_field="reasoning_content")
