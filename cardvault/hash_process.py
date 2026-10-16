"""Bounded, cancellable hashing including potentially blocking handle cleanup."""
import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from .io_guard import ReadCancelled


class HashTimeout(TimeoutError):
    """Stop a task on an unresponsive device, retaining staged copies."""


def worker_command(path, algorithm, limit):
    entry = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).resolve().parents[1] / 'start.py')]
    return entry + ['--hash-worker', '--serve']


class HashProcesses:
    def __init__(self, timeout=30):
        self.timeout = timeout
        self.lock = threading.Lock()
        self.active = {}
        self.workers = {}

    def waiting(self, job_id):
        with self.lock:
            records = [v for v in self.active.values() if v['job'] == job_id]
            if not records:
                return 0, ''
            record = min(records, key=lambda v: v['heartbeat'])
            return time.monotonic() - record['heartbeat'], record['path'] + ' [' + record['phase'] + ']'

    def _spawn(self, path, algorithm, limit):
        env = os.environ.copy()
        env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
        process = subprocess.Popen(worker_command(path, algorithm, limit), stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        messages = queue.Queue()
        requests = queue.Queue()
        def send():
            try:
                while True:
                    request = requests.get()
                    if request is None:
                        break
                    process.stdin.write(request)
                    process.stdin.flush()
            except Exception as error:
                messages.put({'error': str(error)})
            finally:
                process.stdin.close()
        writer = threading.Thread(target=send, daemon=True, name='hash-requests')
        writer.start()
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
        return process, messages, reader, requests, writer

    @staticmethod
    def _dispose(worker):
        process, _, reader, requests, writer = worker
        if process.poll() is None:
            process.kill()  # Only a read-only worker; never a writer.
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        requests.put(None)
        writer.join(timeout=.1)
        reader.join(timeout=.1)

    def close_job(self, job_id):
        # Called after all of this job's copy threads have stopped.
        with self.lock:
            keys = [key for key in self.workers if key[0] == job_id]
            workers = [self.workers.pop(key) for key in keys]
        for worker in workers:
            self._dispose(worker)

    def close(self):
        with self.lock:
            workers = list(self.workers.values())
            self.workers.clear()
        for worker in workers:
            self._dispose(worker)

    def digest(self, path, algorithm, limit, job_id, stopped, progress):
        if stopped():
            raise ReadCancelled()
        key = (job_id, threading.current_thread())
        with self.lock:
            worker = self.workers.get(key)
        if worker is None or worker[0].poll() is not None:
            if worker is not None:
                self._dispose(worker)
            worker = self._spawn(path, algorithm, limit)
            with self.lock:
                self.workers[key] = worker
        process, messages, reader, requests, writer = worker
        request_id = uuid.uuid4().hex
        record = dict(job=job_id, path=str(path), phase='starting', heartbeat=time.monotonic())
        with self.lock:
            self.active[key] = record
        read = 0
        healthy = False
        try:
            request = dict(id=request_id, path=str(path), algorithm=algorithm, limit=limit)
            requests.put((json.dumps(request) + '\n').encode('utf-8'))
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
                    raise OSError('Hash worker exited without a verified result: ' + str(path))
                if message.get('id') != request_id:
                    raise OSError('Invalid hash worker response')
                with self.lock:
                    record['heartbeat'] = time.monotonic()
                    record['phase'] = message.get('phase', record['phase'])
                if 'error' in message:
                    raise OSError(message['error'])
                count = message.get('read', read)
                progress(max(0, count - read))
                read = count
                if 'digest' in message:
                    if stopped():
                        raise ReadCancelled()
                    healthy = True
                    return message['digest']  # Worker emits this only after the handle closes.
        finally:
            with self.lock:
                self.active.pop(key, None)
                if not healthy:
                    self.workers.pop(key, None)
            if not healthy:
                self._dispose(worker)
