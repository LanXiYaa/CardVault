import os
import json
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import test_engine
from cardvault.engine import Paused
from cardvault.io_guard import ReadGuard, ReadCancelled


class PauseRegressionTests(unittest.TestCase):
    setUp = test_engine.BackupTests.setUp
    tearDown = test_engine.BackupTests.tearDown
    file = test_engine.BackupTests.file
    job = test_engine.BackupTests.job
    run_job = test_engine.BackupTests.run_job

    def test_slow_state_flush_does_not_block_snapshot_or_pause(self):
        self.file()
        job = self.job()
        entered, release, responsive = threading.Event(), threading.Event(), threading.Event()
        def slow_save(path, value):
            entered.set()
            release.wait(5)
        def ui():
            self.engine.list_jobs()
            self.engine.pause(job['id'])
            responsive.set()
        with patch('cardvault.engine.atomic_json', side_effect=slow_save):
            writer = threading.Thread(target=lambda: self.engine.save(job, force=True))
            writer.start()
            try:
                self.assertTrue(entered.wait(2))
                reader = threading.Thread(target=ui)
                reader.start()
                self.assertTrue(responsive.wait(1), 'Disk flush blocked UI/pause')
            finally:
                release.set()
                writer.join(3)
                if 'reader' in locals(): reader.join(3)
        self.assertTrue(self.engine.stops[job['id']].is_set())

    def test_batch_verification_is_serial_even_with_eight_copy_workers(self):
        for i in range(24): self.file(f'{i}.bin', b'x' * 1000)
        original = self.engine.verify_one
        guard = threading.Lock()
        active = maximum = 0
        def verify(*args):
            nonlocal active, maximum
            with guard:
                active += 1
                maximum = max(maximum, active)
            try:
                time.sleep(.002)
                return original(*args)
            finally:
                with guard: active -= 1
        with patch.object(self.engine, 'verify_one', side_effect=verify):
            job = self.run_job(verification='batch', workers=8)
        self.assertEqual(job['status'], 'completed', job['message'])
        self.assertEqual(maximum, 1)

    def test_resume_reuses_staged_data_without_rehashing_in_transfer_phase(self):
        for i in range(5): self.file(f'{i}.bin', b'x' * 4096)
        with patch.object(self.engine, 'verify_one', side_effect=Paused):
            job = self.run_job(verification='batch', workers=8)
        self.assertEqual(job['status'], 'paused')
        original = self.engine.digest
        def digest(path, current, limit=None):
            self.assertEqual(current['phase'], 'verification')
            return original(path, current, limit)
        with patch.object(self.engine, 'digest', side_effect=digest):
            self.engine.run(job)
        self.assertEqual(job['status'], 'completed', job['message'])

    def test_corrupt_staged_copy_is_repaired_on_resume(self):
        self.file('file.bin', b'original')
        original = self.engine.verify_one
        def corrupt(job, item, target, index):
            (Path(target) / item['staged'][target]['staging']).write_bytes(b'corrupt!')
            return original(job, item, target, index)
        with patch.object(self.engine, 'verify_one', side_effect=corrupt):
            job = self.run_job(verification='batch')
        self.assertEqual(job['status'], 'partial')
        self.engine.run(job)
        self.assertEqual(job['status'], 'completed', job['message'])
        self.assertEqual((self.a / 'file.bin').read_bytes(), b'original')

    def test_hash_timeout_stops_task_and_preserves_staged_copy(self):
        from cardvault.hash_process import HashTimeout
        self.file('file.bin', b'original')
        original = self.engine.digest
        def digest(path, job, limit=None):
            if job.get('phase') == 'verification':
                raise HashTimeout('storage close timed out')
            return original(path, job, limit)
        with patch.object(self.engine, 'digest', side_effect=digest):
            job = self.run_job(verification='batch')
        self.assertEqual(job['status'], 'failed')
        self.assertEqual(job['copied'], 0)
        item = job['files'][0]
        self.assertTrue(item['staged'])
        self.assertFalse(next(iter(item['staged'].values())).get('verify_failed'))
        self.assertFalse((self.a / 'file.bin').exists())
        self.engine.run(job)
        self.assertEqual(job['status'], 'completed', job['message'])

    def test_paused_status_is_published_only_after_durable_save(self):
        self.file()
        entered, release = threading.Event(), threading.Event()
        from cardvault.engine import atomic_json
        def save(path, value):
            if value['status'] == 'paused':
                entered.set()
                release.wait(4)
            atomic_json(path, value)
        job = self.job(verification='batch')
        with patch.object(self.engine, 'verify_one', side_effect=Paused), patch('cardvault.engine.atomic_json', side_effect=save):
            thread = threading.Thread(target=lambda: self.engine.run(job))
            thread.start()
            try:
                self.assertTrue(entered.wait(3))
                self.assertEqual(self.engine.snapshot(job)['status'], 'pausing')
            finally:
                release.set()
                thread.join(4)
        self.assertEqual(job['status'], 'paused')
        saved = json.loads((self.engine.state_dir / (job['id'] + '.json')).read_text(encoding='utf-8'))
        self.assertEqual(saved['status'], 'paused')


@unittest.skipUnless(os.name == 'nt', 'Windows synchronous I/O cancellation')
class WindowsReadCancellationTests(unittest.TestCase):
    def blocked_pipe(self, timeout, pause):
        guard = ReadGuard(timeout=timeout, interval=.01)
        read_fd, write_fd = os.pipe()
        stream = os.fdopen(read_fd, 'rb', buffering=0)
        started, done, stop = threading.Event(), threading.Event(), threading.Event()
        errors = []
        def worker():
            try:
                def read():
                    started.set()
                    return stream.read(1)
                guard.call('job', 'blocked-pipe', stop.is_set, read)
            except BaseException as error: errors.append(error)
            finally: done.set()
        thread = threading.Thread(target=worker)
        thread.start()
        try:
            self.assertTrue(started.wait(2))
            if pause: stop.set()
            self.assertTrue(done.wait(3), 'Blocking read was not cancelled')
            self.assertIsInstance(errors[0], ReadCancelled if pause else TimeoutError)
        finally:
            if not done.is_set(): os.write(write_fd, b'x')
            thread.join(3)
            stream.close()
            os.close(write_fd)
            guard.close()

    def test_pause_cancels_real_pending_windows_read(self):
        self.blocked_pipe(30, True)

    def test_timeout_cancels_real_pending_windows_read(self):
        self.blocked_pipe(.1, False)
