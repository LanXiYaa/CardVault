"""Check the real GUI entry point, including legacy updater hidden launch."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from release_paths import ROOT, OUTPUT, WORKSPACE
sys.path.insert(0, str(ROOT))
from cardvault.version import VERSION
exe = OUTPUT / f'CardVault-{VERSION}-Windows-x64/CardVault.exe'
state = WORKSPACE / '.test-data' / ('visible-start-' + str(time.time_ns()))
state.mkdir(parents=True)
user = ctypes.WinDLL('user32', use_last_error=True)
callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user.IsWindowVisible.argtypes = [wintypes.HWND]
user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
def window(pid):
    found = []
    @callback_type
    def visit(hwnd, _):
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        title = ctypes.create_unicode_buffer(300)
        user.GetWindowTextW(hwnd, title, 300)
        if owner.value == pid and title.value.startswith('CardVault') and user.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True
    user.EnumWindows(visit, 0)
    return found[0] if found else None

env = {k: v for k, v in os.environ.items() if not k.upper().startswith(('PYTHON', 'QT_', 'PYSIDE', 'VIRTUAL_ENV', '_PYI'))}
env['PATH'] = os.environ['SystemRoot'] + '/System32'
startup = subprocess.STARTUPINFO()
startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
startup.wShowWindow = 0  # Reproduce 2.3.1 updater Start-Process -WindowStyle Hidden.
process = subprocess.Popen([str(exe), '--data-dir', str(state)], env=env, startupinfo=startup)
try:
    deadline = time.monotonic() + 30
    hwnd = None
    while time.monotonic() < deadline:
        hwnd = window(process.pid)
        if hwnd: break
        assert process.poll() is None, 'GUI exited before showing a window'
        time.sleep(.1)
    assert hwnd, 'Legacy hidden startup never became visible'
    user.ShowWindow(hwnd, 0)
    second = subprocess.run([str(exe), '--data-dir', str(state)], env=env, timeout=15)
    assert second.returncode == 0
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not window(process.pid): time.sleep(.1)
    assert window(process.pid), 'Second launch failed to activate existing main window'
    user.PostMessageW(hwnd, 0x0010, 0, 0)
    assert process.wait(timeout=35) == 0
    result = dict(version=VERSION, legacy_hidden_start_visible=True, second_launch_activated=True, graceful_exit=True)
    (WORKSPACE / 'artifacts/visible-start.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
finally:
    if process.poll() is None:
        process.kill()
        process.wait(timeout=5)
