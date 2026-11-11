import tempfile
import threading
import time
import unittest
from pathlib import Path

from agent.core.cancellation import CancellationToken, ExecutionContext, RunCancelled
from agent.tools.executor import execute, run_bash
from agent.tools.schema import TOOL_SCHEMAS


class BashTimeoutTests(unittest.TestCase):
    def test_schema_exposes_optional_bounded_timeout(self):
        schema = next(item['function']['parameters'] for item in TOOL_SCHEMAS
                      if item['function']['name'] == 'run_bash')
        self.assertEqual(schema['required'], ['command'])
        self.assertEqual(schema['properties']['timeout'], {
            'type': 'integer', 'minimum': 1, 'maximum': 86400, 'default': 30,
            'description': 'Maximum execution time in seconds (up to 1 day).'})

    def test_default_and_custom_timeout_are_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(run_bash(root, 'printf hello'), 'hello')
            self.assertEqual(execute(root, 'run_bash', {'command': 'printf custom', 'timeout': 86400}), 'custom')

    def test_invalid_timeout_is_rejected_before_starting_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / 'started'
            for invalid in (0, -1, 86401, 1.5, True, None, '10'):
                with self.subTest(invalid=invalid):
                    result = execute(root, 'run_bash', {'command': 'touch started', 'timeout': invalid})
                    self.assertIn('[tool error] ValueError: timeout must be an integer', result)
                    self.assertFalse(marker.exists())

    def test_timeout_terminates_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = time.monotonic()
            result = execute(root, 'run_bash', {'command': 'sleep 5', 'timeout': 1})
            self.assertIn('[tool error] TimeoutExpired:', result)
            self.assertLess(time.monotonic() - before, 4)

    def test_stop_cancels_even_with_one_day_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            started = root / 'started'
            token = CancellationToken()
            caught = []
            def call():
                try:
                    run_bash(root, 'touch started; sleep 60', ExecutionContext(token), timeout=86400)
                except RunCancelled:
                    caught.append(True)
            thread = threading.Thread(target=call)
            thread.start()
            try:
                deadline = time.monotonic() + 2
                while not started.exists() and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(started.exists())
                token.cancel()
                thread.join(4)
                self.assertFalse(thread.is_alive())
                self.assertEqual(caught, [True])
            finally:
                token.cancel()
                thread.join(4)


if __name__ == '__main__':
    unittest.main()
