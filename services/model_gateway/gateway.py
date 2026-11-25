"""Optional loopback gateway for cloud model APIs."""
import argparse
import json
import logging
import os
from pathlib import Path

import anyio
import httpx
import uvicorn
import yaml


HOP_HEADERS = {b"connection", b"keep-alive", b"proxy-authenticate",
               b"proxy-authorization", b"te", b"trailer", b"transfer-encoding", b"upgrade"}
ENDPOINTS = {("POST", "chat/completions"), ("GET", "models")}
MAX_BODY_BYTES = 64 * 1024 * 1024
MAX_CONNECTIONS = 10
KEEPALIVE_EXPIRY = 24 * 60 * 60
REPRESENTATION_HEADERS = {b"content-length", b"content-encoding", b"content-md5",
                          b"content-digest", b"repr-digest", b"digest", b"etag"}
REASONING_FIELDS = ("reasoning_efforts", "default_reasoning_effort")


def reasoning_levels(value):
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(level.strip() for level in value if isinstance(level, str) and level.strip()))


def reasoning_metadata(name, provider, model):
    levels = reasoning_levels(model.get("reasoning_efforts"))
    default = model.get("default_reasoning_effort")
    if not levels and name == "deepseek" and isinstance(effort := model.get("effort"), dict):
        levels = reasoning_levels(effort.get("supported_levels"))
        if levels:
            # Preserve the chat_ai default: explicitly disable DeepSeek thinking.
            if "none" not in levels:
                levels.insert(0, "none")
            default = "none"
    if not levels and name == "gpt":
        fallback = provider.get("reasoning_fallback", {}).get(model["id"], {})
        levels = reasoning_levels(fallback.get("reasoning_efforts"))
        default = fallback.get("default_reasoning_effort")
    metadata = {"reasoning_efforts": levels} if levels else {}
    if isinstance(default, str) and default in levels:
        metadata["default_reasoning_effort"] = default
    return metadata


def enrich_models(body, name, provider):
    try:
        document = json.loads(body)
    except (ValueError, RecursionError):
        return body
    if not isinstance(document, dict) or not isinstance(document.get("data"), list):
        return body
    changed = False
    for model in document["data"]:
        if not isinstance(model, dict) or not isinstance(model.get("id"), str) or not model["id"]:
            continue
        current = {key: model[key] for key in REASONING_FIELDS if key in model}
        metadata = reasoning_metadata(name, provider, model)
        if current != metadata:
            changed = True
            for key in current:
                del model[key]
            model.update(metadata)
    return json.dumps(document, separators=(",", ":")).encode() if changed else body


async def send_json(send, status, message):
    body = json.dumps(message, ensure_ascii=False).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json; charset=utf-8")]})
    await send({"type": "http.response.body", "body": body})


