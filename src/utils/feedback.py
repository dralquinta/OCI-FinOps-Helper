"""Flushed parent-process feedback for bounded collection stages."""

from contextlib import contextmanager
import re
import math
import os
import shutil
import sys
import threading
import time


_output_lock = threading.RLock()
_active_billing = None


def _safe_text(message):
    text = re.sub(r'ocid1\.[A-Za-z0-9_.-]+', '<resource-ocid>', str(message))
    text = ''.join(character if ord(character) >= 32 and ord(character) != 127 else ' '
                   for character in text)
    return text


def report_progress(message):
    text = _safe_text(message)
    with _output_lock:
        active = _active_billing
        redraw = active is not None and active._tty and active._stream is sys.stdout
        if redraw:
            active._clear_line()
        print(text, flush=True)
        if redraw:
            active._emit(force=True)


@contextmanager
def progress_heartbeat(label, interval=30):
    """Keep slow operations visibly active without forwarding OCI payloads."""
    if interval <= 0:
        raise ValueError('Heartbeat interval must be positive')
    stop = threading.Event()
    started = time.monotonic()

    def pulse():
        while not stop.wait(interval):
            report_progress(f'{label}: still working ({time.monotonic() - started:.0f}s elapsed)')

    thread = threading.Thread(target=pulse, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join()


class BillingProgress:
    """Aggregate billing progress with only counters and currently active jobs."""

    def __init__(self, total_windows, refresh_interval=1.0, summary_interval=30.0):
        if total_windows < 0:
            raise ValueError('total_windows must be nonnegative')
        if any(not math.isfinite(value) or value <= 0
               for value in (refresh_interval, summary_interval)):
            raise ValueError('Progress intervals must be finite and positive')
        self.total_windows = total_windows
        self.refresh_interval, self.summary_interval = refresh_interval, summary_interval
        self._totals = {kind: {'records': 0, 'pages': 0} for kind in ('COST', 'USAGE')}
        self._active = {}
        self._completed = self._failed = self._retries = 0
        self._stop = threading.Event()
        self._thread = None
        self._stream = None
        self._tty = self._line_visible = self._colors = False
        self._started = self._last_output = 0

    def __enter__(self):
        global _active_billing
        with _output_lock:
            if _active_billing is not None:
                raise RuntimeError('Billing progress is already active')
            self._stream = sys.stdout
            self._tty = bool(getattr(self._stream, 'isatty', lambda: False)()) and os.environ.get('TERM') != 'dumb'
            self._colors = self._tty and 'NO_COLOR' not in os.environ
            self._started = time.monotonic()
            _active_billing = self
            if self._tty:
                print(self._paint(f'Billing collection started: {self.total_windows} daily windows', 36), file=self._stream, flush=True)
            self._emit(force=True, state='started')
        self._thread = threading.Thread(target=self._pulse, daemon=True)
        self._thread.start()
        return self

    def _pulse(self):
        interval = self.refresh_interval if self._tty else self.summary_interval
        while not self._stop.wait(interval):
            with _output_lock:
                self._emit()

    def _elapsed(self):
        seconds = int(max(0, time.monotonic() - self._started))
        minutes, seconds = divmod(seconds, 60)
        return f'{minutes:02d}:{seconds:02d}'

    @staticmethod
    def _compact_number(number):
        if number >= 1000000:
            return f'{number / 1000000:.1f}m'
        return f'{number:,}'

    def _summary(self, state):
        cost, usage = self._totals['COST'], self._totals['USAGE']
        return (f'Billing collection {state}: {self._completed}/{self.total_windows} windows completed; '
                f'failed {self._failed}; COST {cost["records"]:,} records / {cost["pages"]:,} pages; '
                f'USAGE {usage["records"]:,} records / {usage["pages"]:,} pages; '
                f'retries {self._retries}; elapsed {self._elapsed()}')

    def _clear_line(self):
        if self._line_visible:
            self._stream.write('\r\x1b[2K')
            self._stream.flush()
            self._line_visible = False

    def _paint(self, text, color):
        return f'\x1b[{color}m{text}\x1b[0m' if self._colors and text else text

    def _status_segments(self, state, width):
        finished = self._completed + self._failed
        ratio = min(1, finished / self.total_windows) if self.total_windows else 1
        percentage = int(100 * ratio)
        bar_size = 8 if width >= 70 and not self._failed else 4
        filled = int(bar_size * ratio)
        bar = '[' + '#' * filled + '-' * (bar_size - filled) + ']'
        color = (32 if state == 'complete' else 33 if state in ('partial', 'interrupted')
                 else 31 if state == 'failed' or self._failed else 32 if ratio == 1 else 36)
        cost, usage = self._totals['COST']['records'], self._totals['USAGE']['records']
        records = f'COST {self._compact_number(cost)} USAGE {self._compact_number(usage)} records'
        prefix = f'Billing {bar} {percentage}% | '
        activity = f'active {len(self._active)}'
        failure = f' failed {self._failed}' if self._failed else ''
        retry = f'retry {self._retries}'
        elapsed = self._elapsed()
        def compact(value):
            return f'{value / 1000000:.1f}m' if value >= 1000000 else f'{value / 1000:.1f}k' if value >= 1000 else str(value)
        if len(prefix + records + activity + failure + retry + elapsed) + 9 > width:
            records = f'COST {compact(cost)} USAGE {compact(usage)} records'
            prefix = f'{bar} {percentage}% | '
        if width < 65:
            records = f'C {compact(cost)} U {compact(usage)} records'
            activity = f'a{len(self._active)}'
            retry = f'r{self._retries}'
        if width < 55:
            records = ''
            activity = ''
        segments = [(prefix, color)]
        if records:
            segments.append((records + ' | ', 36))
        if activity:
            segments.append((activity, 36))
        if failure:
            segments.append((failure, 31))
        segments.extend([(' | ' + retry, 33 if self._retries else 36), (' | ' + elapsed, 36)])
        if width >= 100 and self._active:
            _, start = next(iter(self._active))
            segments.append((f' | {start}', 36))
        return segments

    def _emit(self, force=False, state='working'):
        now = time.monotonic()
        interval = self.refresh_interval if self._tty else self.summary_interval
        if not force and now - self._last_output < interval:
            return
        if self._tty:
            width = shutil.get_terminal_size(fallback=(80, 24)).columns
            remaining = max(0, width - 1)
            rendered = []
            # Clip plain text before applying SGR so ANSI sequences stay intact.
            for text, color in self._status_segments(state, width):
                plain = _safe_text(text)[:remaining]
                rendered.append(self._paint(plain, color))
                remaining -= len(plain)
                if not remaining:
                    break
            self._stream.write('\r\x1b[2K' + ''.join(rendered))
            self._stream.flush()
            self._line_visible = True
        else:
            print(self._summary(state), file=self._stream, flush=True)
        self._last_output = now

    @property
    def active_count(self):
        with _output_lock:
            return len(self._active)

    def snapshot(self):
        with _output_lock:
            return {'completed_windows': self._completed, 'failed_windows': self._failed,
                    'active_count': len(self._active), 'retries': self._retries,
                    **{kind: dict(values) for kind, values in self._totals.items()}}

    def window_started(self, kind, from_date, to_date):
        with _output_lock:
            self._active[kind, from_date] = to_date
            self._emit()

    def page_saved(self, kind, from_date, rowcount):
        with _output_lock:
            if (kind, from_date) not in self._active:
                return
            self._totals[kind]['records'] += rowcount
            self._totals[kind]['pages'] += 1
            self._emit()

    def window_finished(self, kind, from_date, success=True):
        with _output_lock:
            if (kind, from_date) not in self._active:
                return
            del self._active[kind, from_date]
            self._completed += bool(success)
            self._failed += not bool(success)
            self._emit()

    def retry(self, kind, from_date, status, attempt, max_attempts):
        with _output_lock:
            self._retries += 1
            report_progress(f'Billing {kind} {from_date}: HTTP {status}; '
                            f'retry {attempt}/{max_attempts}')

    def __exit__(self, exc_type, exc, traceback):
        global _active_billing
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        with _output_lock:
            self._active.clear()
            if exc_type is not None:
                state = 'interrupted' if issubclass(exc_type, (KeyboardInterrupt, SystemExit)) else 'failed'
            else:
                state = 'partial' if self._failed or self._completed != self.total_windows else 'complete'
            if self._tty:
                self._emit(force=True, state=state)
                self._stream.write('\n')
                self._line_visible = False
            color = 32 if state == 'complete' else 31 if state == 'failed' else 33
            print(self._paint(self._summary(state), color), file=self._stream, flush=True)
            if _active_billing is self:
                _active_billing = None
