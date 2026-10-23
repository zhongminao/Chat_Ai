"""Exercise cancellation against a local HTTP endpoint, without a model service."""
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from openai import InternalServerError

from agent.core.cancellation import CancellationToken, ExecutionContext, RunCancelled
from agent.core.session_registry import SessionRegistry
from agent.model.openai_compatible import stream
from agent.model.openai_compatible import OpenAICompatibleAdapter
from agent.model.http_client import ModelHttpClient
from agent.model.providers import create as create_provider
from agent.workflow.config import load


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        mode, release, ready = self.server.mode, self.server.release, self.server.ready
        self.server.entered.set()
        if mode == 'headers':
            release.wait(5)
        try:
            if mode == 'error':
                self.send_response(500)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            if mode == 'gpt_tools' and body.get('reasoning_effort') != self.server.efforts.get(body['model']):
                self.send_response(400)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            if mode == 'json':
                payload = json.dumps({'path': self.path, 'body': body}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Connection', 'close')
            self.end_headers()
            if mode == 'partial':
                chunk = {'id': 'test', 'object': 'chat.completion.chunk', 'created': 0, 'model': 'test',
                         'choices': [{'index': 0, 'delta': {'content': 'partial'}, 'finish_reason': None}]}
                self.wfile.write(('data: ' + json.dumps(chunk) + '\n\n').encode())
                self.wfile.flush()
            if mode == 'gpt_tools':
                chunk = {'id': 'test', 'object': 'chat.completion.chunk', 'created': 0, 'model': body['model'],
                         'choices': [{'index': 0, 'delta': {'tool_calls': [{'index': 0, 'id': 'call', 'type': 'function',
                             'function': {'name': 'report_status', 'arguments': '{"text":"OK"}'}}]}, 'finish_reason': 'tool_calls'}]}
                self.wfile.write(('data: ' + json.dumps(chunk) + '\n\n').encode())
                self.wfile.flush()
            ready.set()
            release.wait(5)
            self.wfile.write(b'data: [DONE]\n\n')
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


class ModelHttpClientTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.server.mode = 'headers'
        self.server.efforts = {}
        self.server.entered = threading.Event()
        self.server.ready = threading.Event()
        self.server.release = threading.Event()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/v1'

    def tearDown(self):
        self.server.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def test_gpt_chat_adapter_can_stream_function_calls_with_required_reasoning_mode(self):
        self.server.mode = 'gpt_tools'
        self.server.release.set()
        self.server.efforts = {'gpt-6.1-sol': 'high', 'gpt-5.6-sol': 'medium', 'gpt-6-astra': 'medium'}
        request = ModelHttpClient(api_key='test', base_url=self.url, max_retries=0)
        tools = [{'type': 'function', 'function': {'name': 'report_status', 'parameters': {'type': 'object'}}}]
        try:
            for name in ['gpt-6.1-sol', 'gpt-5.6-sol', 'gpt-6-astra']:
                with self.subTest(model=name):
                    chunks = list(stream(request, name, [{'role': 'user', 'content': 'report OK'}], tools,
                                         create_provider('gpt', model=name,
                                                         reasoning_effort=self.server.efforts[name])))
                    self.assertEqual(chunks[0].finish_reason, 'tool_calls')
                    self.assertEqual(chunks[0].tool_deltas[0].name, 'report_status')
                    self.assertEqual(json.loads(chunks[0].tool_deltas[0].arguments), {'text': 'OK'})
        finally:
            request.close()

    def test_cancel_waiting_for_headers_and_stream_data(self):
        for mode in ['headers', 'body', 'partial']:
            with self.subTest(mode=mode):
                self.server.mode = mode
                self.server.entered = threading.Event()
                self.server.ready = threading.Event()
                self.server.release = threading.Event()
                token = CancellationToken()
                partial = threading.Event()
                closed = threading.Event()
                request = ModelHttpClient(api_key='test', base_url=self.url, max_retries=0, timeout=5)

                def run():
                    try:
                        for chunk in stream(request, 'test', [{'role': 'user', 'content': 'hello'}], [],
                                            OpenAICompatibleAdapter(), ExecutionContext(token)):
                            if chunk.content:
                                partial.set()
                    finally:
                        request.close()
                        closed.set()

                with ThreadPoolExecutor(1) as pool:
                    task = pool.submit(run)
                    entered = self.server.entered.wait(10)
                    if not entered and task.done():
                        task.result()  # Surface request setup failures instead of hiding them as readiness timeouts.
                    self.assertTrue(entered)
                    if mode != 'headers':
                        self.assertTrue(self.server.ready.wait(3))
                    if mode == 'partial':
                        self.assertTrue(partial.wait(3))
                    token.cancel()
                    with self.assertRaises(RunCancelled):
                        task.result(2)
                    self.assertTrue(closed.is_set())
                    self.server.release.set()

    def test_network_error_without_stop_remains_failure(self):
        self.server.mode = 'error'
        request = ModelHttpClient(api_key='test', base_url=self.url, max_retries=0)
        try:
            with self.assertRaises(InternalServerError):
                list(stream(request, 'test', [], [], OpenAICompatibleAdapter(), ExecutionContext(CancellationToken())))
        finally:
            request.close()

    def test_auxiliary_json_request_uses_provider_root_and_is_cancellable(self):
        self.server.mode = 'json'
        request = ModelHttpClient(api_key='test', base_url=self.url, max_retries=0)
        try:
            result = request.post_json('/tokenize', {'content': 'hello'})
            self.assertEqual(result, {'path': '/tokenize', 'body': {'content': 'hello'}})
        finally:
            request.close()
        self.server.entered.clear()
        self.server.mode = 'headers'
        token = CancellationToken()
        def run():
            request = ModelHttpClient(api_key='test', base_url=self.url, max_retries=0)
            try:
                request.post_json('/tokenize', {}, ExecutionContext(token))
            finally:
                request.close()
        with ThreadPoolExecutor(1) as pool:
            task = pool.submit(run)
            self.assertTrue(self.server.entered.wait(3))
            token.cancel()
            with self.assertRaises(RunCancelled):
                task.result(2)

    def test_session_stop_publishes_cancelled_and_allows_next_turn(self):
        # A delayed HTTP response must not prevent local cancellation or notify Web as a failure.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            providers = root / 'providers.yaml'
            providers.write_text(f"""default_provider: qwen
providers:
  qwen:
    base_url: {self.url}
    api_key_default: test
    default_model: test
    models: {{test: {{}}}}
""")
            config = replace(load(), approval_mode="full_access", providers_file=providers, workspace=root,
                             storage_dir=root, mcp={})
            registry = SessionRegistry(config)
            runtime = registry.create()
            events = runtime.bus.subscribe()
            try:
                runtime.enqueue('first')
                self.assertTrue(self.server.entered.wait(3))
                self.assertTrue(runtime.stop())
                runtime.queue.join()
                records = runtime.session.events.read()
                self.assertEqual(runtime.state['execution']['status'], 'cancelled')
                self.assertFalse(runtime.busy)
                self.assertEqual(sum(e['type'] == 'turn.cancelled' for e in records), 1)
                self.assertFalse(any(e['type'] == 'turn.failed' for e in records))
                delivered = []
                while not events.empty():
                    delivered.append(events.get_nowait()['type'])
                self.assertIn('turn.cancelled', delivered)
                self.server.mode = 'body'
                self.server.release.set()
                runtime.enqueue('next')
                runtime.queue.join()
                self.assertEqual(runtime.state['execution']['status'], 'completed')
            finally:
                runtime.stop()
                self.server.release.set()
                runtime.queue.put(None)
                runtime.worker.join(5)
                self.assertFalse(runtime.worker.is_alive())


if __name__ == '__main__':
    unittest.main()
