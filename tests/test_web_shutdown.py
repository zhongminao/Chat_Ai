"""Real uvicorn shutdown: keep the SSE socket open while sending a signal."""
import http.client
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'posix', 'POSIX process signals required')
class WebShutdownTests(unittest.TestCase):
    def run_server(self, *, sse, signum):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # All writable paths are temporary; no real storage or API calls.
            (root / 'prompt.md').write_text('Test prompt', encoding='utf-8')
            config = {
                'workspace': str(root), 'storage_dir': str(root / 'storage'),
                'providers_file': str(ROOT / 'agent/model/providers/providers.yaml'),
                'system_prompt_file': 'prompt.md', 'child_system_prompt_file': 'prompt.md',
                'spill': {'enabled': False}, 'mcp': {},
            }
            (root / 'config.yaml').write_text(yaml.safe_dump(config), encoding='utf-8')
            # Reserve a random port and pass the socket, avoiding a free-port race.
            with socket.socket() as listener, (root / 'server.log').open('w+') as log:
                listener.bind(('127.0.0.1', 0))
                port = listener.getsockname()[1]
                env = dict(os.environ, CHAT_AI_CONFIG=str(root / 'config.yaml'))
                process = subprocess.Popen(
                    [sys.executable, '-m', 'uvicorn', 'agent.web.app:app',
                     '--fd', str(listener.fileno()), '--no-access-log'],
                    cwd=ROOT, env=env, pass_fds=(listener.fileno(),),
                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                )
                connection = None
                try:
                    deadline = time.monotonic() + 15
                    while True:
                        try:
                            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=1)
                            connection.request('GET', '/api/sessions')
                            response = connection.getresponse()
                            response.read()
                            self.assertEqual(response.status, 200)
                            break
                        except (OSError, http.client.HTTPException):
                            if connection:
                                connection.close()
                            if process.poll() is not None or time.monotonic() >= deadline:
                                self.fail('uvicorn did not start')
                            time.sleep(.05)
                    if sse:
                        connection.request('POST', '/api/sessions')
                        response = connection.getresponse()
                        self.assertEqual(response.status, 200)
                        session_id = json.loads(response.read())['id']
                        connection.request('GET', f'/api/sessions/{session_id}/events')
                        response = connection.getresponse()
                        self.assertEqual(response.status, 200)
                        # Read through ready: the live SSE remains connected.
                        while b'session.ready' not in response.readline():
                            pass
                    started = time.monotonic()
                    process.send_signal(signum)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.fail('uvicorn did not exit within 5s with SSE socket still open')
                    self.assertLess(time.monotonic() - started, 5)
                    # New uvicorn versions replay the signal after graceful shutdown.
                    self.assertIn(process.returncode, (0, -signum, 128 + signum))
                    log.flush()
                    log.seek(0)
                    output = log.read()
                    self.assertIn('Application shutdown complete.', output)
                    self.assertNotIn('Traceback', output)
                    if sse:
                        self.assertEqual(response.read(), b'\n')
                finally:
                    if connection:
                        connection.close()
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
                    log.flush()
                    log.seek(0)
                    if sys.exc_info()[0] is not None:
                        print(log.read(), file=sys.stderr)

    def test_sigint_without_sse(self):
        self.run_server(sse=False, signum=signal.SIGINT)

    def test_sigint_with_open_sse(self):
        self.run_server(sse=True, signum=signal.SIGINT)

    def test_sigterm_with_open_sse(self):
        self.run_server(sse=True, signum=signal.SIGTERM)


class ShutdownSignalTests(unittest.TestCase):
    def test_chains_server_handlers_and_restores_them(self):
        import threading
        from unittest.mock import Mock, patch
        from agent.web.shutdown import shutdown_signals

        stopping = threading.Event()
        original = {signal.SIGINT: Mock(), signal.SIGTERM: Mock()}
        current = dict(original)
        def install(sig, handler):
            previous = current[sig]
            current[sig] = handler
            return previous
        with patch('signal.getsignal', side_effect=current.__getitem__), \
                patch('signal.signal', side_effect=install):
            with shutdown_signals(stopping):
                current[signal.SIGINT](signal.SIGINT, None)
                self.assertTrue(stopping.is_set())
                original[signal.SIGINT].assert_called_once_with(signal.SIGINT, None)
                current[signal.SIGTERM](signal.SIGTERM, None)
                original[signal.SIGTERM].assert_called_once_with(signal.SIGTERM, None)
            self.assertEqual(current, original)
