"""Local synthetic benchmarks; no camera cards or user task records are touched."""
import argparse
import copy
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
from release_paths import ROOT, WORKSPACE
sys.path.insert(0, str(ROOT))
from cardvault.engine import Engine
from cardvault.hash_process import HashProcesses

def measure(work, repetitions=5):
    times = []
    for _ in range(repetitions):
        start = time.perf_counter()
        work()
        times.append((time.perf_counter() - start) * 1000)
    return round(statistics.median(times), 3)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path)
    args = parser.parse_args()
    temp_root = WORKSPACE / '.test-data'
    temp_root.mkdir(exist_ok=True)
    result = {}
    with tempfile.TemporaryDirectory(dir=temp_root) as folder:
        base = Path(folder)
        source = base / 'source'
        source.mkdir()
        engine = Engine(base / 'state')
        try:
            job = engine.jobs[engine.create(dict(source=str(source), targets=[str(base / 'a'), str(base / 'b')]), start=False)['id']]
            for count in (5000, 20000, 50000):
                job['files'] = [dict(relative=f'DCIM/{i}.JPG', output=f'DCIM/{i}.JPG', size=1048576, mtime_ns=1234567890,
                    status='pending', copies={}, staged={}, destinations={'a': {'path': f'{i}.JPG', 'collision': False}, 'b': {'path': f'{i}.JPG', 'collision': False}}) for i in range(count)]
                engine.refresh_counts(job)
                compact = json.dumps(job, ensure_ascii=False, separators=(',', ':'))
                def old_counts():
                    files = job['files']
                    return (sum(f['status'] == 'done' for f in files), sum(f['status'] == 'skipped' for f in files),
                            sum(f['status'] == 'failed' for f in files), sum(f['size'] * len(f['copies']) for f in files),
                            sum(f['size'] * len(f.get('staged', {})) for f in files), sum(max(f['size'], 1) for f in files),
                            sum(max(f['size'], 1) * (len(f['copies']) + len(f.get('staged', {}))) for f in files),
                            sum(max(f['size'], 1) * len(f['copies']) for f in files))
                result[str(count)] = dict(old_deepcopy_ms=measure(lambda: copy.deepcopy(job)),
                    compact_snapshot_ms=measure(lambda: json.dumps(dict(job), ensure_ascii=False, separators=(',', ':'))),
                    old_chunk_summary_ms=measure(old_counts), cached_chunk_summary_ms=measure(lambda: engine.refresh_counts(job, totals=False), 50),
                    pretty_bytes=len(json.dumps(job, ensure_ascii=False, indent=2).encode()), compact_bytes=len(compact.encode()))
            file = source / 'one-mib.bin'
            file.write_bytes(b'x' * 1048576)
            entry = [str(args.exe)] if args.exe else [sys.executable, str(ROOT / 'start.py')]
            single = entry + ['--hash-worker', str(file), 'sha256', 'none']
            guard = HashProcesses()
            try:
                with patch('cardvault.hash_process.worker_command', return_value=entry + ['--hash-worker', '--serve']):
                    digest = lambda: guard.digest(file, 'sha256', None, 'bench', lambda: False, lambda n: None)
                    digest()
                    result['hash_1MiB'] = dict(single_process_ms=measure(lambda: subprocess.run(single, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True, timeout=10, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)), 20),
                        warm_worker_ms=measure(digest, 20), worker_processes=len(guard.workers), executable=str(args.exe or sys.executable))
            finally:
                guard.close()
        finally:
            engine.shutdown()
    output = WORKSPACE / 'artifacts' / ('engine-benchmark-frozen.json' if args.exe else 'engine-benchmark.json')
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
