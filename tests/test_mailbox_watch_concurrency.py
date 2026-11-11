"""Regression for monitor condition/runtime lock inversion and HTTP-loop blocking."""
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent.agentsessionstate.config import load
from agent.core.session_registry import SessionRegistry
from agent.web import app as web


class MailboxWatchConcurrencyTests(unittest.TestCase):
    def test_notify_and_watch_pending_check_do_not_deadlock(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = SessionRegistry(replace(load(), storage_dir=Path(directory),
                                               workspace=Path(directory), mcp={}))
            parent = registry.create()
            child = registry.create(parent_session_id=parent.session.id)
            monitor = registry.monitor(parent.session.id)
            checking, sending = threading.Event(), threading.Event()
            results, errors = {}, []
            original = registry.mailbox.send

            def send(*args, **kwargs):
                sending.set()
                return original(*args, **kwargs)

            def pending():
                checking.set()
                if not sending.wait(2):
                    raise AssertionError('notification never acquired recipient lock')
                return parent.steering.has_pending()

            def run(key, action):
                try:
                    results[key] = action()
                except BaseException as exc:
                    errors.append(exc)

            try:
                with patch.object(registry.mailbox, 'send', side_effect=send):
                    waiter = threading.Thread(target=run, args=('watch', lambda: monitor.watch(0, 3, wake_if=pending)), daemon=True)
                    waiter.start()
                    self.assertTrue(checking.wait(2))
                    notifier = threading.Thread(target=run, args=('notify', lambda: registry.notify_agent(
                        child.session.id, parent.session.id, 'feedback', kind='feedback')), daemon=True)
                    notifier.start()
                    notifier.join(3)
                    waiter.join(3)
                    self.assertFalse(notifier.is_alive(), 'notify_agent deadlocked with watch')
                    self.assertFalse(waiter.is_alive(), 'watch deadlocked with notify_agent')
                    self.assertEqual(errors, [])
                    self.assertTrue(results['watch']['interrupted_by_guidance'])
                    self.assertEqual(registry.mailbox_unread_count(parent.session.id), 1)
                    snapshot = monitor.watch()
                    mailbox = next(item for item in snapshot['changes']
                                   if item['id'] == f'mailbox:{parent.session.id}')
                    self.assertEqual(mailbox['unread_count'], 1)
            finally:
                for runtime in list(registry.items.values()):
                    runtime.queue.put(None)
                    runtime.worker.join(2)
                registry.store.database.close()


class WatchEventLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_registry_lookup_does_not_block_event_loop(self):
        loop_thread = threading.get_ident()
        calls = []
        expected = {'cursor': 0, 'changes': []}

        def lookup(identifier):
            calls.append(threading.get_ident())
            if threading.get_ident() == loop_thread:
                raise AssertionError('registry lookup runs on the event loop')
            return SimpleNamespace(watch=lambda cursor, timeout: expected)

        def directory(identifier):
            if threading.get_ident() == loop_thread:
                raise AssertionError('session database lookup runs on the event loop')

        with patch.object(web, 'registry', SimpleNamespace(monitor=lookup)), patch.object(web, 'directory_for', side_effect=directory):
            self.assertEqual(await web.watch('session-id', cursor=0, timeout=0), expected)
        self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()

