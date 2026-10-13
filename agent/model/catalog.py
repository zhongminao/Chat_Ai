import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .providers import create as create_provider


@dataclass(frozen=True)
class ModelTarget:
    provider: str
    name: str
    thinking: str

    def as_dict(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "name": self.name,
            "thinking": self.thinking,
        }


class ModelCatalog:
    def __init__(self, path: Path):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        self.providers: dict[str, dict[str, Any]] = data.get("providers", {})
        self.default_provider = data.get("default_provider", "deepseek")

    def resolve(self, provider_name: str, model_name: str | None = None) -> ModelTarget:
        provider = self.providers.get(provider_name)
        if provider is None:
            raise ValueError(f"unknown provider: {provider_name}")
        model_name = model_name or provider.get("default_model")
        entries = provider.get("models", [])
        models = {item["id"] for item in entries}
        if not model_name or (models and model_name not in models):
            raise ValueError(f"unknown model: {provider_name}/{model_name}")
        entry = next((item for item in entries if item["id"] == model_name), None)
        if entry and entry.get("enabled", True) is False:
            raise ValueError(f"model disabled: {provider_name}/{model_name}")
        return ModelTarget(
            provider=provider_name,
            name=model_name,
            thinking=provider.get("thinking", "disabled"),
        )

    def default(self) -> ModelTarget:
        return self.resolve(self.default_provider)

    def runtime(self, target: ModelTarget):
        provider = self.providers[target.provider]
        env_name = provider.get("api_key_env")
        api_key = os.getenv(env_name) if env_name else None
        api_key = api_key or provider.get("api_key_default")
        if not api_key:
            raise RuntimeError(f"missing environment variable: {env_name}")
        from openai import OpenAI
        return (
            OpenAI(api_key=api_key, base_url=provider["base_url"]),
            create_provider(target.provider, target.thinking),
        )
