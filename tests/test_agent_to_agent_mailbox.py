"""Mailbox authorization, durability, and monitor isolation."""
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from agent.core.session_registry import SessionRegistry
from agent.core.session_runtime import SessionBusy
from agent.tools.mailbox import send
from agent.workflow.config import load


class MailboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.registry = SessionRegistry(replace(load(), storage_dir=Path(self.temp.name),
                                                workspace=Path(self.temp.name), mcp={}))
        self.root = self.registry.create()
        self.a = self.registry.create(parent_session_id=self.root.session.id)
        self.b = self.registry.create(parent_session_id=self.root.session.id)
        self.other = self.registry.create()

    def tearDown(self):
        for runtime in self.registry.items.values():
            runtime.queue.put(None)
            runtime.worker.join(5)
        self.registry.store.database.close()
        self.temp.cleanup()

    def test_delivery_reads_monitor_and_reopen(self):
        root, a, b = (item.session.id for item in (self.root, self.a, self.b))
        before = [item.session.events.read() for item in (self.root, self.a, self.b)]
        self.b.busy = True
        self.b.steering.begin()
        result = self.registry.notify_agent(a, root, 'secret', cc=[b], kind='feedback')
        self.assertEqual(result['recipients'], [{'session_id': root, 'role': 'to'},
                                                {'session_id': b, 'role': 'cc'}])
        self.assertEqual(self.registry.mailbox_unread_count(root), 1)
        self.assertEqual(self.registry.mailbox_list(b, True)[0]['role'], 'cc')
        self.assertEqual([item.session.events.read() for item in (self.root, self.a, self.b)], before)
        resource = self.registry.monitor(root).watch()['changes']
        mailbox = next(item for item in resource if item['id'] == f'mailbox:{root}')
        self.assertEqual((mailbox['unread_count'], mailbox['latest_id']), (1, result['id']))
        self.assertNotIn('secret', str(resource))
        with self.assertRaises(FileNotFoundError):
            self.registry.mailbox_read(a, result['id'])
        self.assertIsNotNone(self.registry.mailbox_read(root, result['id'])['read_at'])
        self.assertEqual(self.registry.mailbox_unread_count(root), 0)
        self.assertEqual(self.registry.mailbox_unread_count(b), 1)
        self.assertEqual(self.registry.mailbox_list(root, True), [])
        reopened = SessionRegistry(self.registry.config)
        try:
            self.assertEqual(reopened.mailbox_list(b)[0]['content'], 'secret')
            self.assertEqual(reopened.mailbox_unread_count(root), 0)
        finally:
            reopened.store.database.close()

    def test_authorization_and_atomicity(self):
        root, a, b, other = (item.session.id for item in (self.root, self.a, self.b, self.other))
        for args in [(root, a, 'text', [other]), (a, b, 'text', []),
                     (root, root, 'text', []), (a, root, 'text', [root])]:
            with self.assertRaises((PermissionError, ValueError)):
                self.registry.notify_agent(args[0], args[1], args[2], cc=args[3])
        self.assertEqual(self.registry.mailbox_list(a), [])
        self.assertEqual(self.registry.mailbox_list(root), [])
        self.a.busy = self.b.busy = True
        self.a.steering.begin()
        self.b.steering.begin()
        self.registry.notify_agent(root, a, 'first', cc=[b])
        self.assertEqual(self.registry.mailbox_list(a)[0]['role'], 'to')
        self.assertEqual(self.registry.mailbox_list(b)[0]['role'], 'cc')
        with self.assertRaises(FileNotFoundError):
            self.registry.mailbox_read(other, self.registry.mailbox_list(a)[0]['id'])
        self.assertEqual(self.registry.mailbox_unread_count(other), 0)

    def test_child_parent_alias_and_bad_recipients(self):
        root, a = self.root.session.id, self.a.session.id
        result = send(self.registry, a, to='parent', content='feedback')
        self.assertEqual(result['recipients'][0]['session_id'], root)
        with self.assertRaises(ValueError):
            send(self.registry, root, to='parent', content='invalid')
        for cc in ('string', [{'unhashable': True}], 1):
            with self.assertRaises(ValueError):
                self.registry.notify_agent(a, root, 'invalid', cc=cc, kind='feedback')

    def test_submit_and_stop_boundary(self):
        root, a = self.root.session.id, self.a.session.id
        self.a.submitting = True
        with self.assertRaises(SessionBusy):
            self.registry.notify_agent(root, a, 'too late')
        self.a.submitting = False
        self.a.busy = True
        self.a.control.request_stop()
        with self.assertRaises(SessionBusy):
            self.registry.notify_agent(root, a, 'stopping')
        self.a.busy = False
        self.registry.notify_agent(self.a.session.id, root, 'parent can receive while idle', kind='feedback')
