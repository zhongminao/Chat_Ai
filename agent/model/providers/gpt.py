"""Chat Completions reasoning settings for the GPT models."""
from dataclasses import dataclass

from ..openai_compatible import OpenAICompatibleAdapter


@dataclass(frozen=True)
class GPTChatAdapter(OpenAICompatibleAdapter):
    model: str = ""
    reasoning_effort: str = ""

    def request_options(self) -> dict:
        return {"reasoning_effort": self.reasoning_effort} if self.reasoning_effort else {}
