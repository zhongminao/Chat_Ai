"""Refresh the model directory from provider /models endpoints."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from typing import Any
from urllib.request import Request, urlopen
from .catalog_file import write_models

from .providers import deepseek, gpt


def get_json(url: str, api_key: str, timeout: float = 8) -> dict[str, Any]:
    request = Request(url, headers={"Authorization": f"Bearer {api_key}"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def _normalize(provider: str, raw: dict[str, Any]) -> dict[str, Any]:
    if provider == "gpt":
        return gpt.normalize_model(raw)
    if provider == "deepseek":
        return deepseek.normalize_model(raw)
    identifier = raw.get("id") or raw.get("model") or raw.get("name")
    return {"id": identifier, "name": raw.get("name", identifier)}


def refresh_catalog(catalog, timeout: float = 8) -> dict[str, str]:
    overrides = catalog.overrides.get("providers", {})
    def refresh(name: str, config: dict[str, Any]):
        key_name = config.get("api_key_env")
        key = (os.getenv(key_name) if key_name else None) or config.get("api_key_default", "")
        base = os.getenv(config.get("base_url_env", "")) or config["base_url"]
        payload = get_json(base.rstrip("/") + "/models", key, timeout)
        configured = {item["id"]: item for item in catalog.models_for(name)}
        model_overrides = (overrides.get(name) or {}).get("models", {})
        models = []
        for raw in payload.get("data", []):
            identifier = raw.get("id") or raw.get("model") or raw.get("name")
            normalized = _normalize(name, raw)
            if normalized.get("chat_completions") is False:
                continue
            item = dict(configured.get(identifier, {}))
            item.update(normalized)
            models.append(item)
        updated = dict(config)
        if "models" in config:
            updated["models"] = [
                {**item, **model_overrides.get(item["id"], {})} for item in models
            ]
            return updated, models
        expected = config.get("default_model")
        if not expected or not any(item["id"] == expected for item in models):
            raise ValueError(f"configured model {expected!r} was not returned")
        return updated, None

    results: dict[str, str] = {}
    successful = {}
    with ThreadPoolExecutor(max_workers=max(1, len(catalog.providers))) as pool:
        futures = {pool.submit(refresh, name, config): name
                   for name, config in catalog.providers.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                successful[name] = future.result()
                results[name] = "ok"
            except Exception as exc:
                results[name] = f"error: {exc}"

    if successful:
        write_models(catalog.path, {name: models for name, (_, models) in successful.items()
                                    if models is not None})
        for name, (updated, _) in successful.items():
            catalog.replace_provider(name, updated)
    return results
