"""User-selected local Setup updates. Never execute arbitrary files on drop."""
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from .runtime import resource_root
from .version import VERSION


def powershell():
    return str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe')


def version_tuple(value):
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:\.\d+)?', value):
        raise ValueError('Invalid version')
    values = tuple(map(int, value.split('.')))
    return values + (0,) * (4 - len(values))


def inspect_package(path):
    path = Path(path).resolve(strict=True)
    if path.suffix.lower() != '.exe' or not path.is_file():
        raise ValueError('Select a CardVault Setup EXE')
    quoted = str(path).replace("'", "''")
    script = "[Console]::OutputEncoding=[Text.Encoding]::UTF8;$v=[Diagnostics.FileVersionInfo]::GetVersionInfo('" + quoted + "');@{product=$v.ProductName;version=$v.ProductVersion;description=$v.FileDescription}|ConvertTo-Json -Compress"
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    result = subprocess.run([powershell(), '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded], capture_output=True, timeout=20, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise ValueError('Cannot read installer metadata')
    metadata = json.loads(result.stdout.decode('utf-8-sig'))
    if metadata.get('product', '').strip() != 'CardVault' or 'setup' not in metadata.get('description', '').lower():
        raise ValueError('This file is not a CardVault Setup installer')
    metadata['version'] = metadata['version'].strip()
    version_tuple(metadata['version'])
    return metadata


def stage_package(source, root, current=VERSION):
    root = Path(root).resolve(strict=True)
    folder = root / 'update'
    if folder.is_symlink() or (folder.exists() and folder.resolve().parent != root):
        raise ValueError('Update directory must stay inside the application folder')
    folder.mkdir(exist_ok=True)
    temporary = folder / (uuid.uuid4().hex + '.exe')
    try:
        shutil.copyfile(source, temporary)
        metadata = inspect_package(temporary)
        if version_tuple(metadata['version']) <= version_tuple(current):
            raise ValueError('The installer version must be newer than the current version')
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        destination = folder / ('CardVault-' + metadata['version'] + '-Setup-' + digest[:12] + '.exe')
        os.replace(temporary, destination)
        return {'package': str(destination), 'version': metadata['version'], 'sha256': digest}
    finally:
        temporary.unlink(missing_ok=True)


def launch_update(package, root, state_dir, parent_pid=None, restart_args=None):
    root = Path(root).resolve(strict=True)
    path = Path(package['package']).resolve(strict=True)
    if path.parent != root / 'update' or hashlib.sha256(path.read_bytes()).hexdigest() != package['sha256']:
        raise ValueError('The staged installer has changed')
    if inspect_package(path)['version'] != package['version']:
        raise ValueError('Installer version mismatch')
    folder = root / 'update'
    manifest = {**package, 'root': str(root), 'parent_pid': parent_pid or os.getpid(), 'restart_args': restart_args if restart_args is not None else ['--data-dir', str(Path(state_dir).resolve())]}
    config = folder / ('update-' + uuid.uuid4().hex + '.json')
    config.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    helper = folder / 'apply-update.ps1'
    shutil.copyfile(resource_root() / 'assets/apply-update.ps1', helper)
    return subprocess.Popen([powershell(), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(helper), '-Manifest', str(config)], cwd=folder, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
