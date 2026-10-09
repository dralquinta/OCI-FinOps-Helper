"""Bounded persistent OCI CLI processes with isolated command output."""

import contextlib
import io
import json
import os
from pathlib import Path
import queue
import select
import subprocess
import sys
import threading
import time


def serve(input_stream=None, output_stream=None, invoke=None):
    """Read one command at a time; reserve real stdio for the JSON protocol."""
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    if invoke is None:
        from src import distribution
        distribution._persistent_worker = True
        invoke = distribution.invoke_oci
    for line in input_stream:
        stdout, stderr = io.StringIO(), io.StringIO()
        original_stdin = sys.stdin
        try:
            request = json.loads(line)
            arguments = request['arguments']
            if not isinstance(arguments, list) or not all(isinstance(arg, str) for arg in arguments):
                raise ValueError('Worker arguments must be strings')
            sys.stdin = io.StringIO('')
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                status = invoke(arguments)
        except Exception as error:
            status = 1
            stderr.write(type(error).__name__ + ': ' + str(error) + '\n')
        finally:
            sys.stdin = original_stdin
        # Match sys.exit: a message is printed to stderr and exits with 1,
        # rather than becoming a non-numeric CompletedProcess return code.
        if status is None:
            status = 0
        elif not isinstance(status, int):
            stderr.write(str(status) + '\n')
            status = 1
        else:
            status &= 255
        output_stream.write(json.dumps({'returncode': status, 'stdout': stdout.getvalue(),
                                       'stderr': stderr.getvalue()}) + '\n')
        output_stream.flush()
    return 0


class OCIWorker:
    """A dedicated process handling serialized CLI requests without reimporting."""

    def __init__(self, command=None):
        self.command = command
        self.process = None
        self.buffer = b''

    def _start(self):
        if self.command is not None:
            command = self.command
        elif getattr(sys, 'frozen', False):
            command = [sys.executable, '--internal-oci-worker']
        else:
            command = [sys.executable, '-u', str(Path(__file__).resolve())]
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.buffer = b''

    def run(self, arguments, timeout=None):
        started = time.monotonic()
        if self.process is None or self.process.poll() is not None:
            self.close()
            self._start()
        try:
            self.process.stdin.write((json.dumps({'arguments': arguments}) + '\n').encode('utf-8'))
            self.process.stdin.flush()
            while b'\n' not in self.buffer:
                remaining = None if timeout is None else timeout - (time.monotonic() - started)
                if remaining is not None and remaining <= 0:
                    raise subprocess.TimeoutExpired(['oci', *arguments], timeout)
                ready, _, _ = select.select([self.process.stdout], [], [], remaining)
                if not ready:
                    raise subprocess.TimeoutExpired(['oci', *arguments], timeout)
                chunk = os.read(self.process.stdout.fileno(), 65536)
                if not chunk:
                    raise RuntimeError('OCI worker exited before completing its request')
                self.buffer += chunk
            line, self.buffer = self.buffer.split(b'\n', 1)
            return json.loads(line.decode('utf-8'))
        except BaseException:
            self.close()
            raise

    def close(self):
        process, self.process = self.process, None
        self.buffer = b''
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait()
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    stream.close()


class OCIWorkerPool:
    """At most four live CLI interpreters; waiting requests consume no process."""

    def __init__(self, max_workers=4, worker_factory=OCIWorker):
        if not 1 <= max_workers <= 4:
            raise ValueError('OCI worker pool must contain between one and four workers')
        self.workers = [worker_factory() for _ in range(max_workers)]
        self.available = queue.LifoQueue()
        for worker in self.workers:
            self.available.put(worker)
        self.closed = False
        self.lock = threading.Lock()

    def run(self, command, **kwargs):
        timeout = kwargs.get('timeout')
        started = time.monotonic()
        with self.lock:
            if self.closed:
                raise RuntimeError('OCI worker pool is closed')
        try:
            worker = self.available.get(timeout=timeout)
        except queue.Empty:
            raise subprocess.TimeoutExpired(command, timeout) from None
        try:
            with self.lock:
                if self.closed:
                    raise RuntimeError('OCI worker pool is closed')
            remaining = None if timeout is None else max(0, timeout - (time.monotonic() - started))
            try:
                result = worker.run(command[1:], timeout=remaining)
            except subprocess.TimeoutExpired as error:
                raise subprocess.TimeoutExpired(command, timeout, output=error.output,
                                                stderr=error.stderr) from None
            text = kwargs.get('text') or kwargs.get('universal_newlines') or kwargs.get('encoding') or kwargs.get('errors')
            encoding, errors = kwargs.get('encoding') or 'utf-8', kwargs.get('errors') or 'strict'
            stdout, stderr = result['stdout'], result['stderr']
            if text:
                stdout = stdout.replace('\r\n', '\n').replace('\r', '\n')
                stderr = stderr.replace('\r\n', '\n').replace('\r', '\n')
            else:
                stdout, stderr = stdout.encode(encoding, errors), stderr.encode(encoding, errors)
            completed = subprocess.CompletedProcess(command, result['returncode'], stdout, stderr)
            if kwargs.get('check'):
                completed.check_returncode()
            return completed
        finally:
            self.available.put(worker)

    def close(self):
        with self.lock:
            self.closed = True
        for worker in self.workers:
            worker.close()

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        self.close()


if __name__ == '__main__':
    # A source worker may start after collection changes the working directory.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    raise SystemExit(serve())
