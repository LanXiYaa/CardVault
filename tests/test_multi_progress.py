import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch
import test_engine
from cardvault.engine import Paused


class MultiProgressTests(unittest.TestCase):
    setUp = test_engine.BackupTests.setUp
    tearDown = test_engine.BackupTests.tearDown
    file = test_engine.BackupTests.file
    job = test_engine.BackupTests.job
    run_job = test_engine.BackupTests.run_job

    def test_md5_three_targets_and_empty_files(self):
        self.file('photo.bin', b'new content')
        self.file('empty.bin', b'')
        job = self.run_job(targets=[str(self.a), str(self.b), str(self.root / 'c')], hash_algorithm='md5', verification='batch')
        self.assertEqual(job['status'], 'completed', job['message'])
        self.assertEqual(job['copy_progress'], job['progress_total'])
        self.assertEqual(job['verify_progress'], job['progress_total'])
        for item in job['files']:
            self.assertEqual(len(item['copies']), 3)
            for target, copy in item['copies'].items():
                self.assertEqual(copy['md5'], hashlib.md5((self.source / item['relative']).read_bytes()).hexdigest())
                self.assertNotIn('sha256', copy)
                self.assertEqual((Path(target) / copy['path']).read_bytes(), (self.source / item['relative']).read_bytes())
        csv = self.engine.report(job['id'], 'csv').decode('utf-8-sig')
        self.assertIn('MD5', csv)
        self.assertNotIn('SHA-256', csv)

    def test_batch_copy_100_before_verify_and_pause_resume(self):
        self.file('large.bin', b'x' * 10000)
        with patch.object(self.engine, 'verify_one', side_effect=Paused):
            job = self.run_job(verification='batch', hash_algorithm='md5')
        self.assertEqual(job['status'], 'paused')
        self.assertEqual(job['copy_progress'], job['progress_total'])
        self.assertEqual(job['verify_progress'], 0)
        self.engine.run(job)
        self.assertEqual(job['status'], 'completed', job['message'])
        self.assertEqual(job['verify_progress'], job['progress_total'])

    def test_verification_progress_advances_during_large_file(self):
        import cardvault.engine as module
        self.file('large.bin', b'x' * 100)
        readings = []
        original = self.engine.refresh_counts
        def record(job):
            original(job)
            if job.get('phase') == 'verification': readings.append(job.get('verify_progress', 0))
        with patch.object(module, 'CHUNK', 10), patch.object(self.engine, 'refresh_counts', side_effect=record):
            job = self.run_job(verification='batch')
        self.assertEqual(job['status'], 'completed')
        self.assertTrue(any(0 < n < 100 for n in readings), readings)
        self.assertTrue(all(0 <= n <= 100 for n in readings))

    def test_failed_md5_verification_not_counted_as_verified(self):
        self.file('file.bin', b'original')
        original = self.engine.verify_one
        def corrupt(job, item, target, index):
            (Path(target) / item['staged'][target]['staging']).write_bytes(b'corrupt!')
            return original(job, item, target, index)
        with patch.object(self.engine, 'verify_one', side_effect=corrupt):
            job = self.run_job(verification='batch', hash_algorithm='md5')
        self.assertEqual(job['status'], 'partial')
        self.assertEqual(job['copy_progress'], job['progress_total'])
        self.assertEqual(job['verify_progress'], 0)
        self.assertFalse((self.a / 'file.bin').exists())

    def test_all_pairs_of_destinations_checked(self):
        self.file()
        for third in (self.b, self.b / 'nested'):
            with self.assertRaises(ValueError):
                self.job(targets=[str(self.a), str(self.b), str(third)])
        with self.assertRaises(ValueError): self.job(hash_algorithm='sha1')
