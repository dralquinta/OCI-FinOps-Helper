import contextlib
import io
import os
import shutil
import unittest
from unittest.mock import patch

from src.utils.feedback import BillingProgress, report_progress


class RecordingOutput(io.StringIO):
    def __init__(self, tty=False):
        super().__init__()
        self.tty = tty
        self.flushes = 0
    def isatty(self):
        return self.tty
    def flush(self):
        self.flushes += 1


class BillingProgressTests(unittest.TestCase):
    def test_large_page_count_has_bounded_plain_output_and_active_state(self):
        output = RecordingOutput()
        with contextlib.redirect_stdout(output), patch.dict(os.environ, {'TERM': 'xterm'}):
            with BillingProgress(400) as progress:
                self.assertIn('Billing collection started', output.getvalue())
                self.assertGreater(output.flushes, 0)
                for batch in range(100):
                    jobs = [('COST' if index % 2 == 0 else 'USAGE', f'day-{batch}-{index}') for index in range(4)]
                    for kind, start in jobs:
                        progress.window_started(kind, start, 'end')
                    self.assertEqual(4, progress.active_count)
                    for kind, start in jobs:
                        for page in range(30):
                            progress.page_saved(kind, start, 2)
                        progress.window_finished(kind, start, True)
                    self.assertEqual(0, progress.active_count)
                snapshot = progress.snapshot()
        self.assertEqual(400, snapshot['completed_windows'])
        self.assertEqual({'records': 12000, 'pages': 6000}, snapshot['COST'])
        self.assertEqual(2, len(output.getvalue().splitlines()))
        self.assertNotIn('\x1b', output.getvalue())
        self.assertIn('COST 12,000 records / 6,000 pages', output.getvalue())

    def test_tty_repaints_at_most_once_per_interval_and_warnings_redraw(self):
        output = RecordingOutput(tty=True)
        with contextlib.redirect_stdout(output), patch.dict(os.environ, {'TERM': 'xterm'}), \
             patch('src.utils.feedback.shutil.get_terminal_size', return_value=shutil.os.terminal_size((160, 30))), \
             patch('src.utils.feedback.time.monotonic', return_value=100) as clock:
            with BillingProgress(1) as progress:
                progress.window_started('COST', '2026-09-01', '2026-09-02')
                for index in range(100):
                    progress.page_saved('COST', '2026-09-01', 10)
                self.assertEqual(1, output.getvalue().count('\x1b[2K'))
                clock.return_value = 101.1
                progress.page_saved('COST', '2026-09-01', 10)
                self.assertEqual(2, output.getvalue().count('\x1b[2K'))
                self.assertIn('2026-09-01', output.getvalue())
                report_progress('warning ocid1.tenancy.oc1.private')
                self.assertIn('warning <resource-ocid>\n', output.getvalue())
                progress.window_finished('COST', '2026-09-01', True)
        self.assertIn('Billing collection complete:', output.getvalue())
        self.assertNotIn('ocid1.', output.getvalue())

    def test_failed_windows_retries_and_interruption_are_truthful(self):
        output = RecordingOutput()
        with contextlib.redirect_stdout(output):
            with BillingProgress(2) as progress:
                progress.window_started('COST', 'day', 'end')
                progress.retry('COST', 'day', 503, 1, 4)
                progress.page_saved('COST', 'day', 3)
                progress.window_finished('COST', 'day', True)
                progress.window_started('USAGE', 'day', 'end')
                progress.window_finished('USAGE', 'day', False)
                progress.window_finished('USAGE', 'day', False)
        self.assertIn('retry 1/4', output.getvalue())
        self.assertIn('partial: 1/2 windows completed; failed 1;', output.getvalue())
        self.assertEqual(1, progress.snapshot()['retries'])
        self.assertEqual(0, progress.active_count)
        output = RecordingOutput()
        with contextlib.redirect_stdout(output), self.assertRaises(KeyboardInterrupt):
            with BillingProgress(1) as interrupted:
                interrupted.window_started('COST', 'day', 'end')
                raise KeyboardInterrupt()
        self.assertIn('Billing collection interrupted:', output.getvalue())
        self.assertEqual(0, interrupted.active_count)

    def test_dumb_terminal_uses_plain_periodic_summaries(self):
        output = RecordingOutput(tty=True)
        with contextlib.redirect_stdout(output), patch.dict(os.environ, {'TERM': 'dumb'}), \
             patch('src.utils.feedback.time.monotonic', return_value=100) as clock:
            with BillingProgress(1) as progress:
                progress.window_started('COST', 'day', 'end')
                clock.return_value = 131
                progress.page_saved('COST', 'day', 2)
                progress.window_finished('COST', 'day', True)
        self.assertEqual(3, len(output.getvalue().splitlines()))
        self.assertNotIn('\x1b', output.getvalue())
        self.assertNotIn('\r', output.getvalue())
