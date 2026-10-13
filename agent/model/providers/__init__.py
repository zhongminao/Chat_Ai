from typing import Any

from .deepseek import DeepSeekProvider
from .qwen import QwenProvider


def create(name: str, thinking: str = "disabled") -> Any:
    if name == "deepseek":
        return DeepSeekProvider(thinking=thinking)
    if name in {"qwen", "gpt", "local-qwen3p5-9b"}:
        return QwenProvider()
    raise ValueError(f"unknown provider: {name}")
