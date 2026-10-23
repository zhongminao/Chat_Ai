"""Chat Completions reasoning settings for the GPT models."""
from dataclasses import dataclass
from typing import Any

from ..openai_compatible import OpenAICompatibleAdapter


@dataclass(frozen=True)
class GPTChatAdapter(OpenAICompatibleAdapter):
    model: str = ""
    reasoning_effort: str = ""

    def request_options(self) -> dict:
        return {"reasoning_effort": self.reasoning_effort} if self.reasoning_effort else {}


def normalize_model(raw: dict[str, Any]) -> dict[str, Any]:
    endpoints = raw.get("supported_endpoint_types", [])
    return {"id": raw["id"], "name": raw.get("name", raw["id"]),
            "chat_completions": "openai" in endpoints and "image-generation" not in endpoints}
