"""SSE handshake, replay/live boundary, reconnection and sequence recovery."""
import asyncio
import json
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.requests import Request as HttpRequest

from agent.core.session_registry import SessionRegistry
from agent.web import app as web
from agent.web.events import session_events
from agent.workflow.config import load


class Request:
    async def is_disconnected(self):
        return False


def decode(frame):
    return json.loads(next(line[6:] for line in frame.splitlines() if line.startswith('data: ')))


class SessionEventsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = replace(load(), storage_dir=Path(self.temp.name), mcp={})
        self.registry = SessionRegistry(self.config)
        self.runtime = self.registry.create()
        self.addCleanup(self.close)

    def close(self):
        for runtime in self.registry.items.values():
            runtime.busy = False
            runtime.queue.put(None)
            runtime.worker.join(3)
        self.registry.store.database.close()
        self.temp.cleanup()

    async def close_stream(self, stream):
        await stream.aclose()

    async def frame(self, stream):
        return await asyncio.wait_for(anext(stream), 3)

    async def replay(self, after=0, runtime=None):
        stream = session_events(runtime or self.runtime, Request(), after)
        self.addAsyncCleanup(self.close_stream, stream)
        frames = []
        while True:
            frame = await self.frame(stream)
            frames.append(frame)
            if decode(frame)['type'] == 'session.ready':
                return stream, frames

    async def test_empty_session_initializes_without_constructing_agent_or_persisting_control_frames(self):
        _, frames = await self.replay()
        initial, ready = map(decode, frames)
        self.assertEqual(initial['id'], self.runtime.session.id)
        self.assertEqual((initial['seq'], initial['after'], initial['busy'], initial['reset']), (0, 0, False, False))
        self.assertTrue(frames[0].startswith('id: 0\n'))
        self.assertFalse(frames[1].startswith('id:'))
        self.assertEqual(ready, {'type': 'session.ready', 'seq': 0})
        self.assertIsNone(self.runtime._agent)
        self.assertIsNone(self.runtime._state)
        self.assertEqual(self.runtime.session.events.read(), [])

    async def test_initial_state_restores_model_and_child_read_only_metadata(self):
        child = self.registry.create(parent_session_id=self.runtime.session.id)
        selected = {'provider': 'test', 'name': 'changed', 'thinking': 'disabled'}
        child.session.events.append('model.changed', new=selected)
        _, frames = await self.replay(runtime=child)
        state = decode(frames[0])
        self.assertEqual(state['model'], selected)
        self.assertEqual(state['parent_session_id'], self.runtime.session.id)
        self.assertEqual([decode(frame)['type'] for frame in frames],
                         ['session.init', 'model.changed', 'session.ready'])

    async def test_writes_during_initial_read_are_delivered_after_replay_without_duplicates(self):
        log = self.runtime.session.events
        log.append('turn.started', prompt='hello')
        original = log.read
        def during_read(*args):
            records = original(*args)
            log.append('message.delta', durable=False, text='new')
            return records
        with patch.object(log, 'read', side_effect=during_read):
            stream, frames = await self.replay()
        self.assertEqual([decode(frame)['type'] for frame in frames],
                         ['session.init', 'turn.started', 'session.ready'])
        self.assertEqual(decode(frames[0])['seq'], 1)
        self.assertEqual(decode(await self.frame(stream))['seq'], 2)

    async def test_reconnect_sends_only_missing_events_and_refreshes_runtime_state_after_restart(self):
        log = self.runtime.session.events
        log.append('turn.started', prompt='hello')
        log.append('message.delta', durable=False, text='partial')
        restarted = SessionRegistry(self.config)
        runtime = restarted.get(self.runtime.session.id)
        try:
            stream, frames = await self.replay(after=1, runtime=runtime)
            initial = decode(frames[0])
            self.assertFalse(initial['busy'])
            self.assertEqual((initial['after'], initial['seq']), (1, 2))
            self.assertTrue(frames[0].startswith('id: 1\n'))
            self.assertEqual([decode(frame)['seq'] for frame in frames[1:-1]], [2])
            await stream.aclose()
        finally:
            runtime.queue.put(None)
            runtime.worker.join(3)
            restarted.store.database.close()

    async def test_cursor_ahead_of_database_resets_to_full_replay(self):
        self.runtime.session.events.append('turn.started', prompt='restored backup')
        _, frames = await self.replay(after=99)
        initial = decode(frames[0])
        self.assertTrue(initial['reset'])
        self.assertEqual(initial['after'], 0)
        self.assertTrue(frames[0].startswith('id: 0\n'))
        self.assertEqual(decode(frames[1])['seq'], 1)

    async def test_live_gap_is_recovered_from_sqlite_before_advancing_cursor(self):
        log = self.runtime.session.events
        log.append('turn.started', prompt='hello')
        stream, _ = await self.replay()
        with patch.object(log, 'on_append', None):
            second = log.append('message.delta', durable=False, text='second')
            third = log.append('message.delta', durable=False, text='third')
        self.runtime.bus.publish(third)
        self.runtime.bus.publish(second)
        self.assertEqual(decode(await self.frame(stream))['seq'], 2)
        self.assertEqual(decode(await self.frame(stream))['seq'], 3)
        fourth = log.append('turn.completed', answer='secondthird')
        self.assertEqual(decode(await self.frame(stream)), fourth)

    async def test_terminal_event_does_not_reinitialize_as_running_before_worker_finalization(self):
        self.runtime.session.events.append('turn.started', prompt='done')
        self.runtime.session.events.append('turn.completed', answer='done')
        self.runtime.busy = True
        _, frames = await self.replay()
        self.assertFalse(decode(frames[0])['busy'])

    async def test_disconnect_releases_subscription(self):
        stream, _ = await self.replay()
        self.assertEqual(len(self.runtime.bus.subscribers), 1)
        await stream.aclose()
        self.assertEqual(self.runtime.bus.subscribers, [])

    async def test_shutdown_token_closes_live_stream_and_releases_subscription(self):
        stopping = threading.Event()
        stream = session_events(self.runtime, Request(), 0, stopping=stopping)
        self.addAsyncCleanup(self.close_stream, stream)
        self.assertEqual(decode(await self.frame(stream))['type'], 'session.init')
        self.assertEqual(decode(await self.frame(stream))['type'], 'session.ready')
        self.assertEqual(len(self.runtime.bus.subscribers), 1)
        waiting = asyncio.create_task(anext(stream))
        await asyncio.sleep(.02)
        stopping.set()
        with self.assertRaises(StopAsyncIteration):
            await asyncio.wait_for(waiting, 1)
        self.assertEqual(self.runtime.bus.subscribers, [])

    async def test_last_event_id_header_resumes_without_skipping_unreceived_history(self):
        self.runtime.session.events.append('turn.started', prompt='hello')
        self.runtime.session.events.append('message.delta', durable=False, text='partial')
        request = HttpRequest({'type': 'http', 'headers': [(b'last-event-id', b'1')]})
        with patch.object(web, 'registry', self.registry):
            response = await web.events(self.runtime.session.id, request, after=0)
            stream = response.body_iterator
            try:
                initial = await self.frame(stream)
                self.assertTrue(initial.startswith('id: 1\n'))
                self.assertEqual(decode(initial)['after'], 1)
                self.assertEqual(decode(await self.frame(stream))['seq'], 2)
                self.assertEqual(decode(await self.frame(stream))['type'], 'session.ready')
            finally:
                await stream.aclose()

    def test_snapshot_route_removed_and_invalid_cursors_rejected(self):
        with patch.object(web, 'registry', self.registry), patch.object(web, 'session_store', self.registry.store), TestClient(web.app) as client:
            path = f'/api/sessions/{self.runtime.session.id}'
            self.assertEqual(client.get(path + '/conversation').status_code, 404)
            self.assertEqual(client.get(path + '/events?after=-1').status_code, 422)
            for value in ['invalid', '-1']:
                self.assertEqual(client.get(path + '/events', headers={'Last-Event-ID': value}).status_code, 400)
            self.assertEqual(client.get('/api/sessions/missing/events').status_code, 404)
