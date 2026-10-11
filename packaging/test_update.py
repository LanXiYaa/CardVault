"""Real .upd replacement and rollback checks in isolated portable copies only."""
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from unittest.mock import patch
from pathlib import Path
from release_paths import ROOT, OUTPUT, WORKSPACE
sys.path.insert(0, str(ROOT))
from cardvault.updater import stage_package, launch_update, inspect_package
from cardvault.version import VERSION

folder = WORKSPACE / '.test-data' / ('upd-test-' + str(time.time_ns()))
folder.mkdir(parents=True)
old_package = OUTPUT / 'CardVault-2.3.2-Windows-x64'
assert old_package.is_dir(), 'Provide the 2.3.2 portable folder for upgrade verification'
new_package = OUTPUT / f'CardVault-{VERSION}-from-2.3.2-Windows-x64.upd'
env = {k: v for k, v in os.environ.items() if not k.upper().startswith(('PYTHON', 'QT_', 'PYSIDE', 'VIRTUAL_ENV', '_PYI'))}
env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
env['QT_QPA_PLATFORM'] = 'offscreen'
results = []
for rollback in (False, True):
    app = folder / ('rollback-app' if rollback else 'success-app')
    shutil.copytree(old_package, app)
    state = app / 'data'
    state.mkdir()
    (state / 'keep.txt').write_text('preserve task records', encoding='utf-8')
    (app / 'personal.txt').write_text('preserve unrelated file', encoding='utf-8')
    before = hashlib.sha256((app / 'CardVault.exe').read_bytes()).hexdigest()
    package = stage_package(new_package, app, current='2.3.2')
    update_manifest = inspect_package(new_package)
    old_report = folder / ('old-rollback.json' if rollback else 'old-success.json')
    old = subprocess.Popen([str(app / 'CardVault.exe'), '--self-test', str(old_report)], env=env, cwd=app)
    report = folder / ('rollback.json' if rollback else 'success.json')
    lock = None
    if rollback:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        lock = kernel.CreateFileW(str(app / list(update_manifest['files'])[-1]), 0x80000000, 1, None, 3, 0, None)
        assert lock not in (None, ctypes.c_void_p(-1).value), ctypes.get_last_error()
    try:
        with patch('cardvault.updater.resource_root', return_value=old_package / '_internal'):
            helper = launch_update(package, app, state, parent_pid=old.pid, restart_args=['--self-test', str(report)])
        assert old.wait(timeout=60) == 0
        code = helper.wait(timeout=120)
    finally:
        if lock is not None: kernel.CloseHandle(lock)
    for _ in range(200):
        if report.exists(): break
        time.sleep(.1)
    result = json.loads(report.read_text(encoding='utf-8'))
    update = json.loads((app / 'update/update-result.json').read_text(encoding='utf-8-sig'))
    assert result['ok'], result
    assert (state / 'keep.txt').read_text(encoding='utf-8') == 'preserve task records'
    assert (app / 'personal.txt').read_text(encoding='utf-8') == 'preserve unrelated file'
    if rollback:
        assert code == 1 and update['status'] == 'failed', update
        assert 'rollback needs attention' not in update['message'], update
        assert result['version'] == '2.3.2', result
        assert hashlib.sha256((app / 'CardVault.exe').read_bytes()).hexdigest() == before
    else:
        assert code == 0 and update['status'] == 'completed', update
        assert result['version'] == VERSION and result['verified_copies'] == 9, result
        for name, digest in update_manifest.get('preserved_files', {}).items():
            assert hashlib.sha256((app / name).read_bytes()).hexdigest() == digest, name
        for name, record in update_manifest['files'].items():
            assert hashlib.sha256((app / name).read_bytes()).hexdigest() == record['sha256'], name
    results.append({'rollback': rollback, 'update': update, 'version': result['version'], 'records_preserved': True})
(WORKSPACE / 'artifacts').mkdir(exist_ok=True)
(WORKSPACE / 'artifacts/upd-integration.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(results, ensure_ascii=True))
