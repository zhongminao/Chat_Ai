from dataclasses import dataclass
from typing import Any

from ..openai_compatible import parse_chunk
from ..protocol import ModelChunk


@dataclass(frozen=True)
class QwenProvider:
    def request_options(self) -> dict[str, Any]:
        return {}

    def parse_chunk(self, raw: Any) -> ModelChunk:
        return parse_chunk(raw, reasoning_field="reasoning_content")


@dataclass(frozen=True)
class LocalQwenProvider(QwenProvider):
    thinking: str = "disabled"

    def request_options(self) -> dict[str, Any]:
        return {"extra_body": {"chat_template_kwargs": {"enable_thinking": self.thinking == "enabled"}}}
