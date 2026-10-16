"""Read-only hash subprocess; a digest is accepted only after the file closes."""
import hashlib
import json
import sys
import time


REQUEST_ID = None

def emit(value):
    if REQUEST_ID is not None:
        value['id'] = REQUEST_ID
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
    global REQUEST_ID
    if '--serve' in sys.argv:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                REQUEST_ID = request['id']
                hash_file(request['path'], request['algorithm'], request['limit'])
            except Exception as error:
                emit({'error': str(error)})
        return 0
    try:
        path, algorithm, limit = sys.argv[-3:]
        hash_file(path, algorithm, None if limit == 'none' else int(limit))
    except Exception as error:
        emit({'error': str(error)})
        return 1
    return 0
