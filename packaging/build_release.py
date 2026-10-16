"""Build an isolated onedir release and an Inno Setup installer."""
import hashlib
import importlib.metadata
import json
import os
import shutil
import struct
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

from release_paths import ROOT, OUTPUT as RELEASE, BUILD, WORKSPACE
from compact import compact_package
VERSION = '2.3.4'
PACKAGE = RELEASE / f'CardVault-{VERSION}-Windows-x64'


def icon():
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PySide6.QtCore import QByteArray, QBuffer, QIODevice
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    image = QIcon(str(ROOT / 'assets' / 'logo.svg'))
    sizes, blobs = (16, 32, 48, 64, 128, 256), []
    for size in sizes:
        array = QByteArray()
        buffer = QBuffer(array)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        assert image.pixmap(size, size).save(buffer, 'PNG')
        blobs.append(bytes(array))
    offset = 6 + 16 * len(blobs)
    data = bytearray(struct.pack('<HHH', 0, 1, len(blobs)))
    for size, blob in zip(sizes, blobs):
        data.extend(struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(blob), offset))
        offset += len(blob)
    for blob in blobs:
        data.extend(blob)
    result = BUILD / 'CardVault.ico'
    result.write_bytes(data)
    return result


def notices():
    destination = PACKAGE / 'licenses'
    destination.mkdir(exist_ok=True)
    for package in ('PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6', 'pyinstaller'):
        distribution = importlib.metadata.distribution(package)
        target = destination / package
        target.mkdir(exist_ok=True)
        (target / 'package-metadata.txt').write_text(distribution.read_text('METADATA') or '', encoding='utf-8')
        for file in distribution.files or []:
            if '/licenses/' in str(file).replace('\\', '/') or Path(file).name.upper().startswith(('COPYING', 'LICENSE')):
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    shutil.copy2(source, target / source.name)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if python_license.is_file():
        shutil.copy2(python_license, destination / 'Python-LICENSE.txt')
    for filename in ('LGPL-3.0-only.txt', 'GPL-3.0-only.txt', 'GPL-2.0-only.txt'):
        url = 'https://code.qt.io/cgit/qt/qtbase.git/plain/LICENSES/' + filename
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read()
        if b'<html' in data[:300].lower() or len(data) < 1000:
            raise RuntimeError(f'Unexpected license response for {filename}')
        (destination / filename).write_bytes(data)


