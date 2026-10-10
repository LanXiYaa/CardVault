from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import ctypes
from pathlib import Path
from .i18n import tr


def powershell(script, timeout=20):
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-STA', '-Command', '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; ' + script],
        capture_output=True, timeout=timeout, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )
    if result.returncode:
        raise OSError(result.stderr.decode('utf-8', errors='replace').strip() or tr('系统操作失败'))
    return result.stdout.decode('utf-8-sig', errors='replace').strip()


def drives():
    if os.name != 'nt':
        usage = shutil.disk_usage(Path.home())
        return [{'path': str(Path.home()), 'name': tr('本地目录'), 'kind': 'fixed', 'filesystem': '', 'size': usage.total, 'free': usage.free}]
    script = r"""
    $usbLetters = @{}
    Get-CimInstance Win32_DiskDrive | Where-Object { $_.InterfaceType -eq 'USB' -or $_.PNPDeviceID -like 'USB*' } | ForEach-Object {
        Get-CimAssociatedInstance -InputObject $_ -Association Win32_DiskDriveToDiskPartition | ForEach-Object {
            Get-CimAssociatedInstance -InputObject $_ -Association Win32_LogicalDiskToPartition | ForEach-Object { $usbLetters[$_.DeviceID] = $true }
        }
    }
    $result = @(Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DriveType -in @(2,3) -and $_.Size -gt 0 } | ForEach-Object {
        @{ path = $_.DeviceID + '\'; name = $(if ($_.VolumeName) { $_.VolumeName } else { '本地磁盘' });
        kind = $(if ($_.DriveType -eq 2 -or $usbLetters.ContainsKey($_.DeviceID)) { 'removable' } else { 'fixed' });
        filesystem = $_.FileSystem; size = [double]$_.Size; free = [double]$_.FreeSpace }
    })
    ConvertTo-Json -InputObject $result -Compress
    """
    try:
        value = powershell(script, timeout=8)
        found = json.loads(value or '[]')
        if found:
            found = found if isinstance(found, list) else [found]
            for device in found:
                if device['name'] == '本地磁盘':
                    device['name'] = tr('本地磁盘')
            return found
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    # CIM can be disabled by policy; Win32 still exposes mounted volume metadata.
    kernel = ctypes.windll.kernel32
    mask = kernel.GetLogicalDrives()
    result = []
    for index in range(26):
        if not mask & (1 << index):
            continue
        path = chr(65 + index) + ':\\'
        kind = kernel.GetDriveTypeW(ctypes.c_wchar_p(path))
        if kind not in (2, 3):
            continue
        available = ctypes.c_ulonglong()
        total = ctypes.c_ulonglong()
        free = ctypes.c_ulonglong()
        if not kernel.GetDiskFreeSpaceExW(ctypes.c_wchar_p(path), ctypes.byref(available), ctypes.byref(total), ctypes.byref(free)):
            continue
        name = ctypes.create_unicode_buffer(261)
        filesystem = ctypes.create_unicode_buffer(261)
        kernel.GetVolumeInformationW(ctypes.c_wchar_p(path), name, 261, None, None, None, filesystem, 261)
        result.append({'path': path, 'name': name.value or tr('本地磁盘'), 'kind': 'removable' if kind == 2 else 'fixed', 'filesystem': filesystem.value, 'size': total.value, 'free': available.value})
    return result


def eject(path):
    if os.name != 'nt' or not re.fullmatch(r'[A-Za-z]:[\\/]?', path):
        raise ValueError(tr('只能弹出 Windows 可移动磁盘'))
    letter = path[:2].upper()
    available = drives()
    if not any(d['path'][:2].upper() == letter and d['kind'] == 'removable' for d in available):
        raise ValueError(tr('未找到可安全弹出的移动磁盘'))
    # Delegate the dismount decision to Windows; never force a busy volume offline.
    powershell(f"$shell = New-Object -ComObject Shell.Application; $item = $shell.Namespace(17).ParseName('{letter}'); if ($null -eq $item) {{ throw '设备不可用' }}; $item.InvokeVerb('Eject')")
    return tr('已向 Windows 请求安全弹出；请确认系统提示或设备从列表消失后再拔出')
