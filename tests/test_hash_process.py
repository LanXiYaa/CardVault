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
                    result = HashProcesses().digest(path, algorithm, limit, 'job', lambda: False, amounts.append)
                    data = path.read_bytes()[:limit]
                    self.assertEqual(result, hashlib.new(algorithm, data).hexdigest())
                    self.assertEqual(sum(amounts), len(data))

    def blocked_close(self, pause):
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / 'blocked.py'
            # Exercise the real worker function, but reproduce a filesystem close
            # that never returns. No digest may be accepted before __exit__ ends.
            script.write_text("import sys, io, time\nsys.path.insert(0, " + repr(str(Path(__file__).resolve().parents[1])) + ")\nfrom cardvault.hash_worker import hash_file\nclass Blocked(io.BytesIO):\n def __exit__(self, *args): time.sleep(60)\nhash_file('unused', 'sha256', opener=lambda *args, **kw: Blocked(b'abc'))\n", encoding='utf-8')
            guard = HashProcesses(timeout=2 if pause else .3)
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

    def test_close_timeout_never_returns_digest(self):
        self.blocked_close(False)

    def test_pause_interrupts_close(self):
        self.blocked_close(True)

    def test_missing_file_reports_failure(self):
        with self.assertRaises(OSError):
            HashProcesses().digest('does-not-exist-93841', 'sha256', None, 'job', lambda: False, lambda n: None)
