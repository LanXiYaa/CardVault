"""Validated CardVault .upd archives; no code executes when a package is dropped."""
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path
from .runtime import resource_root
from .version import VERSION

FORMAT = 'CardVault.Update'
MAX_SIZE = 4 * 1024 ** 3
MAX_FILES = 20000


def powershell():
    return str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe')


def version_tuple(value):
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:\.\d+)?', value):
        raise ValueError('Invalid version')
    values = tuple(map(int, value.split('.')))
    return values + (0,) * (4 - len(values))


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_name(name):
    if not isinstance(name, str) or not name or len(name) > 240:
        raise ValueError('Invalid update path')
    parts = name.split('/')
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
    if any(p in ('', '.', '..') or p.endswith((' ', '.')) or p.split('.')[0].upper() in reserved or any(c in p for c in '<>:"\\|?*') or any(ord(c) < 32 for c in p) for p in parts):
        raise ValueError('Unsafe update path')
    if parts[0] not in {'CardVault.exe', '_internal', 'licenses', '发行版说明.txt', 'THIRD_PARTY_NOTICES.txt'}:
        raise ValueError('Update cannot modify user data or installer records')
    if len(parts) > 1 and parts[0] not in {'_internal', 'licenses'}:
        raise ValueError('Invalid update path')
    return name


def inspect_package(path):
    path = Path(path).resolve(strict=True)
    if path.suffix.lower() != '.upd' or not path.is_file():
        raise ValueError('Select a CardVault .upd update archive')
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            names = [e.filename for e in entries]
            if len(entries) > MAX_FILES or len(names) != len(set(n.casefold() for n in names)):
                raise ValueError('Duplicate or excessive archive entries')
            if 'manifest.json' not in names or archive.getinfo('manifest.json').file_size > 8 * 1024 ** 2:
                raise ValueError('Missing or excessive update manifest')
            manifest = json.loads(archive.read('manifest.json'))
            if not isinstance(manifest, dict) or manifest.get('format') != FORMAT or manifest.get('schema') != 1 or manifest.get('product') != 'CardVault':
                raise ValueError('Not a supported CardVault update')
            version_tuple(manifest.get('version', ''))
            files = manifest.get('files')
            if not isinstance(files, dict) or not files or 'CardVault.exe' not in files:
                raise ValueError('Missing application payload')
            if set(names) != {'manifest.json', *('payload/' + n for n in files)}:
                raise ValueError('Archive contents do not match the manifest')
            if sum(e.file_size for e in entries) > MAX_SIZE:
                raise ValueError('Update is too large')
            for name, record in files.items():
                safe_name(name)
                entry = archive.getinfo('payload/' + name)
                if entry.is_dir() or stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                    raise ValueError('Links, directories and encrypted entries are not supported')
                if not isinstance(record, dict) or type(record.get('size')) is not int or record['size'] != entry.file_size or not re.fullmatch('[0-9a-f]{64}', record.get('sha256', '')):
                    raise ValueError('Invalid file metadata')
                with archive.open(entry) as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                if digest != record['sha256']:
                    raise ValueError('Payload hash mismatch: ' + name)
            return manifest
    except (zipfile.BadZipFile, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError('Invalid CardVault update archive') from error


def build_package(application, destination, version):
    application, destination = Path(application), Path(destination)
    version_tuple(version)
    files = {}
    for path in sorted(application.rglob('*')):
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise ValueError('Links cannot be packaged')
        if path.is_file():
            name = safe_name(path.relative_to(application).as_posix())
            files[name] = {'size': path.stat().st_size, 'sha256': file_hash(path)}
    manifest = {'format': FORMAT, 'schema': 1, 'product': 'CardVault', 'version': version, 'files': files}
    temporary = destination.with_suffix('.tmp')
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False))
            for name in files:
                archive.write(application / name, 'payload/' + name)
        os.replace(temporary, destination)
        inspect_package(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def stage_package(source, root, current=VERSION):
    if Path(source).suffix.lower() != '.upd':
        raise ValueError('Select a CardVault .upd update archive')
    root = Path(root).resolve(strict=True)
    folder = root / 'update'
    if folder.is_symlink() or (hasattr(folder, 'is_junction') and folder.is_junction()) or (folder.exists() and folder.resolve().parent != root):
        raise ValueError('Update directory must stay inside the application folder')
    folder.mkdir(exist_ok=True)
    temporary = folder / (uuid.uuid4().hex + '.upd')
    try:
        shutil.copyfile(source, temporary)
        metadata = inspect_package(temporary)
        if version_tuple(metadata['version']) <= version_tuple(current):
            raise ValueError('The update version must be newer than the current version')
        digest = file_hash(temporary)
        destination = folder / ('CardVault-' + metadata['version'] + '-' + digest[:12] + '.upd')
        os.replace(temporary, destination)
        return {'package': str(destination), 'version': metadata['version'], 'sha256': digest}
    finally:
        temporary.unlink(missing_ok=True)


def launch_update(package, root, state_dir, parent_pid=None, restart_args=None):
    root = Path(root).resolve(strict=True)
    path = Path(package['package']).resolve(strict=True)
    if path.parent != root / 'update' or file_hash(path) != package['sha256']:
        raise ValueError('The staged update has changed')
    if inspect_package(path)['version'] != package['version']:
        raise ValueError('Update version mismatch')
    folder = root / 'update'
    manifest = {**package, 'root': str(root), 'parent_pid': parent_pid or os.getpid(), 'restart_args': restart_args if restart_args is not None else ['--data-dir', str(Path(state_dir).resolve())]}
    config = folder / ('update-' + uuid.uuid4().hex + '.json')
    config.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    helper = folder / ('apply-update-' + uuid.uuid4().hex + '.ps1')
    shutil.copyfile(resource_root() / 'assets/apply-update.ps1', helper)
    return subprocess.Popen([powershell(), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(helper), '-Manifest', str(config)], cwd=folder, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
