import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import test_engine
from cardvault.engine import Paused

class BatchVerificationTests(unittest.TestCase):
    setUp = test_engine.BackupTests.setUp
    tearDown = test_engine.BackupTests.tearDown
    file = test_engine.BackupTests.file
    job = test_engine.BackupTests.job
    run_job = test_engine.BackupTests.run_job

    def test_all_transfers_finish_before_target_verification(self):
        for i in range(5): self.file(f'{i}.bin', bytes([i]) * 1024)
        original = self.engine.verify_one
        calls=[]
        def verify(job,item,target,index):
            with self.engine.lock:
                self.assertEqual(sum(len(f.get('staged',{})) + len(f['copies']) for f in job['files']),10)
            self.assertEqual(job['phase'],'verification')
            calls.append((index,target))
            return original(job,item,target,index)
        with patch.object(self.engine,'verify_one',side_effect=verify):
            job=self.run_job(verification='batch',targets=[str(self.a),str(self.b)])
        self.assertEqual(job['status'],'completed',job['message'])
        self.assertEqual(len(calls),10)
        self.assertEqual(job['done_bytes'],job['total_bytes'])
        self.assertFalse(any(f.get('staged') for f in job['files']))

    def test_batch_corrupt_copy_never_overwrites_existing_file(self):
        self.file('a.jpg',b'new');self.a.mkdir();(self.a/'a.jpg').write_bytes(b'old')
        original=self.engine.verify_one
        def corrupt(job,item,target,index):
            (Path(target)/item['staged'][target]['staging']).write_bytes(b'bad')
            return original(job,item,target,index)
        with patch.object(self.engine,'verify_one',side_effect=corrupt):
            job=self.run_job(verification='batch',duplicate='overwrite')
        self.assertEqual(job['status'],'partial')
        self.assertEqual(job['failed'],1)
        self.assertEqual(job['copied'],0)
        self.assertEqual((self.a/'a.jpg').read_bytes(),b'old')
        report=json.loads(self.engine.report(job['id']))
        self.assertEqual(report['summary']['success'],0)
        self.assertEqual(report['summary']['failed'],1)
        self.assertIn('失败,1',self.engine.report(job['id'],'csv').decode('utf-8-sig'))

    def test_pause_before_batch_verification_resumes_staged_files(self):
        for i in range(3):self.file(f'{i}.bin',b'test')
        with patch.object(self.engine,'verify_one',side_effect=Paused):
            job=self.run_job(verification='batch')
        self.assertEqual(job['status'],'paused')
        self.assertEqual(job['copied'],0)
        self.assertEqual(len(list(self.a.glob('*.part'))),3)
        self.assertFalse(list(self.a.glob('*.bin')))
        self.engine.run(job)
        self.assertEqual(job['status'],'completed',job['message'])
        self.assertEqual(job['copied'],3)
        self.assertFalse(list(self.a.glob('*.part')))

    def test_per_file_mode_verifies_before_next_transfer(self):
        for i in range(2):self.file(f'{i}.bin',b'test')
        original=self.engine.copy_one
        def copy(job,item,target,index):
            if index==1:self.assertEqual(job['copied'],1)
            return original(job,item,target,index)
        with patch.object(self.engine,'copy_one',side_effect=copy):
            job=self.run_job(verification='per_file',workers=1)
        self.assertEqual(job['status'],'completed')
