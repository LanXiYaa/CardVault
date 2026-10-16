"""Cooperative synchronous I/O cancellation with Windows synchronous-I/O cancellation.

Never terminates a thread. Drivers may still delay acknowledging cancellation.
"""
import os
import threading
import time


class ReadCancelled(Exception):
    pass


class ReadGuard:
    def __init__(self, timeout=30.0, interval=.1):
        self.timeout = timeout
        self.interval = interval
        self.lock = threading.Lock()
        self.active = {}
        self.closed = threading.Event()
        self.kernel = None
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            self.kernel.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            self.kernel.OpenThread.restype = wintypes.HANDLE
            self.kernel.CancelSynchronousIo.argtypes = [wintypes.HANDLE]
            self.kernel.CancelSynchronousIo.restype = wintypes.BOOL
            self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            self.kernel.CloseHandle.restype = wintypes.BOOL
        self.thread = threading.Thread(target=self._watch, name='cardvault-read-watch', daemon=True)
        self.thread.start()

    def _watch(self):
        while not self.closed.wait(self.interval):
            with self.lock:
                now = time.monotonic()
                for record in self.active.values():
                    stopped = record['stopped']()
                    if stopped or now - record['started'] >= self.timeout:
                        record['cancelled'] = True
                        if record['handle']:
                            self.kernel.CancelSynchronousIo(record['handle'])

    def call(self, job_id, path, stopped, operation):
        if stopped():
            raise ReadCancelled()
        handle = self.kernel.OpenThread(1, False, threading.get_native_id()) if self.kernel else None
        record = dict(job_id=job_id, path=str(path), stopped=stopped, handle=handle,
                      started=time.monotonic(), cancelled=False)
        key = threading.get_ident()
        with self.lock:
            self.active[key] = record
        try:
            try:
                result = operation()
            except OSError:
                if stopped():
                    raise ReadCancelled() from None
                if record['cancelled']:
                    raise TimeoutError('Storage I/O timed out: ' + str(path)) from None
                raise
            if stopped() or record['cancelled']:
                closer = getattr(result, 'close', None)
                if closer:
                    closer()
            if stopped():
                raise ReadCancelled()
            if record['cancelled']:
                raise TimeoutError('Storage I/O timed out: ' + str(path))
            return result
        finally:
            # Synchronize unregister/close with cancellation; the worker cannot
            # enter another filesystem operation before its record is removed.
            with self.lock:
                self.active.pop(key, None)
                if handle:
                    self.kernel.CloseHandle(handle)

    def waiting(self, job_id):
        with self.lock:
            records = [r for r in self.active.values() if r['job_id'] == job_id]
            if not records:
                return 0, ''
            oldest = min(records, key=lambda r: r['started'])
            return time.monotonic() - oldest['started'], oldest['path']

    def close(self):
        self.closed.set()
        self.thread.join(timeout=1)
