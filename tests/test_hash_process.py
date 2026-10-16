import hashlib
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from cardvault.hash_process import HashProcesses
from cardvault.io_guard import ReadCancelled


class HashProcessTests(unittest.TestCase):
    def test_hash_and_prefix(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '测试.bin'
            path.write_bytes(b'content' * 1000)
            for algorithm in ('sha256', 'md5'):
                for limit in (None, 13):
                    amounts = []
                    guard = HashProcesses()
                    self.addCleanup(guard.close)
                    result = guard.digest(path, algorithm, limit, 'job', lambda: False, amounts.append)
                    data = path.read_bytes()[:limit]
                    self.assertEqual(result, hashlib.new(algorithm, data).hexdigest())
                    self.assertEqual(sum(amounts), len(data))

    def blocked_close(self, pause):
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / 'blocked.py'
            # Exercise the real worker function, but reproduce a filesystem close
            # that never returns. No digest may be accepted before __exit__ ends.
            script.write_text("import sys, io, time\nsys.path.insert(0, " + repr(str(Path(__file__).resolve().parents[1])) + ")\nfrom cardvault.hash_worker import hash_file\nimport cardvault.hash_worker as worker, json\nworker.REQUEST_ID = json.loads(sys.stdin.readline())['id']\nclass Blocked(io.BytesIO):\n def __exit__(self, *args): time.sleep(60)\nhash_file('unused', 'sha256', opener=lambda *args, **kw: Blocked(b'abc'))\n", encoding='utf-8')
            guard = HashProcesses(timeout=2 if pause else .3)
            self.addCleanup(guard.close)
            stop = threading.Event()
            seen = threading.Event()
            timer = None
            def progress(amount):
                if amount:
                    seen.set()
                    if pause: stop.set()
            started = time.monotonic()
            with patch('cardvault.hash_process.worker_command', return_value=[sys.executable, str(script)]):
                with self.assertRaises(ReadCancelled if pause else TimeoutError):
                    guard.digest('unused', 'sha256', None, 'job', stop.is_set, progress)
            self.assertTrue(seen.is_set())
            self.assertLess(time.monotonic() - started, 3)
            self.assertEqual(guard.waiting('job'), (0, ''))
            self.assertFalse(guard.workers)
            stop.clear()
            result = guard.digest(script, 'sha256', None, 'job', stop.is_set, lambda n: None)
            self.assertEqual(result, hashlib.sha256(script.read_bytes()).hexdigest())

    def test_close_timeout_never_returns_digest(self):
        self.blocked_close(False)

    def test_pause_interrupts_close(self):
        self.blocked_close(True)

    def test_missing_file_reports_failure(self):
        with self.assertRaises(OSError):
            HashProcesses().digest('does-not-exist-93841', 'sha256', None, 'job', lambda: False, lambda n: None)

    def test_worker_reuse_error_replacement_and_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'file.bin'
            path.write_bytes(b'abc')
            guard = HashProcesses()
            self.addCleanup(guard.close)
            def digest(p):
                return guard.digest(p, 'sha256', None, 'job', lambda: False, lambda n: None)
            self.assertEqual(digest(path), hashlib.sha256(b'abc').hexdigest())
            first = next(iter(guard.workers.values()))[0]
            path.write_bytes(b'xyz')
            self.assertEqual(digest(path), hashlib.sha256(b'xyz').hexdigest())
            self.assertIs(next(iter(guard.workers.values()))[0], first)
            with self.assertRaises(OSError): digest(path.with_name('missing'))
            self.assertIsNotNone(first.poll())
            self.assertEqual(digest(path), hashlib.sha256(b'xyz').hexdigest())
            second = next(iter(guard.workers.values()))[0]
            self.assertNotEqual(first.pid, second.pid)
            guard.close_job('job')
            self.assertFalse(guard.workers)
            self.assertIsNotNone(second.poll())
