import hashlib
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from cardvault.engine import Engine, Paused, CHUNK


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root / 'CARD'
        self.source.mkdir()
        self.a, self.b = self.root / 'backup-a', self.root / 'backup-b'
        self.engine = Engine(self.root / 'state')

    def tearDown(self):
        self.engine.shutdown()
        self.tmp.cleanup()

    def file(self, name='DCIM/photo.JPG', content=b'original image data'):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def job(self, **options):
        config = {'source': str(self.source), 'targets': [str(self.a)], 'retries': 0, **options}
        result = self.engine.create(config, start=False)
        job = self.engine.jobs[result['id']]
        self.engine.stops[job['id']] = threading.Event()
        return job

    def run_job(self, **options):
        job = self.job(**options)
        self.engine.run(job)
        return job

    def test_dual_backup_preserves_source_and_reports_hashes(self):
        source = self.file()
        before = source.stat()
        self.file('clip.mp4', os.urandom(180000))
        self.file('empty.txt', b'')
        job = self.run_job(targets=[str(self.a), str(self.b)])
        self.assertEqual(job['status'], 'completed', job['message'])
        self.assertEqual(job['copied'], 3)
        self.assertEqual(source.read_bytes(), b'original image data')
        self.assertEqual(source.stat().st_mtime_ns, before.st_mtime_ns)
        for item in job['files']:
            digest = hashlib.sha256((self.source / item['relative']).read_bytes()).hexdigest()
            self.assertEqual(len(item['copies']), 2)
            for target, copy in item['copies'].items():
                self.assertEqual(hashlib.sha256((Path(target) / copy['path']).read_bytes()).hexdigest(), digest)
                self.assertEqual(copy['sha256'], digest)
        report = json.loads(self.engine.report(job['id']))
        self.assertEqual(report['status'], 'completed')
        self.assertTrue(self.engine.report(job['id'], 'csv').startswith(b'\xef\xbb\xbf'))

    def test_identical_skip_requires_hash(self):
        self.file('same.jpg', b'1234')
        self.a.mkdir()
        (self.a / 'same.jpg').write_bytes(b'1234')
        job = self.run_job(duplicate='skip')
        self.assertEqual(job['skipped'], 1)
        self.assertEqual(job['status'], 'completed')

    def test_different_same_size_file_is_not_skipped_or_overwritten(self):
        self.file('same.jpg', b'1234')
        self.a.mkdir()
        (self.a / 'same.jpg').write_bytes(b'4321')
        job = self.run_job(duplicate='skip')
        self.assertEqual(job['status'], 'partial')
        self.assertEqual((self.a / 'same.jpg').read_bytes(), b'4321')
        self.assertEqual(job['failed'], 1)

    def test_automatic_rename_preserves_existing(self):
        self.file('same.jpg', b'new')
        self.a.mkdir()
        (self.a / 'same.jpg').write_bytes(b'old')
        job = self.run_job()
        self.assertEqual(job['status'], 'completed')
        self.assertEqual((self.a / 'same.jpg').read_bytes(), b'old')
        self.assertEqual((self.a / 'same (1).jpg').read_bytes(), b'new')

    def test_overwrite_only_after_verification(self):
        self.file('same.jpg', b'new')
        self.a.mkdir()
        (self.a / 'same.jpg').write_bytes(b'old')
        original = self.engine.digest
        def bad_digest(path, job, limit=None):
            return 'wrong' if path.suffix == '.part' else original(path, job, limit)
        with patch.object(self.engine, 'digest', side_effect=bad_digest):
            job = self.run_job(duplicate='overwrite')
        self.assertEqual(job['status'], 'partial')
        self.assertEqual((self.a / 'same.jpg').read_bytes(), b'old')
        self.assertEqual((self.source / 'same.jpg').read_bytes(), b'new')

    def test_overwrite_success(self):
        self.file('same.jpg', b'new')
        self.a.mkdir()
        (self.a / 'same.jpg').write_bytes(b'old')
        job = self.run_job(duplicate='overwrite')
        self.assertEqual(job['status'], 'completed')
        self.assertEqual((self.a / 'same.jpg').read_bytes(), b'new')

    def test_rejects_overlapping_paths(self):
        for target in [self.source, self.source / 'nested', self.root]:
            with self.assertRaises(ValueError):
                self.job(targets=[str(target)])
        with self.assertRaises(ValueError):
            self.job(targets=[str(self.a), str(self.a / 'inside')])

    def test_filters_and_date_type_naming(self):
        self.file('folder/photo.JPG')
        self.file('video.mp4')
        self.file('notes.txt')
        job = self.run_job(filter='photo', organize='date_type', rename=True, project='秋日')
        self.assertEqual(job['total_files'], 1)
        self.assertEqual(job['status'], 'completed')
        self.assertIn('照片', job['files'][0]['output'])
        self.assertIn('秋日_', job['files'][0]['output'])

    def test_custom_filter(self):
        self.file('a.RAW')
        self.file('b.txt')
        job = self.run_job(filter='custom', extensions='raw, .JPG')
        self.assertEqual(job['total_files'], 1)

    def test_flattened_same_names_never_clobber(self):
        self.file('a/x.jpg', b'one')
        self.file('b/x.jpg', b'two')
        job = self.run_job(organize='type', duplicate='overwrite')
        self.assertEqual(job['status'], 'completed')
        self.assertEqual((self.a / '照片' / 'x.jpg').read_bytes(), b'one')
        self.assertEqual((self.a / '照片' / 'x (1).jpg').read_bytes(), b'two')

    def test_resume_validates_partial_prefix(self):
        data = os.urandom(CHUNK + 100)
        self.file('large.bin', data)
        job = self.job()
        self.engine.scan(job)
        self.a.mkdir()
        staging = self.a / f'.cardvault-{job["id"]}-0.part'
        staging.write_bytes(data[:100000])
        self.engine.run(job)
        self.assertEqual(job['status'], 'completed')
        self.assertEqual((self.a / 'large.bin').read_bytes(), data)
        self.assertFalse(staging.exists())

    def test_corrupt_partial_is_rebuilt(self):
        self.file('a.bin', b'correct payload')
        job = self.job()
        self.engine.scan(job)
        self.a.mkdir()
        (self.a / f'.cardvault-{job["id"]}-0.part').write_bytes(b'incorrect')
        self.engine.run(job)
        self.assertEqual(job['status'], 'completed')
        self.assertEqual((self.a / 'a.bin').read_bytes(), b'correct payload')

    def test_restart_marks_interrupted_job_paused(self):
        self.file()
        job = self.job()
        self.engine.scan(job)
        other = Engine(self.root / 'state')
        try:
            self.assertEqual(other.jobs[job['id']]['status'], 'paused')
            other.run(other.jobs[job['id']])
            self.assertEqual(other.jobs[job['id']]['status'], 'completed')
        finally:
            other.shutdown()

    def test_pause_leaves_resumeable_partial(self):
        data = os.urandom(CHUNK * 2 + 12)
        self.file('large.bin', data)
        job = self.job()
        checkpoint = self.engine.checkpoint
        def pause_after_write(current):
            if current['status'] == 'copying' and current['done_bytes'] >= CHUNK:
                raise Paused()
            return checkpoint(current)
        with patch.object(self.engine, 'checkpoint', side_effect=pause_after_write):
            self.engine.run(job)
        self.assertEqual(job['status'], 'paused')
        self.assertFalse((self.a / 'large.bin').exists())
        self.assertTrue(list(self.a.glob('*.part')))
        self.engine.run(job)
        self.assertEqual(job['status'], 'completed')
        self.assertEqual((self.a / 'large.bin').read_bytes(), data)

    def test_resume_rechecks_completed_copy(self):
        self.file('x.jpg', b'correct')
        job = self.run_job(duplicate='overwrite')
        (self.a / 'x.jpg').write_bytes(b'corrupt')
        self.engine.run(job)
        self.assertEqual(job['status'], 'completed')
        self.assertEqual((self.a / 'x.jpg').read_bytes(), b'correct')

    def test_source_changed_after_scan_fails(self):
        path = self.file('x.jpg', b'old')
        job = self.job()
        self.engine.scan(job)
        path.write_bytes(b'new content')
        self.engine.run(job)
        self.assertEqual(job['status'], 'partial')
        self.assertFalse((self.a / 'x.jpg').exists())

    def test_copy_failure_does_not_prevent_second_destination(self):
        self.file('x.jpg')
        original = self.engine.copy_one
        def fail_first(job, item, target, index):
            if target == str(self.a):
                raise OSError('simulated disconnected disk')
            return original(job, item, target, index)
        with patch.object(self.engine, 'copy_one', side_effect=fail_first):
            job = self.run_job(targets=[str(self.a), str(self.b)])
        self.assertEqual(job['status'], 'partial')
        self.assertTrue((self.b / 'x.jpg').is_file())
        self.assertEqual(len(job['files'][0]['copies']), 1)

    def test_transient_failure_retries(self):
        self.file('x.jpg')
        original = self.engine.copy_one
        count = 0
        def transient(*args):
            nonlocal count
            count += 1
            if count == 1:
                raise OSError('temporary read failure')
            return original(*args)
        with patch.object(self.engine, 'copy_one', side_effect=transient):
            job = self.run_job(retries=1)
        self.assertEqual(job['status'], 'completed')
        self.assertEqual(count, 2)

    def test_insufficient_space_does_not_copy(self):
        self.file()
        with patch('cardvault.engine.shutil.disk_usage', return_value=type('Usage', (), {'free': 0})()):
            job = self.run_job()
        self.assertEqual(job['status'], 'failed')
        self.assertIn('空间不足', job['message'])
        self.assertFalse((self.a / 'DCIM' / 'photo.JPG').exists())

    def test_csv_formula_is_escaped(self):
        self.file('=formula.jpg')
        job = self.run_job()
        report = self.engine.report(job['id'], 'csv').decode('utf-8-sig')
        self.assertIn("'=formula.jpg", report)

    def test_active_task_source_cannot_be_used_as_another_target(self):
        self.file()
        self.job()
        another_source = self.root / 'CARD2'
        another_source.mkdir()
        with self.assertRaises(ValueError):
            self.engine.create({'source': str(another_source), 'targets': [str(self.source / 'folder')]}, start=False)

    def test_three_independent_cards_can_run(self):
        jobs = []
        for index in range(3):
            source = self.root / f'card{index}'
            source.mkdir()
            (source / 'file.bin').write_bytes(os.urandom(1024 * 1024))
            result = self.engine.create({'source': str(source), 'targets': [str(self.root / f'target{index}')]})
            jobs.append(result['id'])
        # wait for current futures without cancelling the work
        self.engine.pool.shutdown(wait=True)
        for ident in jobs:
            self.assertEqual(self.engine.jobs[ident]['status'], 'completed')

    def test_permission_denied_preflight_stops_before_reading_any_source(self):
        for i in range(6):
            self.file(f'{i}.ARW', b'camera source')
        error = PermissionError(13, 'Permission denied', str(self.a / '.cardvault-writecheck-test.tmp'))
        with patch.object(self.engine, 'probe_target', side_effect=error) as probe, patch.object(self.engine, 'digest') as digest:
            job = self.run_job(retries=5)
        self.assertEqual(job['status'], 'failed')
        self.assertEqual(probe.call_count, 1)
        digest.assert_not_called()
        self.assertFalse(job['scanned'])
        self.assertIn('目标目录不可写', job['message'])
        self.assertEqual(len(list(self.source.glob('*.ARW'))), 6)

    def test_permission_lost_during_copy_is_not_retried_for_every_file(self):
        for i in range(4):
            self.file(f'{i}.JPG', b'photo')
        error = PermissionError(13, 'Permission denied', str(self.a / '.cardvault-part.tmp'))
        with patch.object(self.engine, 'copy_one', side_effect=error) as copy:
            job = self.run_job(retries=5, workers=1)
        self.assertEqual(job['status'], 'failed')
        self.assertEqual(copy.call_count, 1)
        self.assertEqual(job['failed'], 1)
        self.assertEqual(sum(f['status'] == 'pending' for f in job['files']), 3)

    def test_unwritable_first_target_keeps_second_copy(self):
        self.file('photo.JPG', b'read only source')
        original = self.engine.probe_target
        def probe(job, target):
            if target == str(self.a):
                raise PermissionError(13, 'Permission denied', str(self.a))
            return original(job, target)
        with patch.object(self.engine, 'probe_target', side_effect=probe):
            job = self.run_job(targets=[str(self.a), str(self.b)])
        self.assertEqual(job['status'], 'partial')
        self.assertEqual((self.b / 'photo.JPG').read_bytes(), b'read only source')
        self.assertEqual(job['files'][0]['copies'][str(self.b)]['sha256'], hashlib.sha256(b'read only source').hexdigest())

    def test_probe_leaves_no_temporary_files(self):
        self.file('x.jpg')
        job = self.run_job()
        self.assertEqual(job['status'], 'completed')
        self.assertEqual([p.name for p in self.a.iterdir()], ['x.jpg'])


if __name__ == '__main__':
    unittest.main()