def main():
    if sys.platform != 'win32' or struct.calcsize('P') != 8:
        raise SystemExit('This recipe requires 64-bit Windows Python.')
    PACKAGE.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    # Keep build caches and optional user-site discovery inside the project.
    os.environ['PYTHONUSERBASE'] = str(BUILD / 'python-user')
    os.environ['PYTHONNOUSERSITE'] = '1'
    os.environ['PYINSTALLER_CONFIG_DIR'] = str(BUILD / 'cache')
    (BUILD / 'python-user').mkdir(exist_ok=True)
    # DLL discovery must not pick up unrelated toolchains from the inherited PATH.
    windows = Path(os.environ.get('SystemRoot', 'C:/Windows'))
    os.environ['PATH'] = os.pathsep.join(map(str, (Path(sys.executable).parent, Path(sys.base_prefix), windows / 'System32', windows)))
    for key in ('QT_PLUGIN_PATH', 'QML2_IMPORT_PATH', 'PYTHONPATH', 'PYTHONHOME'):
        os.environ.pop(key, None)
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed', '--name', 'CardVault',
               '--distpath', str(BUILD / 'dist'), '--workpath', str(BUILD / 'pyinstaller'), '--specpath', str(BUILD),
               '--icon', str(icon()), '--version-file', str(ROOT / 'packaging/windows-version.txt'),
               '--add-data', f'{ROOT / "assets"};assets',
               '--hidden-import', 'PySide6.QtSvg', str(ROOT / 'start.py')]
    if '--package-only' not in sys.argv:
        subprocess.run(command, cwd=ROOT, check=True)
        shutil.copytree(BUILD / 'dist/CardVault', PACKAGE, dirs_exist_ok=True)
    # Windows 10+ supplies the Universal CRT and API sets. Older compatibility
    # copies discovered in third-party toolchains shadow the OS and break QtCore.
    removed = []
    for file in (PACKAGE / '_internal').rglob('*.dll'):
        if file.name.lower() in {'ucrtbase.dll', 'icuuc.dll', 'icuin.dll', 'icudt78.dll'} or file.name.lower().startswith(('api-ms-win-', 'ext-ms-win-')):
            removed.append(str(file.relative_to(PACKAGE)))
            file.unlink()
    (BUILD / 'excluded-system-dlls.json').write_text(json.dumps(removed, indent=2), encoding='utf-8')
    # Use the OpenSSL runtime belonging to CPython, never a PATH-discovered copy.
    for name in ('libcrypto-3.dll', 'libssl-3.dll'):
        source = Path(sys.base_prefix) / 'DLLs' / name
        if source.is_file():
            shutil.copy2(source, PACKAGE / '_internal' / name)
    for name in ('libcrypto-3-x64.dll', 'libssl-3-x64.dll'):
        (PACKAGE / '_internal' / name).unlink(missing_ok=True)
    for name in ('发行版说明.txt', 'THIRD_PARTY_NOTICES.txt'):
        shutil.copy2(ROOT / 'packaging' / name, PACKAGE / name)
    (BUILD / 'compact-report.json').write_text(json.dumps(compact_package(PACKAGE), indent=2), encoding='utf-8')
    notices()
    # Do not produce an installer if its embedded application cannot run.
    subprocess.run([sys.executable, str(ROOT / 'packaging/test_release.py')], cwd=ROOT, check=True)
    compiler = Path(os.environ.get('ISCC', str(WORKSPACE / 'build/tools/inno/ISCC.exe')))
    if not compiler.is_file():
        raise SystemExit('Inno Setup compiler missing; set ISCC to its full path.')
    subprocess.run([str(compiler), '/DOutputRoot=' + str(RELEASE), '/DBuildRoot=' + str(BUILD), str(ROOT / 'packaging/CardVault.iss')], check=True)
    setup = RELEASE / f'CardVault-{VERSION}-Setup-x64.exe'
    archive = RELEASE / f'CardVault-{VERSION}-Windows-x64.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for file in sorted(PACKAGE.rglob('*')):
            if file.is_file():
                output.write(file, Path(PACKAGE.name) / file.relative_to(PACKAGE))
    source_archive = RELEASE / f'CardVault-{VERSION}-source.zip'
    with zipfile.ZipFile(source_archive, 'w', compression=zipfile.ZIP_DEFLATED) as output:
        files = [ROOT / name for name in ('start.py', 'requirements.txt', 'README.md', 'README.en.md', 'CHANGELOG.md', '.gitignore', '.gitattributes')]
        for folder, pattern in [('cardvault', '*.py'), ('tests', '*.py'), ('packaging', '*'), ('assets', '*'), ('docs', '*.md')]:
            files.extend(p for p in (ROOT / folder).rglob(pattern) if p.is_file() and '__pycache__' not in p.parts)
        for file in files:
            if file.is_file():
                output.write(file, file.relative_to(ROOT))
    sys.path.insert(0, str(ROOT))
    from cardvault.updater import build_package
    update = build_package(PACKAGE, RELEASE / f'CardVault-{VERSION}-Windows-x64.upd', VERSION)
    checksums = {str(file.relative_to(RELEASE)): hashlib.file_digest(file.open('rb'), 'sha256').hexdigest() for file in (setup, PACKAGE / 'CardVault.exe', archive, source_archive, update)}
    (RELEASE / 'SHA256SUMS.txt').write_text(''.join(f'{digest}  {name}\n' for name, digest in checksums.items()), encoding='utf-8')
    print(json.dumps({'release': str(archive), 'exe_bytes': (PACKAGE / 'CardVault.exe').stat().st_size, 'sha256': checksums}, indent=2), flush=True)


if __name__ == '__main__':
    main()
