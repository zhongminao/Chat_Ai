"""Live, sender-scoped read receipts without mailbox or watch replay."""
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from agent.core.cancellation import CancellationToken, ExecutionContext, RunCancelled
from agent.core.monitor import Monitor
from agent.storage.agent_to_agent_mailbox import AgentToAgentMailbox
from agent.storage.session import SessionStore


class WatchReadReceiptTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(directory)
        self.store = self.open_store()
        self.mailbox = AgentToAgentMailbox(self.store.database)
        self.sender = self.store.create().id
        self.reader = self.store.create(parent_session_id=self.sender).id
        self.cc = self.store.create(parent_session_id=self.sender).id
        self.monitor = Monitor(self.store, self.sender)

    def open_store(self):
        store = SessionStore(self.path)
        self.addCleanup(store.database.close)
        return store

    def start_watch(self, pool, monitor, detail_level, *, cursor=0, wake_if=None, context=None):
        ready = threading.Event()

        def check():
            ready.set()
            return wake_if and wake_if()

        future = pool.submit(monitor.watch, cursor, 5, context, wake_if=check, detail_level=detail_level)
        self.assertTrue(ready.wait(2), "watch never reached its wait loop")
        return future

    def read_and_publish(self, recipient, message_id, monitors):
        # Mirror the registry integration without needing to start an agent runtime.
        result, newly_read = self.mailbox.read_with_ack(recipient, message_id)
        if newly_read:
            monitors[result['sender_id']].record_read_receipt(result['id'], recipient)
        return result

    def test_receipt_notifies_only_detailed_watches_of_the_sender(self):
        other = Monitor(self.store, self.cc)
        monitors = {self.sender: self.monitor, self.cc: other}
        outbound = self.mailbox.send(self.sender, self.reader, 'private')['id']
        unrelated = self.mailbox.send(self.cc, self.sender, 'separate', kind='feedback')['id']
        with ThreadPoolExecutor(4) as pool:
            default = self.start_watch(pool, self.monitor, 'default')
            detailed = [self.start_watch(pool, self.monitor, 'detailed') for _ in range(2)]
            unrelated_watch = self.start_watch(pool, other, 'detailed')
            with patch.object(self.monitor.condition, 'notify_all', wraps=self.monitor.condition.notify_all) as wake:
                self.read_and_publish(self.reader, outbound, monitors)
                wake.assert_not_called()
            self.assertFalse(default.done(), 'default watch returned for a receipt')
            self.assertFalse(unrelated_watch.done(), 'another sender saw a private receipt')
            expected = {'cursor': 0, 'changes': [], 'read_receipts': [
                {'message_id': outbound, 'recipient_id': self.reader},
            ]}
            for future in detailed:
                self.assertEqual(future.result(2), expected)

            # Neither another sender's receipt nor a repeat read may wake this sender.
            quiet = self.start_watch(pool, self.monitor, 'detailed')
            with patch.object(self.monitor._detailed_condition, 'notify_all',
                              wraps=self.monitor._detailed_condition.notify_all) as wake:
                self.read_and_publish(self.reader, outbound, monitors)
                self.read_and_publish(self.sender, unrelated, monitors)
                wake.assert_not_called()
            self.assertEqual(unrelated_watch.result(2)['read_receipts'], [
                {'message_id': unrelated, 'recipient_id': self.sender},
            ])
            self.monitor.update('agent:child', kind='agent', status='completed')
            expected = {'cursor': 1, 'changes': [
                {'id': 'agent:child', 'kind': 'agent', 'status': 'completed', 'version': 1},
            ]}
            self.assertEqual(default.result(2), expected)
            self.assertEqual(quiet.result(2), expected)

    def test_receipts_never_replay_even_with_stale_cursor_or_other_active_watch(self):
        message_id = self.mailbox.send(self.sender, self.reader, 'private')['id']
        with ThreadPoolExecutor(1) as pool:
            earlier = self.start_watch(pool, self.monitor, 'detailed')
            with self.monitor.condition:
                self.read_and_publish(self.reader, message_id, {self.sender: self.monitor})
                self.monitor.update('agent:child', kind='agent', status='running')
                # Earlier is active and has a pending receipt, but neither a new
                # snapshot nor a stale cursor can see what came before that call.
                snapshot = self.monitor.watch(detail_level='detailed')
                self.assertEqual(snapshot, self.monitor.watch(0, detail_level='detailed'))
                self.assertNotIn('read_receipts', snapshot)
            self.assertEqual(earlier.result(2), {**snapshot, 'read_receipts': [
                {'message_id': message_id, 'recipient_id': self.reader},
            ]})
        self.assertEqual(self.monitor.watch(1, 0.02, detail_level='detailed'), {'cursor': 1, 'changes': []})
        reopened = self.open_store()
        self.assertEqual(Monitor(reopened, self.sender).watch(0, detail_level='detailed'), snapshot)
        self.assertEqual(reopened.read_monitor(self.sender), self.store.read_monitor(self.sender))
        self.assertNotIn(message_id, str(reopened.read_monitor(self.sender)))
        self.assertIsNotNone(AgentToAgentMailbox(reopened.database).read(self.reader, message_id)['read_at'])

    def test_detailed_watch_keeps_inbox_changes_and_guidance_with_multiple_receipts(self):
        message_id = self.mailbox.send(self.sender, self.reader, 'private', cc=[self.cc])['id']
        incoming = self.mailbox.send(self.reader, self.sender, 'feedback', kind='feedback')['id']
        pending = threading.Event()
        with ThreadPoolExecutor(1) as pool:
            watch = self.start_watch(pool, self.monitor, 'detailed', wake_if=pending.is_set)
            with self.monitor.condition:
                self.read_and_publish(self.reader, message_id, {self.sender: self.monitor})
                self.read_and_publish(self.cc, message_id, {self.sender: self.monitor})
                self.monitor.update(f'mailbox:{self.sender}', kind='mailbox', session_id=self.sender,
                                    unread_count=1, latest_id=incoming)
                pending.set()
                self.monitor._wake()
            self.assertEqual(watch.result(2), {
                'cursor': 1,
                'changes': [{'id': f'mailbox:{self.sender}', 'kind': 'mailbox',
                             'session_id': self.sender, 'unread_count': 1, 'latest_id': incoming, 'version': 1}],
                'interrupted_by_guidance': True,
                'read_receipts': [{'message_id': message_id, 'recipient_id': self.reader},
                                  {'message_id': message_id, 'recipient_id': self.cc}],
            })

    def test_detailed_guidance_and_cancellation_wake_without_receipts(self):
        pending = threading.Event()
        with ThreadPoolExecutor(1) as pool:
            watch = self.start_watch(pool, self.monitor, 'detailed', wake_if=pending.is_set)
            pending.set()
            self.monitor._wake()
            self.assertEqual(watch.result(2), {'cursor': 0, 'changes': [], 'interrupted_by_guidance': True})

            cancellation = CancellationToken()
            watch = self.start_watch(pool, self.monitor, 'detailed', context=ExecutionContext(cancellation))
            cancellation.cancel()
            with self.assertRaises(RunCancelled):
                watch.result(2)
            self.assertEqual(self.monitor._receipt_waiters, {})

    def test_detail_level_validation(self):
        for detail_level in ('other', [], None):
            with self.subTest(detail_level=detail_level), self.assertRaisesRegex(ValueError, 'detail_level'):
                self.monitor.watch(detail_level=detail_level)

    def test_only_one_concurrent_reader_acknowledges_each_delivery(self):
        message_id = self.mailbox.send(self.sender, self.reader, 'private', cc=[self.cc])['id']
        second = AgentToAgentMailbox(self.open_store().database)
        tasks = [(box, recipient) for recipient in (self.reader, self.cc) for box in (self.mailbox, second)]
        barrier = threading.Barrier(len(tasks))

        def read(task):
            box, recipient = task
            barrier.wait(2)
            return box.read_with_ack(recipient, message_id)

        with ThreadPoolExecutor(len(tasks)) as pool:
            results = list(pool.map(read, tasks))
        for offset, recipient in ((0, self.reader), (2, self.cc)):
            (first, first_ack), (other, other_ack) = results[offset:offset + 2]
            self.assertEqual(first, other)
            self.assertEqual(first['sender_id'], self.sender)
            self.assertIsNotNone(first['read_at'])
            self.assertEqual(int(first_ack) + int(other_ack), 1)
            self.assertEqual(self.mailbox.read_with_ack(recipient, message_id), (first, False))
            self.assertEqual(self.mailbox.read(recipient, message_id), first)
        with self.assertRaises(FileNotFoundError):
            self.mailbox.read_with_ack(self.sender, message_id)


if __name__ == '__main__':
    unittest.main()
