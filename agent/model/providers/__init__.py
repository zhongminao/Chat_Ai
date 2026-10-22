from typing import Any

from .deepseek import DeepSeekProvider
from .gpt import GPTChatAdapter
from ..openai_compatible import OpenAICompatibleAdapter
from .qwen import QwenChatTemplateAdapter


def create(name: str, thinking: str = "disabled", *, model: str = "", reasoning_effort: str = "") -> Any:
    if name == "deepseek":
        return DeepSeekProvider(thinking=thinking)
    if name in {"local-qwen3p5-9b", "local-qwen3p6-35b"}:
        return QwenChatTemplateAdapter(thinking=thinking)
    if name == "gpt":
        return GPTChatAdapter(model, reasoning_effort)
    if name in {"qwen", "local-qwen3-coder-30b"}:
        return OpenAICompatibleAdapter()
    raise ValueError(f"unknown provider: {name}")
