"""Refresh the model directory from provider /models endpoints."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from typing import Any
from urllib.request import Request, urlopen

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
    # Publish one complete snapshot; readers keep the previous list during refresh.
    with catalog._lock:
        snapshot = catalog.read_config()
        results = {}
        def refresh(config):
            key_name = config.get("api_key_env")
            key = (os.getenv(key_name) if key_name else None) or config.get("api_key_default", "")
            base = os.getenv(config.get("base_url_env", "")) or config["base_url"]
            return get_json(base.rstrip("/") + "/models", key, timeout)

        with ThreadPoolExecutor(max_workers=max(1, len(snapshot["providers"]))) as pool:
            futures = {pool.submit(refresh, config): name
                       for name, config in snapshot["providers"].items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    models = [_normalize(name, raw) for raw in future.result().get("data", [])]
                    snapshot["discovered"][name] = [item for item in models
                        if item.get("id") and item.get("chat_completions", True)]
                    results[name] = "ok"
                except Exception as exc:
                    results[name] = f"error: {exc}"
        catalog._state.update(snapshot)
        return results
