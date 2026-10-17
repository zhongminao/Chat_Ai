"""Chat Completions reasoning settings supported by the configured GPT models."""
from dataclasses import dataclass

from ..openai_compatible import OpenAICompatibleAdapter


@dataclass(frozen=True)
class GPTChatAdapter(OpenAICompatibleAdapter):
    model: str = ""

    def request_options(self) -> dict:
        return {"reasoning_effort": "low" if self.model == "gpt-6-astra" else "none"}
