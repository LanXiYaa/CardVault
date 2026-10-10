"""Read-only hash subprocess; a digest is accepted only after the file closes."""
import hashlib
import json
import sys
import time


def emit(value):
    print(json.dumps(value), flush=True)


def hash_file(path, algorithm, limit=None, opener=open):
    emit({'phase': 'opening'})
    hasher = hashlib.new(algorithm)
    read = 0
    last = 0
    with opener(path, 'rb', buffering=0) as stream:
        while limit is None or read < limit:
            chunk = stream.read(min(1024 * 1024, limit - read) if limit is not None else 1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
            read += len(chunk)
            now = time.monotonic()
            if now - last >= .1:
                emit({'read': read, 'phase': 'reading'})
                last = now
        emit({'read': read, 'phase': 'closing'})
    emit({'digest': hasher.hexdigest(), 'read': read})


def main():
    try:
        path, algorithm, limit = sys.argv[-3:]
        hash_file(path, algorithm, None if limit == 'none' else int(limit))
    except Exception as error:
        emit({'error': str(error)})
        return 1
    return 0
