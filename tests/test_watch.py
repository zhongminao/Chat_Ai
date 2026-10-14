import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent.core.cancellation import CancellationToken, ExecutionContext, RunCancelled
from agent.core.monitor import Monitor


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'watch.json'
        self.monitor = Monitor(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_snapshot_diff_repeated_reads_and_persistence(self):
        self.assertEqual(self.monitor.watch(), {'cursor': 0, 'changes': []})
        self.monitor.update('agent:a', kind='agent', status='running')
        snapshot = self.monitor.watch()
        self.monitor.update('bash:b', kind='bash', status='running', output_path='/tmp/output.log')
        self.monitor.update('agent:a', kind='agent', status='completed', result_path='/tmp/report.md')
        diff = self.monitor.watch(snapshot['cursor'])
        self.assertEqual({v['id'] for v in diff['changes']}, {'agent:a', 'bash:b'})
        self.assertEqual(diff, self.monitor.watch(snapshot['cursor']), 'reading does not consume updates')
        self.assertEqual(diff, Monitor(self.path).watch(snapshot['cursor']))
        self.assertEqual(self.monitor.watch(diff['cursor'])['changes'], [])
        self.monitor.update('agent:a', kind='agent', status='completed', result_path='/tmp/report.md')
        self.assertEqual(self.monitor.watch()['cursor'], diff['cursor'], 'unchanged states do not wake consumers')
        self.monitor.remove('agent:a')
        self.assertTrue(self.monitor.watch(diff['cursor'])['changes'][0]['deleted'])
        self.assertEqual([v['id'] for v in self.monitor.watch()['changes']], ['bash:b'])

    def test_wait_wakes_for_any_change_and_other_consumers_do_not_steal_it(self):
        self.monitor.update('agent:a', kind='agent', status='running')
        cursor = self.monitor.watch()['cursor']
        with ThreadPoolExecutor(2) as pool:
            first = pool.submit(self.monitor.watch, cursor, 5)
            second = pool.submit(self.monitor.watch, cursor, 5)
            self.monitor.update('agent:a', kind='agent', status='completed', result_path='/tmp/a.md')
            self.assertEqual(first.result(2), second.result(2))

    def test_wait_timeout_and_cancellation(self):
        self.assertEqual(self.monitor.watch(0, 0.02), {'cursor': 0, 'changes': []})
        token = CancellationToken()
        with ThreadPoolExecutor(1) as pool:
            waiting = pool.submit(self.monitor.watch, 0, 120, ExecutionContext(token))
            token.cancel()
            with self.assertRaises(RunCancelled):
                waiting.result(2)

    def test_invalid_cursors_and_timeouts(self):
        for cursor in [-1, True, '1', 10]:
            with self.assertRaises(ValueError):
                self.monitor.watch(cursor)
        for timeout in [-1, 121, float('nan')]:
            with self.assertRaises(ValueError):
                self.monitor.watch(timeout=timeout)

    def test_invalid_producer_data_does_not_advance_state(self):
        self.monitor.update('valid', kind='bash', status='running')
        snapshot = self.monitor.watch()
        with self.assertRaises(TypeError):
            self.monitor.update('invalid', kind='other', detail=object())
        self.assertEqual(snapshot, self.monitor.watch())
        self.assertEqual(snapshot, Monitor(self.path).watch())


if __name__ == '__main__':
    unittest.main()
