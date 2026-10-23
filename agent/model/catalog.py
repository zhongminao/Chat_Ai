import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .providers import create as create_provider
from .http_client import ModelHttpClient


@dataclass(frozen=True)
class ModelTarget:
    provider: str
    name: str
    thinking: str
    reasoning_effort: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "name": self.name,
            "thinking": self.thinking,
            **({"reasoning_effort": self.reasoning_effort} if self.reasoning_effort else {}),
        }


class ModelCatalog:
    def __init__(self, path: Path, overrides: dict | None = None):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        self.path = path
        self._state = {"providers": data.get("providers", {})}
        self.overrides = overrides or {}
        self._lock = threading.RLock()
        self._apply_overrides()
        self.default_provider = os.getenv("CHAT_AI_DEFAULT_PROVIDER") or data.get("default_provider", "deepseek")
        self._bound_target: ModelTarget | None = None
        self._binding: tuple[Any, Any] | None = None

    @property
    def providers(self) -> dict[str, dict[str, Any]]:
        return self._state["providers"]

    def fork(self):
        child = object.__new__(ModelCatalog)
        child.path = self.path
        child._state = self._state
        child.overrides = self.overrides
        child._lock = self._lock
        child.default_provider = self.default_provider
        child._bound_target = None
        child._binding = None
        return child

    def models_for(self, provider_name: str) -> list[dict[str, Any]]:
        provider = self.providers.get(provider_name, {})
        entries = provider.get("models")
        if entries is None and provider.get("default_model"):
            identifier = provider["default_model"]
            entries = [{"id": identifier, "name": identifier}]
        return entries or []

    def _apply_overrides(self) -> None:
        models = self.overrides.get("providers", {})
        for name, provider in self.providers.items():
            for item in self.models_for(name):
                item.update((models.get(name) or {}).get("models", {}).get(item["id"], {}))

    def replace_provider(self, name: str, provider: dict[str, Any]) -> None:
        with self._lock:
            providers = dict(self.providers)
            providers[name] = provider
            self._state["providers"] = providers

    def resolve(self, provider_name: str, model_name: str | None = None) -> ModelTarget:
        provider = self.providers.get(provider_name)
        if provider is None:
            raise ValueError(f"unknown provider: {provider_name}")
        model_name = model_name or provider.get("default_model")
        entries = self.models_for(provider_name)
        models = {item["id"] for item in entries}
        if not model_name or (models and model_name not in models):
            raise ValueError(f"unknown model: {provider_name}/{model_name}")
        entry = next((item for item in entries if item["id"] == model_name), None)
        if entry and entry.get("enabled", True) is False:
            raise ValueError(f"model disabled: {provider_name}/{model_name}")
        if provider_name == "gpt":
            policy = self.overrides.get("providers", {}).get("gpt", {}).get("models", {}).get(model_name, {})
            effort = policy.get("default_reasoning_effort", "medium")
        else:
            effort = (entry or {}).get("default_reasoning_effort", (entry or {}).get("reasoning_effort", ""))
        return ModelTarget(
            provider=provider_name,
            name=model_name,
            thinking=provider.get("thinking", "disabled"),
            reasoning_effort=effort,
        )

    def default(self) -> ModelTarget:
        return self.resolve(self.default_provider)

    def supports_vision(self, model: dict[str, str]) -> bool:
        provider = self.providers.get(model["provider"], {})
        entry = next((item for item in self.models_for(model["provider"]) if item["id"] == model["name"]), {})
        return entry.get("vision", provider.get("vision", False)) is True

    def get_binding(self, target: ModelTarget) -> tuple[Any, Any]:
        if target == self._bound_target and self._binding is not None:
            return self._binding
        provider = self.providers[target.provider]
        env_name = provider.get("api_key_env")
        api_key = os.getenv(env_name) if env_name else None
        api_key = api_key or provider.get("api_key_default")
        if not api_key and target.provider.startswith("local-"):
            api_key = "local"
        if not api_key:
            raise RuntimeError(f"missing environment variable: {env_name}")
        adapter = create_provider(target.provider, target.thinking, model=target.name,
                                  reasoning_effort=target.reasoning_effort)
        base_url = os.getenv(provider.get("base_url_env", "")) or provider["base_url"]
        binding = (ModelHttpClient(api_key=api_key, base_url=base_url), adapter)
        previous = self._binding
        self._binding, self._bound_target = binding, target
        if previous:
            previous[0].close()
        return binding

    def token_counter(self, model: dict[str, str]) -> str:
        provider = self.providers[model["provider"]]
        entry = next((item for item in self.models_for(model["provider"]) if item["id"] == model["name"]), {})
        return entry.get("token_counter", provider.get("token_counter", "estimate"))

    def close(self) -> None:
        if self._binding:
            self._binding[0].close()
            self._binding = None
            self._bound_target = None
