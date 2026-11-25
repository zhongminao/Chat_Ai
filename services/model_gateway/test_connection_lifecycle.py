"""Exercise real TCP connections, including disconnects during pool cleanup."""
import asyncio
import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import httpx
from httpcore._async.http11 import HTTP11ConnectionByteStream

from gateway import Gateway


class ConnectionLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.writers = set()
        self.handlers = set()
        self.accepted = 0
        self.started = asyncio.Queue()
        self.server = await asyncio.start_server(self.upstream, '127.0.0.1', 0)
        port = self.server.sockets[0].getsockname()[1]
        self.enterContext(patch.dict(os.environ, {'GATEWAY_TEST_KEY': 'fake-key'}))
        self.gateway = Gateway({'gpt': {'base_url': f'http://127.0.0.1:{port}/v1',
                                        'api_key_env': 'GATEWAY_TEST_KEY'}})
        self.client = self.gateway.client
        self.calls = []

    async def asyncTearDown(self):
        for task, queue in self.calls:
            if not task.done():
                queue.put_nowait({'type': 'http.disconnect'})
        await asyncio.gather(*(task for task, _ in self.calls), return_exceptions=True)
        await self.client.aclose()
        self.server.close()
        await self.server.wait_closed()
        for writer in list(self.writers):
            writer.close()
        await asyncio.gather(*list(self.handlers), return_exceptions=True)

    async def upstream(self, reader, writer):
        self.accepted += 1
        self.writers.add(writer)
        task = asyncio.current_task()
        self.handlers.add(task)
        try:
            while True:
                headers = await reader.readuntil(b'\r\n\r\n')
                target = headers.split(b' ', 2)[1].decode()
                mode = parse_qs(urlsplit(target).query).get('mode', ['normal'])[0]
                await self.started.put(mode)
                if mode == 'headers':
                    await reader.read(1)
                    return
                if mode in {'stream', 'stall'}:
                    writer.write(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n'
                                 b'Content-Type: text/event-stream\r\n\r\n')
                    if mode == 'stream':
                        data = b'data: first\n\n'
                        writer.write(f'{len(data):x}\r\n'.encode() + data + b'\r\n')
                    await writer.drain()
                    await reader.read(1)
                    return
                if mode == 'broken':
                    writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\nshort')
                    await writer.drain()
                    return
                writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 11\r\n'
                             b'Content-Type: application/json\r\n\r\n{"data":[]}')
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass
            self.writers.discard(writer)
            self.handlers.discard(task)

    def start_call(self, mode='normal', fail_send=False):
        queue = asyncio.Queue()
        queue.put_nowait({'type': 'http.request', 'body': b''})
        messages = []
        first_body = asyncio.Event()

        async def send(message):
            messages.append(message)
            if message.get('body'):
                first_body.set()
                if fail_send:
                    raise RuntimeError('downstream write failed')

        task = asyncio.create_task(self.gateway(
            {'type': 'http', 'method': 'POST', 'path': '/gpt/v1/chat/completions', 'headers': [],
             'query_string': ('mode=' + mode).encode()}, queue.get, send))
        self.calls.append((task, queue))
        return task, queue, messages, first_body

    def assert_released(self):
        pool = self.client._transport._pool
        self.assertEqual(len(pool._requests), 0)
        self.assertTrue(all(connection.is_idle() for connection in pool.connections))

    async def assert_normal_request(self):
        task, _, sent, _ = self.start_call()
        await asyncio.wait_for(task, 2)
        self.assertEqual(sent[0]['status'], 200)
        self.assertEqual(b''.join(m.get('body', b'') for m in sent), b'{"data":[]}')
        self.assert_released()

    async def test_normal_requests_reuse_one_connection(self):
        self.assertEqual(self.client.timeout.pool, 5)
        self.assertEqual(self.client.timeout.read, 600)
        for _ in range(110):
            await self.assert_normal_request()
        self.assertEqual(self.accepted, 1)

    async def test_disconnect_during_cleanup_releases_pool_slot(self):
        # Slow a real HTTPcore close so disconnect occurs inside its cancellation
        # shield. Raw asyncio Task.cancel() stranded an ACTIVE connection here.
        original = HTTP11ConnectionByteStream.aclose
        for _ in range(110):
            closing, release = asyncio.Event(), asyncio.Event()

            async def slow_close(stream):
                closing.set()
                await release.wait()
                await original(stream)

            with patch.object(HTTP11ConnectionByteStream, 'aclose', slow_close):
                task, queue, _, _ = self.start_call()
                try:
                    await asyncio.wait_for(closing.wait(), 2)
                    queue.put_nowait({'type': 'http.disconnect'})
                    for _ in range(10):
                        await asyncio.sleep(0)
                finally:
                    release.set()
                await asyncio.wait_for(task, 2)
            self.assert_released()
        await self.assert_normal_request()
        self.assertEqual(self.accepted, 1)

    async def test_disconnect_before_headers_and_during_stream(self):
        for mode in ['headers', 'stream']:
            for _ in range(110):
                task, queue, _, first = self.start_call(mode)
                # Ignore prior normal requests recorded by the server.
                while await asyncio.wait_for(self.started.get(), 2) != mode:
                    pass
                if mode == 'stream':
                    await asyncio.wait_for(first.wait(), 2)
                queue.put_nowait({'type': 'http.disconnect'})
                await asyncio.wait_for(task, 2)
                self.assert_released()
            await self.assert_normal_request()

    async def test_ten_busy_connections_reject_extra_then_recover(self):
        held = []
        for _ in range(10):
            call = self.start_call('stream')
            held.append(call)
            await asyncio.wait_for(call[3].wait(), 2)
        self.assertEqual(self.accepted, 10)
        task, _, sent, _ = self.start_call()
        await asyncio.wait_for(task, 7)
        self.assertEqual(sent[0]['status'], 503)
        self.assertIn(b'busy', sent[-1]['body'])
        self.assertEqual(self.accepted, 10)
        for task, queue, _, _ in held:
            queue.put_nowait({'type': 'http.disconnect'})
        await asyncio.wait_for(asyncio.gather(*(call[0] for call in held)), 2)
        self.assert_released()
        await self.assert_normal_request()

    async def test_read_timeout_before_and_after_headers_releases_connection(self):
        self.client.timeout = httpx.Timeout(1, read=.05)
        for mode in ['headers', 'stall']:
            task, _, sent, _ = self.start_call(mode)
            if mode == 'headers':
                await asyncio.wait_for(task, 2)
                self.assertEqual(sent[0]['status'], 504)
            else:
                with self.assertRaises(httpx.ReadTimeout):
                    await asyncio.wait_for(task, 2)
                self.assertEqual(sent[0]['status'], 200)
                self.assertFalse(any(m['type'] == 'http.response.body' and not m.get('more_body', False)
                                     for m in sent))
            self.assert_released()
            await self.assert_normal_request()

    async def test_broken_upstream_and_downstream_write_failure_release_connection(self):
        for mode, fail_send, exception in [('broken', False, httpx.RemoteProtocolError),
                                           ('stream', True, RuntimeError)]:
            task, _, _, _ = self.start_call(mode, fail_send)
            with self.assertRaises(exception):
                await asyncio.wait_for(task, 2)
            self.assert_released()
            await self.assert_normal_request()

    async def test_external_request_cancellation_releases_connection(self):
        task, _, _, first = self.start_call('stream')
        await asyncio.wait_for(first.wait(), 2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assert_released()
        await self.assert_normal_request()

    async def test_idle_connection_expires_after_one_day(self):
        await self.assert_normal_request()
        # Move the connection's expiry clock forward rather than sleeping a day.
        with patch('httpcore._async.http11.time') as clock:
            clock.monotonic.return_value = 10**15
            await self.assert_normal_request()
        self.assertEqual(self.accepted, 2)
        self.assertEqual(self.client._transport._pool._keepalive_expiry, 86400)


if __name__ == '__main__':
    unittest.main()
