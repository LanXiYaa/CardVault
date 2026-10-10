"""Bounded, cancellable hashing including potentially blocking handle cleanup."""
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from .io_guard import ReadCancelled


class HashTimeout(TimeoutError):
    """Stop a task on an unresponsive device, retaining staged copies."""


def worker_command(path, algorithm, limit):
    entry = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).resolve().parents[1] / 'start.py')]
    return entry + ['--hash-worker', str(path), algorithm, 'none' if limit is None else str(limit)]


class HashProcesses:
    def __init__(self, timeout=30):
        self.timeout = timeout
        self.lock = threading.Lock()
        self.active = {}

    def waiting(self, job_id):
        with self.lock:
            records = [v for v in self.active.values() if v['job'] == job_id]
            if not records:
                return 0, ''
            record = min(records, key=lambda v: v['heartbeat'])
            return time.monotonic() - record['heartbeat'], record['path'] + ' [' + record['phase'] + ']'

    def digest(self, path, algorithm, limit, job_id, stopped, progress):
        if stopped():
            raise ReadCancelled()
        env = os.environ.copy()
        env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
        process = subprocess.Popen(worker_command(path, algorithm, limit), stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        messages = queue.Queue()
        def receive():
            try:
                for line in process.stdout:
                    messages.put(json.loads(line))
            except Exception as error:
                messages.put({'error': str(error)})
            finally:
                process.stdout.close()
                messages.put(None)
        reader = threading.Thread(target=receive, daemon=True, name='hash-progress')
        reader.start()
        key = id(process)
        record = dict(job=job_id, path=str(path), phase='starting', heartbeat=time.monotonic())
        with self.lock:
            self.active[key] = record
        digest = None
        read = 0
        try:
            while True:
                if stopped():
                    raise ReadCancelled()
                if time.monotonic() - record['heartbeat'] >= self.timeout:
                    raise HashTimeout('Hash I/O timed out (' + record['phase'] + '): ' + str(path))
                try:
                    message = messages.get(timeout=.05)
                except queue.Empty:
                    continue
                if message is None:
                    code = process.wait(timeout=1)
                    if code or digest is None:
                        raise OSError('Hash worker exited without a verified result: ' + str(path))
                    return digest
                with self.lock:
                    record['heartbeat'] = time.monotonic()
                    record['phase'] = message.get('phase', record['phase'])
                if 'error' in message:
                    raise OSError(message['error'])
                count = message.get('read', read)
                progress(max(0, count - read))
                read = count
                if 'digest' in message:
                    digest = message['digest']
        finally:
            with self.lock:
                self.active.pop(key, None)
            if process.poll() is None:
                process.kill()  # Only this isolated read-only worker, never a writer.
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass  # A faulty driver must not hold up pause/checkpoint persistence.
            reader.join(timeout=.1)
