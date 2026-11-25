from dataclasses import dataclass
from typing import Any

from ..openai_compatible import OpenAICompatibleAdapter


@dataclass(frozen=True)
class DeepSeekProvider(OpenAICompatibleAdapter):
    thinking: str = "disabled"
    reasoning_effort: str = ""

    def request_options(self) -> dict[str, Any]:
        options: dict[str, Any] = {"extra_body": {"thinking": {"type": self.thinking}}}
        if self.thinking == "enabled" and self.reasoning_effort not in {"", "none"}:
            options["reasoning_effort"] = self.reasoning_effort
        return options

    def reasoning_for_request(self, message: dict) -> dict:
        # The gateway requires this key on tool calls in thinking mode, including
        # history produced before thinking was enabled or by a different model.
        if self.thinking == "enabled" and message.get("tool_calls"):
            return {"reasoning_content": message.get("reasoning_content", "")}
        return {}


def normalize_model(raw: dict[str, Any]) -> dict[str, Any]:
    identifier = raw.get("id")
    return {"id": identifier, "name": raw.get("name", identifier),
            "context_window": raw.get("context_window")}