class Gateway:
    def __init__(self, providers, client=None):
        self.providers = providers
        for provider in providers.values():
            url = httpx.URL(provider["base_url"])
            if (url.scheme not in {"http", "https"} or not url.host
                    or url.userinfo or url.query or url.fragment):
                raise ValueError("provider base_url must be a fixed HTTP(S) URL without credentials/query/fragment")
        self.client = client or httpx.AsyncClient(
            trust_env=False, follow_redirects=False,
            limits=httpx.Limits(max_connections=MAX_CONNECTIONS,
                                max_keepalive_connections=MAX_CONNECTIONS,
                                keepalive_expiry=KEEPALIVE_EXPIRY),
            timeout=httpx.Timeout(600, connect=5, write=60, pool=5),
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                event = await receive()
                if event["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif event["type"] == "lifespan.shutdown":
                    await self.client.aclose()
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope["type"] != "http":
            return

        async def error(status, message):
            await send_json(send, status, {"error": {"message": message, "type": "gateway_error"}})

        if scope["path"] == "/health" and scope["method"] == "GET":
            await send_json(send, 200, {"status": "ok"})
            return
        parts = scope["path"].strip("/").split("/", 2)
        if len(parts) != 3 or parts[1] != "v1" or parts[0] not in self.providers:
            await error(404, "Unknown model gateway route")
            return
        name, _, endpoint = parts
        if (scope["method"], endpoint) not in ENDPOINTS:
            await error(404, "Only chat/completions and models are available")
            return
        provider = self.providers[name]
        key_env = provider.get("api_key_env")
        key = os.environ.get(key_env, "") if key_env else ""
        if not provider.get("enabled", True) or not key:
            await error(503, f"Model provider {name} is unavailable")
            return

        body = bytearray()
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            body.extend(event.get("body", b""))
            if len(body) > MAX_BODY_BYTES:
                await error(413, "Model request exceeds 64 MiB")
                return
            if not event.get("more_body", False):
                break

        # Watch disconnects even while the upstream has not returned headers yet.
        async def disconnected():
            while (await receive())["type"] != "http.disconnect":
                pass

        async def forward():
            url = httpx.URL(provider["base_url"].rstrip("/") + "/" + endpoint)
            url = url.copy_with(query=scope.get("query_string") or None)
            headers = {"Accept-Encoding": "identity", "Authorization": f"Bearer {key}"}
            for header, value in scope.get("headers", []):
                if header.lower() in {b"content-type", b"accept"}:
                    headers[header.decode("ascii")] = value.decode("latin-1")
            started = False
            try:
                async with self.client.stream(scope["method"], url, headers=headers, content=bytes(body)) as response:
                    excluded = HOP_HEADERS | {
                        item.strip().lower()
                        for key, value in response.headers.raw if key.lower() == b"connection"
                        for item in value.split(b",") if item.strip()
                    }
                    if endpoint == "models" and response.status_code == 200:
                        # Buffer only the list response; chat streams straight through.
                        raw = await response.aread()
                        enriched = enrich_models(raw, name, provider)
                        extra_headers = []
                        if enriched is not raw or response.headers.get("content-encoding"):
                            excluded |= REPRESENTATION_HEADERS
                            extra_headers.append((b"content-length", str(len(enriched)).encode()))
                        response_headers = [(k, v) for k, v in response.headers.raw if k.lower() not in excluded]
                        await send({"type": "http.response.start", "status": response.status_code,
                                    "headers": response_headers + extra_headers})
                        started = True
                        await send({"type": "http.response.body", "body": enriched})
                        return
                    response_headers = [(k, v) for k, v in response.headers.raw if k.lower() not in excluded]
                    await send({"type": "http.response.start", "status": response.status_code,
                                "headers": response_headers})
                    started = True
                    async for chunk in response.aiter_raw():
                        await send({"type": "http.response.body", "body": chunk, "more_body": True})
                    await send({"type": "http.response.body", "body": b""})
            except httpx.PoolTimeout:
                logging.getLogger("gateway").warning("%s upstream PoolTimeout", name)
                if started:
                    raise
                await error(503, f"Model provider {name} is busy; try again later")
            except httpx.HTTPError as exc:
                # Never log prompts, response bodies, Authorization or exception details.
                logging.getLogger("gateway").warning("%s upstream %s", name, type(exc).__name__)
                if started:
                    raise
                await error(504 if isinstance(exc, httpx.TimeoutException) else 502,
                            f"Model provider {name} connection failed")

        # HTTPcore shields connection cleanup with AnyIO cancellation scopes.
        # Task.cancel() bypasses those shields and can strand an ACTIVE pool slot
        # when a downstream disconnect races with response.aclose().
        failure = None

        async def run_until_finished(operation):
            nonlocal failure
            try:
                await operation()
            except Exception as exc:
                failure = exc
            finally:
                group.cancel_scope.cancel()

        async with anyio.create_task_group() as group:
            group.start_soon(run_until_finished, forward)
            group.start_soon(run_until_finished, disconnected)
        if failure is not None:
            raise failure


def main():
    parser = argparse.ArgumentParser(description="Loopback-only, fixed-upstream cloud model gateway")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.yaml"))
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if config.get("local") or "listeners" in config:
        raise ValueError("the cloud gateway has no local model proxy")
    host = config.get("host", "127.0.0.1")
    if host != "127.0.0.1":
        raise ValueError("cloud gateway must remain loopback-only")
    uvicorn.run(Gateway(config["providers"]), host=host, port=int(config.get("port", 18101)),
                proxy_headers=False, log_level="info")


if __name__ == "__main__":
    main()
