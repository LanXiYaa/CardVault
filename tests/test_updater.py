import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cardvault.updater import stage_package, launch_update, version_tuple, inspect_package

class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.source=self.root/'new.exe';self.source.write_bytes(b'installer bytes')
    def tearDown(self):self.temp.cleanup()
    def metadata(self,version='2.3.0'):return {'product':'CardVault','version':version,'description':'CardVault Setup'}
    def test_stage_copies_and_hashes_without_execution(self):
        with patch('cardvault.updater.inspect_package',return_value=self.metadata()):
            staged=stage_package(self.source,self.root)
        self.assertEqual(Path(staged['package']).parent,self.root/'update')
        self.assertEqual(Path(staged['package']).read_bytes(),self.source.read_bytes())
        self.assertEqual(staged['sha256'],hashlib.sha256(self.source.read_bytes()).hexdigest())
    def test_old_version_and_invalid_package_leave_no_update_exe(self):
        for metadata in [self.metadata('2.1.0'),self.metadata('2.2.0')]:
            with patch('cardvault.updater.inspect_package',return_value=metadata),self.assertRaises(ValueError):stage_package(self.source,self.root)
        with patch('cardvault.updater.inspect_package',side_effect=ValueError('wrong app')),self.assertRaises(ValueError):stage_package(self.source,self.root)
        self.assertFalse(list((self.root/'update').glob('*.exe')))
    def test_changed_staged_package_cannot_execute(self):
        with patch('cardvault.updater.inspect_package',return_value=self.metadata()):staged=stage_package(self.source,self.root)
        Path(staged['package']).write_bytes(b'tampered')
        with patch('cardvault.updater.subprocess.Popen') as spawn,self.assertRaises(ValueError):launch_update(staged,self.root,self.root/'state')
        spawn.assert_not_called()
    def test_helper_uses_manifest_and_waits_for_owner(self):
        with patch('cardvault.updater.inspect_package',return_value=self.metadata()):
            staged=stage_package(self.source,self.root)
            with patch('cardvault.updater.subprocess.Popen') as spawn:
                launch_update(staged,self.root,self.root/'state',parent_pid=123)
        config=json.loads(next((self.root/'update').glob('update-*.json')).read_text(encoding='utf-8'))
        self.assertEqual(config['parent_pid'],123)
        self.assertEqual(config['restart_args'],['--data-dir',str(self.root/'state')])
        script=(self.root/'update/apply-update.ps1').read_text(encoding='utf-8-sig')
        self.assertLess(script.index('WaitForExit'),script.index('$installer = Start-Process'))
        self.assertIn('/NOCLOSEAPPLICATIONS',script)
        spawn.assert_called_once()
    def test_version_order_is_numeric(self):self.assertGreater(version_tuple('2.10.0'),version_tuple('2.9.0'))
