"""Flushed parent-process feedback for bounded collection stages."""

from contextlib import contextmanager
import re
import threading
import time


_output_lock = threading.Lock()


def report_progress(message):
    text = re.sub(r'ocid1\.[A-Za-z0-9_.-]+', '<resource-ocid>', str(message))
    text = ''.join(character if ord(character) >= 32 and ord(character) != 127 else ' '
                   for character in text)
    with _output_lock:
        print(text, flush=True)


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
