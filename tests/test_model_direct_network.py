"""Real HTTP requests must bypass an inherited proxy, including an empty NO_PROXY."""
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from agent.model.discovery import get_json
from agent.model.http_client import ModelHttpClient


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.respond()

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.respond()

    def respond(self):
        self.server.requests.append(self.path)
        if self.server.is_proxy:
            status, body = 502, b"unexpected proxy request"
        elif self.path.endswith("/chat/completions"):
            chunk = {"id": "test", "object": "chat.completion.chunk", "created": 0,
                     "model": "test", "choices": [{"index": 0, "delta": {"content": "OK"},
                                                     "finish_reason": "stop"}]}
            status, body = 200, ("data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n").encode()
        else:
            status, body = 200, json.dumps({"path": self.path}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/event-stream" if "completions" in self.path
                         else "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ModelDirectNetworkTests(unittest.TestCase):
    def setUp(self):
        self.origin = self.start_server(False)
        self.proxy = self.start_server(True)
        proxy_url = f"http://127.0.0.1:{self.proxy.server_port}"
        self.environment = {name: proxy_url for name in
                            ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                             "http_proxy", "https_proxy", "all_proxy")}
        self.environment.update(NO_PROXY="", no_proxy="")
        self.base_url = f"http://127.0.0.1:{self.origin.server_port}/v1"

    def start_server(self, is_proxy):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.is_proxy = is_proxy
        server.requests = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def close():
            server.shutdown()
            server.server_close()
            thread.join(5)
        self.addCleanup(close)
        return server

    def test_discovery_bypasses_proxy_with_no_bypass_list(self):
        with patch.dict(os.environ, self.environment):
            self.assertEqual(get_json(self.base_url + "/models", "test"),
                             {"path": "/v1/models"})
        self.assertEqual(self.origin.requests, ["/v1/models"])
        self.assertEqual(self.proxy.requests, [])

    def test_chat_and_auxiliary_requests_bypass_proxy_and_close(self):
        with patch.dict(os.environ, self.environment):
            client = ModelHttpClient(api_key="test", base_url=self.base_url, max_retries=0)
            try:
                chunks = list(client.stream({"model": "test", "messages": [], "stream": True}))
                self.assertEqual(chunks[0].choices[0].delta.content, "OK")
                self.assertEqual(client.post_json("/tokenize", {"content": "hello"}),
                                 {"path": "/tokenize"})
                self.assertEqual(client.post_json("/apply-template", {"messages": []}),
                                 {"path": "/apply-template"})
            finally:
                client.close()
            self.assertTrue(client.client.is_closed())
            self.assertTrue(client.loop.is_closed())
        self.assertEqual(self.origin.requests,
                         ["/v1/chat/completions", "/tokenize", "/apply-template"])
        self.assertEqual(self.proxy.requests, [])
