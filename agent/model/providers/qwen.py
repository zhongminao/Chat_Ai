from dataclasses import dataclass
from typing import Any

from ..openai_compatible import OpenAICompatibleAdapter


@dataclass(frozen=True)
class QwenChatTemplateAdapter(OpenAICompatibleAdapter):
    thinking: str = "disabled"

    def request_options(self) -> dict[str, Any]:
        return {"extra_body": {"chat_template_kwargs": {"enable_thinking": self.thinking == "enabled"}}}
