from typing import Any

from .deepseek import DeepSeekProvider
from ..openai_compatible import OpenAICompatibleAdapter
from .qwen import QwenChatTemplateAdapter


def create(name: str, thinking: str = "disabled") -> Any:
    if name == "deepseek":
        return DeepSeekProvider(thinking=thinking)
    if name == "local-qwen3p5-9b":
        return QwenChatTemplateAdapter(thinking=thinking)
    if name in {"qwen", "gpt", "local-qwen3-coder-30b"}:
        return OpenAICompatibleAdapter()
    raise ValueError(f"unknown provider: {name}")
