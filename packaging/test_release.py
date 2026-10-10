"""Execute the distributed EXE with no Python/Qt installation on its search path."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
package = ROOT / 'release/CardVault-2.3.2-Windows-x64'
exe = package / 'CardVault.exe'
assert not (package / '_internal/icuuc.dll').exists(), 'Foreign ICU DLL breaks QtCore imports'
assert not list((package / '_internal').glob('api-ms-win-*.dll')), 'Do not shadow Windows API sets'
test_dir = ROOT / '.test-data' / ('独立发行验证-' + str(time.time_ns()))
test_dir.mkdir(parents=True)
copied = test_dir / 'CardVault.exe'
env = {key: value for key, value in os.environ.items() if not key.upper().startswith(('PYTHON', 'PYSIDE', 'QT_', 'VIRTUAL_ENV', 'PYINSTALLER', '_PYI'))}
windows = Path(os.environ.get('SystemRoot', 'C:/Windows'))
env['PATH'] = os.pathsep.join(map(str, (windows / 'System32', windows, windows / 'System32/WindowsPowerShell/v1.0')))
env['LOCALAPPDATA'] = str(test_dir / 'local-user')
(test_dir / 'local-user').mkdir()
env['QT_QPA_PLATFORM'] = 'windows' if '--native' in sys.argv else 'offscreen'
env['TMP'] = env['TEMP'] = str(test_dir / 'temporary')
(test_dir / 'temporary').mkdir()
if '--installer' in sys.argv:
    setup = ROOT / 'release/CardVault-2.3.2-Setup-x64.exe'
    installed = subprocess.run([str(setup), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOICONS', '/TASKS=', '/DIR=' + str(test_dir), '/LOG=' + str(test_dir / 'install.log')], env=env, timeout=120)
    assert installed.returncode == 0, f'Installer failed: {installed.returncode}'
else:
    shutil.copytree(package, test_dir, dirs_exist_ok=True)
report = test_dir / 'standalone-test.json'
start = time.monotonic()
process = subprocess.run([str(copied), '--self-test', str(report)], cwd=test_dir, env=env, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=120)
assert process.returncode == 0, f'EXE returned {process.returncode}; inspect {report}'
result = json.loads(report.read_text(encoding='utf-8'))
assert result['ok'] and result['frozen'], result
assert result['verified_copies'] == 9
assert result['workers'] == 3
assert len(result['languages']) == 4
assert all(str(test_dir).lower() in path.lower() for path in result['module_search_paths']), result['module_search_paths']
assert Path(result['data_dir']) == test_dir / 'local-user/CardVault'
result.update(elapsed_seconds=round(time.monotonic() - start, 2), stripped_path=env['PATH'], copied_release_directory=True, platform=env['QT_QPA_PLATFORM'], exe_sha256=hashlib.sha256(exe.read_bytes()).hexdigest())
artifact = ROOT / ('artifacts/release-native-test' if '--native' in sys.argv else 'artifacts/release-standalone-test')
if '--installer' in sys.argv:
    sentinel = Path(result['data_dir']) / 'preserve-record.txt'
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text('Keep task history after uninstall', encoding='utf-8')
    uninstalled = subprocess.run([str(test_dir / 'unins000.exe'), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/LOG=' + str(test_dir / 'uninstall.log')], env=env, timeout=120)
    assert uninstalled.returncode == 0
    for _ in range(50):
        if not copied.exists():
            break
        time.sleep(0.1)
    assert not copied.exists(), 'Uninstaller did not remove the application'
    assert sentinel.is_file(), 'Uninstall removed task history'
    result.update(installer_passed=True, uninstall_passed=True, history_preserved=True)
    artifact = ROOT / 'artifacts/release-installer-test'
artifact.parent.mkdir(parents=True, exist_ok=True)
artifact.with_suffix('.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
shutil.copy2(report.with_suffix('.png'), artifact.with_suffix('.png'))
print(json.dumps(result, ensure_ascii=True, indent=2))
