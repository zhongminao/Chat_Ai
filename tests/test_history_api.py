"""Historical snapshot and backwards segment paging over JSONL."""
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from agent.core.session_registry import SessionRegistry
from agent.web import app as web
from agent.workflow.config import load


class HistoryAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.registry = SessionRegistry(replace(load(), storage_dir=Path(self.temp.name), mcp={}))
        self.rt = self.registry.create()
        self.log = self.rt.session.events
        self.store_patch = patch.object(web, 'session_store', self.registry.store)
        self.store_patch.start()
        self.addCleanup(self.store_patch.stop)
        self.client = TestClient(web.app)
        self.addCleanup(self.client.close)
        self.url = f'/api/sessions/{self.rt.session.id}/history'
        self.addCleanup(self.close)

    def close(self):
        self.rt.queue.put(None)
        self.rt.worker.join(3)
        self.registry.store.database.close()
        self.temp.cleanup()

    def page(self, **params):
        response = self.client.get(self.url, params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_empty_and_validation(self):
        self.assertEqual(self.page(), dict(events=[], snapshot_seq=0, min_seq=0, has_more=False))
        for params in ({'before': 1}, {'through': 1}, {'before': 3, 'through': 2},
                       {'before': 1, 'through': 10}):
            self.assertEqual(self.client.get(self.url, params=params).status_code, 400)
        self.assertEqual(self.client.get('/api/sessions/missing/history').status_code, 404)
        self.assertEqual(self.client.get(self.url, params={'before': -1, 'through': 2}).status_code, 422)

    def test_latest_aligns_to_started_and_frozen_older_page(self):
        for index in range(4):
            self.log.append('turn.started', prompt=str(index))
            for _ in range(105):
                self.log.append('message.delta', durable=False, text='x')
            self.log.append('turn.completed')
        recent = self.page()
        self.assertEqual(recent['events'][0]['type'], 'turn.started')
        self.assertEqual(recent['min_seq'], 215)
        self.assertEqual(recent['snapshot_seq'], 428)
        self.assertTrue(recent['has_more'])
        self.log.append('turn.started', prompt='new')
        older = self.page(before=recent['min_seq'], through=recent['snapshot_seq'])
        self.assertEqual(older['snapshot_seq'], 428)
        self.assertEqual(older['events'][0]['seq'], 1)
        self.assertEqual(older['events'][-1]['seq'], 214)
        self.assertFalse(older['has_more'])

    def test_compaction_stays_with_newer_segment_and_not_inside_turn(self):
        for prompt in ('old', 'second'):
            self.log.append('turn.started', prompt=prompt)
            self.log.append('turn.completed')
        self.log.append('turn.started', prompt='third')
        self.log.append('context.compacted', messages=[])
        self.log.append('turn.completed')
        self.log.append('turn.started', prompt='fourth')
        self.log.append('turn.completed')
        page = self.page(before=8, through=8)
        self.assertEqual([e['seq'] for e in page['events']], [5, 6, 7])
        self.assertEqual(page['min_seq'], 5)
        old = self.page(before=5, through=8)
        self.assertEqual([e['seq'] for e in old['events']], [1, 2, 3, 4])

    def test_boundary_before_turn_keeps_compaction_in_newer_page(self):
        self.log.append('turn.started', prompt='old')
        self.log.append('turn.completed')
        self.log.append('context.compacted', messages=[])
        self.log.append('turn.started', prompt='new')
        self.log.append('turn.completed')
        self.assertEqual([e['seq'] for e in self.page(before=4, through=5)['events']], [3])
        self.assertEqual([e['seq'] for e in self.page(before=3, through=5)['events']], [1, 2])

    def test_running_turn_in_latest_page(self):
        self.log.append('turn.started', prompt='running')
        self.log.append('message.delta', durable=False, text='partial')
        page = self.page()
        self.assertEqual([e['seq'] for e in page['events']], [1, 2])
        self.assertFalse(page['has_more'])
