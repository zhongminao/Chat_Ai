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
    def __init__(self, path: Path):
        self.path = path
        self._state = self.read_config()
        self._lock = threading.RLock()
        self._bound_target = None
        self._binding: tuple[Any, Any] | None = None

    def read_config(self) -> dict:
        data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        return {"providers": data.get("providers", {}), "discovered": {},
                "default_provider": os.getenv("CHAT_AI_DEFAULT_PROVIDER") or data.get("default_provider", "deepseek")}

    @property
    def providers(self) -> dict[str, dict[str, Any]]:
        return self._state["providers"]

    @property
    def default_provider(self) -> str:
        return self._state["default_provider"]

    def fork(self):
        child = object.__new__(ModelCatalog)
        child.path = self.path
        child._state = self._state
        child._lock = self._lock
        child._bound_target = None
        child._binding = None
        return child

    def model_options(self, provider_name: str, model_name: str) -> dict[str, Any]:
        provider = self.providers.get(provider_name, {})
        discovered = next((item for item in self._state["discovered"].get(provider_name, [])
                           if item["id"] == model_name), {})
        return {"id": model_name, "name": model_name, **discovered,
                **provider.get("defaults", {}),
                **(provider.get("models", {}).get(model_name) or {})}

    def models_for(self, provider_name: str) -> list[dict[str, Any]]:
        # Only API discoveries are selectable; manual overrides never imply availability.
        return [options for item in self._state["discovered"].get(provider_name, [])
                if (options := self.model_options(provider_name, item["id"])).get("enabled", True)]

    def resolve(self, provider_name: str, model_name: str | None = None) -> ModelTarget:
        provider = self.providers.get(provider_name)
        if provider is None:
            raise ValueError(f"unknown provider: {provider_name}")
        model_name = model_name or provider.get("default_model")
        if not model_name:
            raise ValueError(f"unknown model: {provider_name}/{model_name}")
        # Keep historical/default identities resolvable even while a service is offline.
        entry = self.model_options(provider_name, model_name)
        if entry.get("enabled", True) is False:
            raise ValueError(f"model disabled: {provider_name}/{model_name}")
        return ModelTarget(
            provider=provider_name, name=model_name,
            thinking=entry.get("thinking", "disabled"),
            reasoning_effort=entry.get("default_reasoning_effort",
                                      entry.get("api_default_reasoning_effort", "")),
        )

    def default(self) -> ModelTarget:
        return self.resolve(self.default_provider)

    def supports_vision(self, model: dict[str, str]) -> bool:
        entry = self.model_options(model["provider"], model["name"])
        return entry.get("vision", "image" in entry.get("input_modalities", [])) is True

    def get_binding(self, target: ModelTarget) -> tuple[Any, Any]:
        provider = self.providers[target.provider]
        env_name = provider.get("api_key_env")
        api_key = os.getenv(env_name) if env_name else None
        api_key = api_key or provider.get("api_key_default")
        if not api_key and target.provider.startswith("local-"):
            api_key = "local"
        if not api_key:
            raise RuntimeError(f"missing environment variable: {env_name}")
        base_url = os.getenv(provider.get("base_url_env", "")) or provider["base_url"]
        binding_key = (target, base_url, api_key)
        if binding_key == self._bound_target and self._binding is not None:
            return self._binding
        adapter = create_provider(target.provider, target.thinking, model=target.name,
                                  reasoning_effort=target.reasoning_effort)
        binding = (ModelHttpClient(api_key=api_key, base_url=base_url), adapter)
        previous = self._binding
        self._binding, self._bound_target = binding, binding_key
        if previous:
            previous[0].close()
        return binding

    def token_counter(self, model: dict[str, str]) -> str:
        provider = self.providers[model["provider"]]
        entry = self.model_options(model["provider"], model["name"])
        return entry.get("token_counter", provider.get("token_counter", "estimate"))

    def close(self) -> None:
        if self._binding:
            self._binding[0].close()
            self._binding = None
            self._bound_target = None
