"""Acquisition control tests only: no provider requests and no market fixtures."""
import subprocess
import unittest
from unittest.mock import patch

from scripts.fetch_demo_eod import run_worker_bounded


class AcquisitionLimitTests(unittest.TestCase):
    def test_success_does_not_retry(self):
        completed = subprocess.CompletedProcess(['worker'], 0, '', '')
        with patch('scripts.fetch_demo_eod.subprocess.run', return_value=completed) as run, \
             patch('scripts.fetch_demo_eod.time.sleep') as sleep:
            self.assertEqual(run_worker_bounded(['worker']), (completed, 0))
            self.assertEqual(run.call_count, 1)
            sleep.assert_not_called()

    def test_timeout_retries_once_with_bounded_backoff(self):
        completed = subprocess.CompletedProcess(['worker'], 0, '', '')
        timeout = subprocess.TimeoutExpired(['worker'], 45)
        with patch('scripts.fetch_demo_eod.subprocess.run', side_effect=[timeout, completed]) as run, \
             patch('scripts.fetch_demo_eod.time.sleep') as sleep:
            self.assertEqual(run_worker_bounded(['worker']), (completed, 1))
            self.assertEqual(run.call_count, 2)
            sleep.assert_called_once_with(10)
            self.assertEqual(run.call_args.kwargs['timeout'], 45)
        with patch('scripts.fetch_demo_eod.subprocess.run', side_effect=timeout) as run, \
             patch('scripts.fetch_demo_eod.time.sleep') as sleep:
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                run_worker_bounded(['worker'])
            self.assertEqual(caught.exception.retries_used, 1)
            self.assertEqual(run.call_count, 2)
            sleep.assert_called_once_with(10)

    def test_nonzero_exit_is_not_retried(self):
        denied = subprocess.CompletedProcess(['worker'], 1, '', 'Source unavailable')
        with patch('scripts.fetch_demo_eod.subprocess.run', return_value=denied) as run, \
             patch('scripts.fetch_demo_eod.time.sleep') as sleep:
            self.assertEqual(run_worker_bounded(['worker']), (denied, 0))
            self.assertEqual(run.call_count, 1)
            sleep.assert_not_called()
