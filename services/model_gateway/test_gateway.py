import asyncio
import gzip
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx
import yaml

from gateway import Gateway, main


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk

    async def aclose(self):
        self.closed = True


class GatewayTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.environment = patch.dict(os.environ, {"GPT_API_KEY": "test-gpt", "DEEPSEEK_API_KEY": "test-deepseek"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.requests = []
        self.response = httpx.Response(200, stream=Chunks([b"data: one\n\n", b"data: [DONE]\n\n"]),
                                       headers={"content-type": "text/event-stream"})

        async def handler(request):
            self.requests.append(request)
            return self.response

        self.handler = handler
        self.clients = []

    async def asyncTearDown(self):
        for client in self.clients:
            await client.aclose()

    def gateway(self, providers=None):
        client = httpx.AsyncClient(transport=httpx.MockTransport(self.handler), follow_redirects=False)
        self.clients.append(client)
        return Gateway(providers or {
            "gpt": {"base_url": "https://gpt.invalid/v1", "api_key_env": "GPT_API_KEY"},
            "deepseek": {"base_url": "https://deepseek.invalid/v1", "api_key_env": "DEEPSEEK_API_KEY"},
        }, client)

    def call(self, gateway=None, path="/gpt/v1/chat/completions", method="POST", body=b"{}", headers=None):
        receive = asyncio.Queue()
        receive.put_nowait({"type": "http.request", "body": body})
        sent = []

        async def send(message):
            sent.append(message)

        scope = {"type": "http", "method": method, "path": path, "query_string": b"",
                 "headers": headers or [(b"content-type", b"application/json")]}
        task = asyncio.create_task((gateway or self.gateway())(scope, receive.get, send))
        return task, receive, sent

    async def result(self, **kwargs):
        task, _, sent = self.call(**kwargs)
        await asyncio.wait_for(task, 1)
        return sent[0]["status"], b"".join(x.get("body", b"") for x in sent), sent


class GatewayTests(GatewayTestCase):
    async def test_routes_replace_authorization_and_preserve_complete_payload(self):
        body = json.dumps({"model": "test", "stream": True, "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}]}],
            "tools": [{"type": "function", "function": {"name": "test"}}]}).encode()
        for provider in ["gpt", "deepseek"]:
            self.response = httpx.Response(200, stream=Chunks([b"data: ok\n\n"]))
            status, output, _ = await self.result(path=f"/{provider}/v1/chat/completions", body=body,
                headers=[(b"authorization", b"Bearer vm-placeholder"), (b"host", b"attacker.invalid"),
                         (b"content-type", b"application/json"), (b"x-api-key", b"caller-secret")])
            request = self.requests[-1]
            self.assertEqual(str(request.url), f"https://{provider}.invalid/v1/chat/completions")
            self.assertEqual(request.headers["authorization"], f"Bearer test-{provider}")
            self.assertNotIn("x-api-key", request.headers)
            self.assertEqual(request.content, body)
            self.assertEqual((status, output), (200, b"data: ok\n\n"))

    async def test_stream_chunks_are_forwarded_before_completion_and_closed(self):
        first = asyncio.Event()
        release = asyncio.Event()

        class SlowStream(Chunks):
            async def __aiter__(self):
                yield b"data: first\n\n"
                first.set()
                await release.wait()
                yield b"data: last\n\n"

        stream = SlowStream([])
        self.response = httpx.Response(200, stream=stream, headers={"content-type": "text/event-stream"})
        task, _, sent = self.call()
        await asyncio.wait_for(first.wait(), 1)
        self.assertFalse(task.done())
        self.assertEqual(sent[1]["body"], b"data: first\n\n")
        release.set()
        await asyncio.wait_for(task, 1)
        self.assertTrue(stream.closed)
        self.assertEqual(sent[-1], {"type": "http.response.body", "body": b""})

    async def test_disconnect_cancels_waiting_for_upstream_headers(self):
        started, cancelled = asyncio.Event(), asyncio.Event()

        async def handler(request):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        self.handler = handler
        task, receive, sent = self.call()
        await asyncio.wait_for(started.wait(), 1)
        receive.put_nowait({"type": "http.disconnect"})
        await asyncio.wait_for(task, 1)
        self.assertTrue(cancelled.is_set())
        self.assertEqual(sent, [])

    async def test_disconnect_closes_open_stream_waiting_for_more_data(self):
        started = asyncio.Event()

        class WaitingStream(Chunks):
            async def __aiter__(self):
                yield b"data: first\n\n"
                started.set()
                await asyncio.Event().wait()

        stream = WaitingStream([])
        self.response = httpx.Response(200, stream=stream)
        task, receive, _ = self.call()
        await asyncio.wait_for(started.wait(), 1)
        receive.put_nowait({"type": "http.disconnect"})
        await asyncio.wait_for(task, 1)
        self.assertTrue(stream.closed)

    async def test_upstream_errors_and_redirects_keep_status_and_body(self):
        for status in [401, 429, 503, 307]:
            self.response = httpx.Response(status, stream=Chunks([b'{"error":"upstream"}']),
                headers={"location": "http://private.invalid", "connection": "keep-alive, x-hop",
                         "x-hop": "remove", "x-request-id": "keep"})
            actual, body, sent = await self.result()
            self.assertEqual((actual, body), (status, b'{"error":"upstream"}'))
            headers = dict(sent[0]["headers"])
            self.assertNotIn(b"connection", headers)
            self.assertNotIn(b"x-hop", headers)
            self.assertEqual(headers[b"x-request-id"], b"keep")
        self.assertEqual(len(self.requests), 4)

    async def test_connection_errors_are_sanitized(self):
        for exception, status in [(httpx.ConnectError("secret-detail"), 502),
                                  (httpx.ReadTimeout("secret-detail"), 504),
                                  (httpx.PoolTimeout("secret-detail"), 503)]:
            async def handler(request):
                raise exception
            self.handler = handler
            actual, body, _ = await self.result()
            self.assertEqual(actual, status)
            self.assertNotIn(b"secret-detail", body)

    async def test_unknown_paths_disabled_and_missing_keys_never_forward(self):
        for path in ["/unknown/v1/models", "/gpt/v1/http://private.invalid", "/gpt/v1/files",
                     "/v1/chat/completions", "/local/v1/chat/completions", "/apply-template", "/tokenize"]:
            status, _, _ = await self.result(path=path)
            self.assertEqual(status, 404)
        gateway = self.gateway()
        gateway.providers["gpt"]["enabled"] = False
        self.assertEqual((await self.result(gateway=gateway))[0], 503)
        del os.environ["DEEPSEEK_API_KEY"]
        self.assertEqual((await self.result(path="/deepseek/v1/models", method="GET"))[0], 503)
        self.assertEqual(self.requests, [])

    async def test_models_and_health(self):
        self.response = httpx.Response(200, stream=Chunks([b'{"data":[]}']))
        self.assertEqual((await self.result(path="/deepseek/v1/models", method="GET"))[:2],
                         (200, b'{"data":[]}'))
        self.assertEqual(str(self.requests[-1].url), "https://deepseek.invalid/v1/models")
        self.assertEqual((await self.result(path="/health", method="GET"))[0], 200)
        self.assertEqual(len(self.requests), 1)

    async def test_body_limit_and_disconnect_before_body_do_not_forward(self):
        with patch("gateway.MAX_BODY_BYTES", 1):
            self.assertEqual((await self.result(body=b"too large"))[0], 413)
        async def receive():
            return {"type": "http.disconnect"}
        async def send(message):
            self.fail("No response expected after disconnect")
        await self.gateway()({"type": "http", "path": "/gpt/v1/chat/completions", "method": "POST"}, receive, send)
        self.assertEqual(self.requests, [])

    async def test_midstream_failure_is_not_reported_as_successful_completion(self):
        class BrokenStream(Chunks):
            async def __aiter__(self):
                yield b"partial"
                raise httpx.ReadError("broken")
        stream = BrokenStream([])
        self.response = httpx.Response(200, stream=stream)
        task, _, sent = self.call()
        with self.assertRaises(httpx.ReadError):
            await task
        self.assertTrue(stream.closed)
        self.assertTrue(sent[-1]["more_body"])

    async def test_lifespan_closes_shared_client(self):
        gateway = self.gateway()
        messages = iter([{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}])
        sent = []
        async def receive():
            return next(messages)
        async def send(message):
            sent.append(message["type"])
        await gateway({"type": "lifespan"}, receive, send)
        self.assertTrue(gateway.client.is_closed)
        self.assertEqual(sent, ["lifespan.startup.complete", "lifespan.shutdown.complete"])


class ModelDiscoveryTests(GatewayTestCase):
    def configured_gateway(self):
        config = yaml.safe_load(Path(__file__).with_name("config.example.yaml").read_text(encoding="utf-8"))
        return self.gateway(config["providers"])

    async def discover(self, gateway, provider, payload, *, status=200, compressed=False):
        data = json.dumps(payload).encode()
        if compressed:
            data = gzip.compress(data)
        headers = {"content-type": "application/json", "content-length": str(len(data)), "etag": '"upstream"'}
        if compressed:
            headers["content-encoding"] = "gzip"
        stream = Chunks([data])
        self.response = httpx.Response(status, stream=stream, headers=headers)
        previous = len(self.requests)
        actual, body, sent = await self.result(gateway=gateway, path=f"/{provider}/v1/models", method="GET", body=b"")
        self.assertEqual(actual, status)
        self.assertEqual([(r.method, r.url.path) for r in self.requests[previous:]], [("GET", "/v1/models")])
        self.assertEqual(self.requests[-1].headers["authorization"], f"Bearer test-{provider}")
        self.assertTrue(stream.closed)
        self.assertEqual(int(dict(sent[0]["headers"])[b"content-length"]), len(body))
        return json.loads(body), dict(sent[0]["headers"])

    async def test_gpt_example_fallback_only_for_discovered_models(self):
        gateway = self.configured_gateway()
        expected = {
            "gpt-6.2-sol": "high", "gpt-6-sol": "high", "gpt-6.1-sol": "medium",
            "gpt-6-astra": "medium", "gpt-6.1-terra": "medium", "gpt-5.6-sol": "medium",
            "gpt-5.6-terra": "medium", "gpt-6.2-astra": "medium", "codex-auto-review": "medium",
        }
        self.assertEqual(set(gateway.providers["gpt"]["reasoning_fallback"]), set(expected))
        payload = {"object": "list", "data": [{"id": model, "owned_by": "upstream"} for model in expected]}
        actual, _ = await self.discover(gateway, "gpt", payload)
        self.assertEqual(actual, {"object": "list", "data": [
            {"id": model, "owned_by": "upstream", "reasoning_efforts": ["low", "medium", "high", "xhigh"],
             "default_reasoning_effort": default} for model, default in expected.items()
        ]})
        # A fresh call sees additions/removals and lets advertised metadata supersede local fallback.
        payload = {"data": [
            {"id": "new-model"},
            {"id": "gpt-6-sol", "reasoning_efforts": ["auto", "low", "", " ", "auto", None],
             "default_reasoning_effort": "auto"},
        ]}
        actual, headers = await self.discover(gateway, "gpt", payload, compressed=True)
        self.assertEqual(actual, {"data": [{"id": "new-model"}, {
            "id": "gpt-6-sol", "reasoning_efforts": ["auto", "low"], "default_reasoning_effort": "auto",
        }]})
        self.assertNotIn(b"content-encoding", headers)
        self.assertNotIn(b"etag", headers)

    async def test_deepseek_native_changes_and_standard_metadata_precedence(self):
        gateway = self.configured_gateway()
        gateway.providers["deepseek"]["reasoning_fallback"] = {
            "deepseek-unknown": {"reasoning_efforts": ["high"], "default_reasoning_effort": "high"},
        }
        native = {"id": "deepseek-native", "effort": {"supported_levels": ["medium", "high", "medium", 1]}}
        standard = {"id": "deepseek-standard", "reasoning_efforts": ["auto"], "default_reasoning_effort": "auto",
                    "effort": {"supported_levels": ["high"]}}
        unknown = {"id": "deepseek-unknown", "effort": {"supported_levels": ["", None]},
                   "reasoning_efforts": [], "default_reasoning_effort": "high"}
        actual, _ = await self.discover(gateway, "deepseek", {"data": [native, standard, unknown]})
        self.assertEqual(actual["data"], [
            {**native, "reasoning_efforts": ["none", "medium", "high"], "default_reasoning_effort": "none"},
            standard, {key: unknown[key] for key in ("id", "effort")},
        ])
        native["effort"]["supported_levels"] = ["max", "none", "max"]
        actual, _ = await self.discover(gateway, "deepseek", {"data": [native]})
        self.assertEqual(actual["data"], [
            {**native, "reasoning_efforts": ["max", "none"], "default_reasoning_effort": "none"},
        ])

    async def test_unknown_default_is_omitted_without_mixing_metadata_sources(self):
        gateway = self.configured_gateway()
        model = {"id": "gpt-6-sol", "reasoning_efforts": ["low", "high"], "default_reasoning_effort": "invalid"}
        actual, _ = await self.discover(gateway, "gpt", {"data": [model]})
        self.assertEqual(actual, {"data": [{"id": "gpt-6-sol", "reasoning_efforts": ["low", "high"]}]})

    async def test_non_success_list_is_forwarded_without_enrichment_or_retry(self):
        gateway = self.configured_gateway()
        payload = {"data": [{"id": "gpt-6-sol"}], "error": "throttled"}
        actual, headers = await self.discover(gateway, "gpt", payload, status=429)
        self.assertEqual(actual, payload)
        self.assertIn(b"etag", headers)

    async def test_disconnect_while_reading_models_closes_upstream_without_partial_catalog(self):
        first = asyncio.Event()

        class PartialList(Chunks):
            async def __aiter__(self):
                yield b'{"data":['
                first.set()
                await asyncio.Event().wait()

        stream = PartialList([])
        self.response = httpx.Response(200, stream=stream)
        task, receive, sent = self.call(path="/gpt/v1/models", method="GET", body=b"")
        await asyncio.wait_for(first.wait(), 1)
        receive.put_nowait({"type": "http.disconnect"})
        await asyncio.wait_for(task, 1)
        self.assertTrue(stream.closed)
        self.assertEqual(sent, [])
        self.assertEqual(len(self.requests), 1)


class CliTests(unittest.IsolatedAsyncioTestCase):
    async def test_example_uses_loopback_and_separate_port(self):
        config = Path(__file__).with_name("config.example.yaml")
        with patch("sys.argv", ["gateway.py", "--config", str(config)]), patch("gateway.uvicorn.run") as run:
            main()
        run.assert_called_once()
        app = run.call_args.args[0]
        try:
            self.assertEqual(run.call_args.kwargs["host"], "127.0.0.1")
            self.assertEqual(run.call_args.kwargs["port"], 18101)
            self.assertFalse(run.call_args.kwargs["proxy_headers"])
        finally:
            await app.client.aclose()

    async def test_cli_rejects_non_loopback_and_local_proxy_config(self):
        config = Path(__file__).with_name("config.example.yaml")
        for data in ({"host": "0.0.0.0"}, {"local": True}, {"listeners": []}):
            with self.subTest(data=data):
                with patch("sys.argv", ["gateway.py", "--config", str(config)]), \
                        patch("gateway.yaml.safe_load", return_value=data), patch("gateway.uvicorn.run") as run:
                    with self.assertRaises(ValueError):
                        main()
                    run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
