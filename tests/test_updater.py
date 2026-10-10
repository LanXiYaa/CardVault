import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from cardvault.updater import build_package, stage_package, launch_update, version_tuple, inspect_package, safe_name


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = self.root / 'app'
        self.app.mkdir()
        (self.app / 'CardVault.exe').write_bytes(b'MZ test application')
        (self.app / '_internal').mkdir()
        (self.app / '_internal/library.dll').write_bytes(b'library')
        self.source = build_package(self.app, self.root / 'new.upd', '9.0.0')

    def tearDown(self):
        self.temp.cleanup()

    def test_stage_copies_and_hashes_without_execution(self):
        with patch('cardvault.updater.subprocess.Popen') as spawn:
            staged = stage_package(self.source, self.root)
        spawn.assert_not_called()
        self.assertEqual(Path(staged['package']).parent, self.root / 'update')
        self.assertEqual(Path(staged['package']).read_bytes(), self.source.read_bytes())
        self.assertEqual(staged['sha256'], hashlib.sha256(self.source.read_bytes()).hexdigest())

    def test_old_version_and_exe_rejected(self):
        with self.assertRaises(ValueError):
            stage_package(self.source, self.root, current='9.0.0')
        with self.assertRaises(ValueError):
            stage_package(self.app / 'CardVault.exe', self.root)
        self.assertFalse(list((self.root / 'update').glob('*.upd')))

    def test_changed_staged_package_cannot_execute(self):
        staged = stage_package(self.source, self.root)
        Path(staged['package']).write_bytes(b'tampered')
        with patch('cardvault.updater.subprocess.Popen') as spawn, self.assertRaises(ValueError):
            launch_update(staged, self.root, self.root / 'state')
        spawn.assert_not_called()

    def test_helper_uses_manifest_and_waits_before_replacement(self):
        staged = stage_package(self.source, self.root)
        with patch('cardvault.updater.subprocess.Popen') as spawn:
            launch_update(staged, self.root, self.root / 'state', parent_pid=123)
        config = json.loads(next((self.root / 'update').glob('update-*.json')).read_text(encoding='utf-8'))
        self.assertEqual(config['parent_pid'], 123)
        self.assertEqual(config['restart_args'], ['--data-dir', str(self.root / 'state')])
        script = next((self.root / 'update').glob('apply-update-*.ps1')).read_text(encoding='utf-8-sig')
        self.assertLess(script.index('WaitForExit'), script.index('[IO.File]::Replace'))
        self.assertIn('rollback.json', script)
        spawn.assert_called_once()

    def test_unsafe_paths_and_user_data_are_rejected(self):
        for name in ('../outside', '_internal/../../x', '_internal/a:stream', '_internal/CON.txt', '_internal/evil.', '_internal/a\\b', 'data/user.json', 'update/x', '/abs', '_internal//a'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_name(name)

    def test_corruption_and_extra_entries_rejected(self):
        with zipfile.ZipFile(self.source) as z:
            original = {name: z.read(name) for name in z.namelist()}
        for extra in (False, True):
            path = self.root / ('extra.upd' if extra else 'bad.upd')
            data = dict(original)
            if extra:
                data['payload/../escaped.exe'] = b'bad'
            else:
                data['payload/CardVault.exe'] = b'wrong bytes'
            with zipfile.ZipFile(path, 'w') as z:
                for name, payload in data.items(): z.writestr(name, payload)
            with self.assertRaises(ValueError): inspect_package(path)

    def test_manifest_identity_and_symlink_rejected(self):
        with zipfile.ZipFile(self.source) as z:
            original = {name: z.read(name) for name in z.namelist()}
        for kind in ('identity', 'symlink', 'duplicate'):
            path = self.root / (kind + '.upd')
            with zipfile.ZipFile(path, 'w') as z:
                for name, payload in original.items():
                    if kind == 'identity' and name == 'manifest.json':
                        m = json.loads(payload); m['product'] = 'AnotherApp'; payload = json.dumps(m).encode()
                    if kind == 'symlink' and name == 'payload/CardVault.exe':
                        info = zipfile.ZipInfo(name); info.create_system = 3; info.external_attr = 0o120777 << 16; z.writestr(info, payload)
                    else: z.writestr(name, payload)
                if kind == 'duplicate': z.writestr('payload/cardvault.EXE', b'duplicate')
            with self.assertRaises(ValueError): inspect_package(path)

    def test_version_order_is_numeric(self):
        self.assertGreater(version_tuple('2.10.0'), version_tuple('2.9.0'))
