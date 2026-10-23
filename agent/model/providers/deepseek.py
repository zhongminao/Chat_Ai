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


def normalize_model(raw: dict[str, Any]) -> dict[str, Any]:
    effort = raw.get("effort") or {}
    return {"id": raw["id"], "name": raw.get("name", raw["id"]),
            "reasoning_efforts": effort.get("supported_levels", []),
            "api_default_reasoning_effort": effort.get("default_level", ""),
            "context_window": raw.get("context_window"),
            "input_modalities": raw.get("input_modalities", ["text"])}
