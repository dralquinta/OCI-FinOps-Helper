import contextlib
import io
import os
import re
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

    def test_colored_bar_tracks_finished_work_and_respects_terminal_width(self):
        for width in (80, 40, 16, 1):
            output = RecordingOutput(tty=True)
            with contextlib.redirect_stdout(output), patch.dict(os.environ, {'TERM': 'xterm'}, clear=True), \
                 patch('src.utils.feedback.shutil.get_terminal_size', return_value=os.terminal_size((width, 24))), \
                 patch('src.utils.feedback.time.monotonic', return_value=100) as clock:
                with BillingProgress(2) as progress:
                    progress.window_started('COST', 'day', 'end')
                    progress.page_saved('COST', 'day', 120000)
                    clock.return_value = 102
                    progress.window_finished('COST', 'day', True)
                    progress.window_started('USAGE', 'day', 'end')
                    progress.retry('USAGE', 'day', 503, 1, 4)
                    clock.return_value = 104
                    progress.window_finished('USAGE', 'day', False)
            frames = output.getvalue().split('\r\x1b[2K')[1:]
            for frame in frames:
                line = frame.split('\n')[0]
                plain = re.sub(r'\x1b\[[0-9;]*m', '', line)
                if plain.startswith(('Billing collection', 'Billing USAGE')):
                    continue
                self.assertLessEqual(len(plain), max(0, width - 1))
                self.assertNotIn('\x1b', plain)
            if width == 80:
                self.assertIn('50%', output.getvalue())
                self.assertIn('100%', output.getvalue())
                self.assertRegex(output.getvalue(), r'\[[#-]+\]')
                for color in (36, 33, 31):
                    self.assertIn(f'\x1b[{color}m', output.getvalue())
                self.assertIn('failed 1', output.getvalue())
                self.assertIn('partial: 1/2 windows completed', output.getvalue())
                self.assertIn('\x1b[0m\n', output.getvalue())

    def test_no_color_retains_bar_and_success_zero_work_are_green(self):
        for no_color in (True, False):
            output = RecordingOutput(tty=True)
            environment = {'TERM': 'xterm'}
            if no_color:
                environment['NO_COLOR'] = ''
            with contextlib.redirect_stdout(output), patch.dict(os.environ, environment, clear=True):
                with BillingProgress(0):
                    pass
            self.assertIn('100%', output.getvalue())
            self.assertIn('\r\x1b[2K', output.getvalue())
            if no_color:
                self.assertNotRegex(output.getvalue(), r'\x1b\[[0-9;]*m')
            else:
                self.assertIn('\x1b[32m', output.getvalue())
            self.assertIn('complete: 0/0 windows completed', output.getvalue())

    def test_final_bar_remains_visible_above_summary(self):
        output = RecordingOutput(tty=True)
        with contextlib.redirect_stdout(output), patch.dict(os.environ, {'TERM': 'xterm'}, clear=True):
            with BillingProgress(1) as progress:
                progress.window_started('COST', 'day', 'end')
                progress.window_finished('COST', 'day', True)
        final_frame = output.getvalue().split('\r\x1b[2K')[-1]
        lines = re.sub(r'\x1b\[[0-9;]*m', '', final_frame).splitlines()
        self.assertIn('100%', lines[0])
        self.assertIn('Billing collection complete:', lines[1])
