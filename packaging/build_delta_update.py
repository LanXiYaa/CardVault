"""Build a version-specific delta; legacy updaters do not enforce its base version."""
import argparse
import hashlib
import json
import sys
import zipfile
from release_paths import ROOT, OUTPUT
sys.path.insert(0, str(ROOT))
from cardvault.version import VERSION
from cardvault.updater import inspect_package, version_tuple


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-version', required=True)
    args = parser.parse_args()
    if version_tuple(args.base_version) >= version_tuple(VERSION):
        raise ValueError('Base version must be older than the target')
    base = OUTPUT / f'CardVault-{args.base_version}-Windows-x64'
    new = OUTPUT / f'CardVault-{VERSION}-Windows-x64'
    if not (base / 'CardVault.exe').is_file() or not (new / 'CardVault.exe').is_file():
        raise ValueError('Provide complete original base and target release folders')
    files, preserved = {}, {}
    for p in sorted(new.rglob('*')):
        if not p.is_file(): continue
        name = p.relative_to(new).as_posix()
        data = p.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        old = base / name
        if old.is_file() and hashlib.sha256(old.read_bytes()).hexdigest() == digest:
            preserved[name] = digest
        else:
            files[name] = {'size': len(data), 'sha256': digest}
    if 'CardVault.exe' not in files:
        raise ValueError('Target executable must differ from the base')
    manifest = dict(format='CardVault.Update', schema=1, product='CardVault', version=VERSION,
                    base_version=args.base_version, files=files, preserved_files=preserved)
    dest = OUTPUT / f'CardVault-{VERSION}-from-{args.base_version}-Windows-x64.upd'
    temporary = dest.with_name(dest.stem + '.tmp.upd')
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            z.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False))
            for name in files: z.write(new / name, 'payload/' + name)
        inspect_package(temporary)
        temporary.replace(dest)
    finally:
        temporary.unlink(missing_ok=True)
    print(json.dumps({'package': str(dest), 'base_version': args.base_version,
                      'bytes': dest.stat().st_size, 'changed_files': list(files)}, ensure_ascii=False))

if __name__ == '__main__':
    main()
