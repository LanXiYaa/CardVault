import json
import threading
from unittest.mock import patch
import unittest
import test_engine
from cardvault.engine import Engine, CHUNK


class ConcurrentCopyTests(unittest.TestCase):
    setUp = test_engine.BackupTests.setUp
    tearDown = test_engine.BackupTests.tearDown
    file = test_engine.BackupTests.file
    job = test_engine.BackupTests.job
    run_job = test_engine.BackupTests.run_job

    def test_windows_extended_prefix_is_same_namespace(self):
        import os
        from pathlib import Path
        from cardvault.engine import under
        if os.name != 'nt':
            self.skipTest('Windows extended paths')
        self.assertTrue(under(Path('\\\\?\\C:\\backup\\folder\\file.bin'), Path('C:/backup')))
        self.assertFalse(under(Path('\\\\?\\C:\\outside\\file.bin'), Path('C:/backup')))

    def test_resume_after_publication_before_manifest_save(self):
        self.file('photo.jpg', b'original')
        job = self.job(workers=3)
        self.engine.scan(job)
        self.engine.plan_destinations(job)
        self.a.mkdir()
        (self.a / 'photo.jpg').write_bytes(b'original')
        self.engine.run(job)
        self.assertEqual(job['status'], 'completed', job['message'])
        self.assertEqual([p.name for p in self.a.iterdir()], ['photo.jpg'])
    def test_workers_overlap_and_all_copies_match(self):
        for i in range(3):
            self.file(f'folder{i}/same.bin', bytes([i]) * (CHUNK + 9))
        barrier = threading.Barrier(3)
        threads = set()
        lock = threading.Lock()
        original = self.engine.copy_one
        def concurrent(job, item, target, index):
            if target == str(self.a):
                with lock:
                    threads.add(threading.get_ident())
                barrier.wait(timeout=5)
            return original(job, item, target, index)
        with patch.object(self.engine, 'copy_one', side_effect=concurrent):
            job = self.run_job(workers=3, organize='type', duplicate='overwrite', targets=[str(self.a), str(self.b)])
        self.assertEqual(job['status'], 'completed', job['message'])
        self.assertEqual(len(threads), 3)
        self.assertEqual(job['done_bytes'], job['total_bytes'])
        self.assertEqual(len({f['destinations'][str(self.a)]['path'].casefold() for f in job['files']}), 3)
        for item in job['files']:
            for target, copy in item['copies'].items():
                from pathlib import Path
                self.assertEqual((Path(target) / copy['path']).read_bytes(), (self.source / item['relative']).read_bytes())

    def test_parallel_pause_restart_and_progress_bounds(self):
        for i in range(6):
            self.file(f'card{i}/same.bin', bytes([i]) * (CHUNK * 2 + 5))
        job = self.job(workers=3, organize='type')
        checkpoint = self.engine.checkpoint
        samples = []
        def pause(current):
            with self.engine.lock:
                samples.append((current['done_bytes'], current['total_bytes']))
                if current['done_bytes'] >= CHUNK:
                    self.engine.stops[current['id']].set()
            checkpoint(current)
        with patch.object(self.engine, 'checkpoint', side_effect=pause):
            self.engine.run(job)
        self.assertEqual(job['status'], 'paused')
        self.assertTrue(all(0 <= done <= total for done, total in samples))
        saved = json.loads((self.engine.state_dir / (job['id'] + '.json')).read_text(encoding='utf-8'))
        self.assertEqual(saved['workers'], 3)
        other = Engine(self.engine.state_dir)
        try:
            other.run(other.jobs[job['id']])
            complete = other.jobs[job['id']]
            self.assertEqual(complete['status'], 'completed', complete['message'])
            self.assertEqual(complete['copied'], 6)
            self.assertEqual(complete['done_bytes'], complete['total_bytes'])
            self.assertFalse(list(self.a.rglob('*.part')))
        finally:
            other.shutdown()

    def test_parallel_target_failure_stops_dispatch(self):
        for i in range(20):
            self.file(f'{i}.bin')
        gate = threading.Barrier(3)
        calls = []
        def denied(job, item, target, index):
            calls.append(index)
            gate.wait(timeout=5)
            raise PermissionError(13, 'Denied', str(self.a / '.part'))
        with patch.object(self.engine, 'copy_one', side_effect=denied):
            job = self.run_job(workers=3, retries=5)
        self.assertEqual(job['status'], 'failed')
        self.assertEqual(len(calls), 3)
        self.assertEqual(job['failed'], 3)
        self.assertEqual(sum(f['status'] == 'pending' for f in job['files']), 17)

    def test_changed_completed_copy_is_renamed_safely(self):
        self.file('photo.jpg', b'original')
        job = self.run_job(workers=3)
        (self.a / 'photo.jpg').write_bytes(b'changed')
        self.engine.run(job)
        self.assertEqual(job['status'], 'completed', job['message'])
        self.assertEqual((self.a / 'photo.jpg').read_bytes(), b'changed')
        self.assertEqual((self.a / 'photo (1).jpg').read_bytes(), b'original')
