from __future__ import annotations
from .i18n import tr
import csv
import copy
from .io_guard import ReadGuard, ReadCancelled
from .hash_process import HashProcesses, HashTimeout
import hashlib
import io
import json
import os
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime
from pathlib import Path
PHOTO = {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.raw', '.cr2', '.cr3', '.nef', '.arw', '.dng', '.raf', '.orf', '.rw2', '.tif', '.tiff', '.webp'}
VIDEO = {'.mp4', '.mov', '.mxf', '.avi', '.mkv', '.mts', '.m2ts', '.r3d', '.braw', '.wmv'}
CHUNK = 4 * 1024 * 1024

class Paused(Exception):
    pass

class TargetUnavailable(OSError):
    """A destination-wide failure; retrying every source file cannot repair it."""

def target_error(target, error):
    if isinstance(error, PermissionError) or getattr(error, 'winerror', None) in {5, 19}:
        reason = tr('目标目录不可写。请检查磁盘写保护和文件夹权限，确认当前用户可以在该目录新建文件。')
    else:
        reason = tr('目标存储设备不可用，请检查连接、剩余空间和文件系统。')
    return tr('{v0}\n目标：{v1}\n原始错误：{v2}', v0=reason, v1=target, v2=error)

def normalized_path(path: Path) -> Path:
    # Windows may retain the extended-path prefix when resolve() races with a
    # directory being created. Compare equivalent paths in one namespace.
    text = str(path)
    if os.name == 'nt' and text.startswith('\\\\?\\'):
        text = ('\\\\' + text[8:]) if text[4:8].upper() == 'UNC\\' else text[4:]
    return Path(text)


def under(path: Path, parent: Path) -> bool:
    path, parent = normalized_path(path), normalized_path(parent)
    return path == parent or parent in path.parents

def linklike(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction())

def clean_name(value: str) -> str:
    value = ''.join(('_' if c in '<>:"/\\|?*' or ord(c) < 32 else c for c in value)).strip(' .')[:80]
    if value.upper().split('.')[0] in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        value = '_' + value
    return value or tr('未命名')

def atomic_json(path: Path, data):
    temp = path.with_suffix('.tmp')
    with temp.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)

class Engine:

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir.resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.persistence_lock = threading.Lock()
        self.log_lock = threading.Lock()
        self.destination_lock = threading.Lock()
        self.last_saved = {}
        self.io_guard = ReadGuard()
        self.hash_processes = HashProcesses()
        self.jobs = {}
        self.stops = {}
        self.transfers = {}
        self.verifications = {}
        self.verify_threads = {}
        self.aborts = {}
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix='backup')
        for file in self.state_dir.glob('*.json'):
            try:
                job = json.loads(file.read_text(encoding='utf-8'))
                if job['status'] in {'queued', 'checking', 'scanning', 'copying', 'verifying', 'pausing'}:
                    job['status'] = 'paused'
                    job['message'] = tr('上次任务未完成，可以继续备份')
                job['speed'] = 0
                self.jobs[job['id']] = job
            except (ValueError, KeyError, OSError):
                continue

    def save(self, job, force=False, paused=False):
        # Always called without self.lock. Disk flushes must not block snapshots
        # or a pause request. One serializer also prevents stale saves overtaking.
        with self.persistence_lock:
            now = time.monotonic()
            if not force and now - self.last_saved.get(job['id'], 0) < .5:
                return
            with self.lock:
                job['updated'] = datetime.now().isoformat(timespec='seconds')
                saved = copy.deepcopy(job)
                if paused:
                    saved.update(status='paused', message=tr('进度已保存，重新连接存储设备后可继续'))
            atomic_json(self.state_dir / (job['id'] + '.json'), saved)
            self.last_saved[job['id']] = time.monotonic()
            if paused:
                with self.lock:
                    job.update(status=saved['status'], message=saved['message'])

    def log(self, job, level, message):
        with self.lock:
            event = {'time': datetime.now().isoformat(timespec='seconds'), 'level': level, 'message': message}
            job['events'].append(event)
            job['events'] = job['events'][-100:]
        with self.log_lock:
            with (self.state_dir / (job['id'] + '.jsonl')).open('a', encoding='utf-8') as f:
                f.write(json.dumps(event, ensure_ascii=False) + '\n')

    def snapshot(self, job):
        with self.lock:
            public = {k: v for k, v in job.items() if k != 'files'}
            public['events'] = list(job['events'])
            public['io_wait_seconds'], public['io_wait_path'] = max(self.io_guard.waiting(job['id']), self.hash_processes.waiting(job['id']), key=lambda value: value[0])
            public['errors'] = [{'path': f['relative'], 'error': f.get('error', '')} for f in job['files'] if f['status'] == 'failed']
            return json.loads(json.dumps(public))

    def list_jobs(self):
        with self.lock:
            return [self.snapshot(j) for j in sorted(self.jobs.values(), key=lambda j: j['created'], reverse=True)]

    def create(self, data, start=True):
        source = Path(data.get('source', '')).expanduser().resolve(strict=True)
        if not source.is_dir():
            raise ValueError(tr('请选择有效的源目录或存储卡'))
        raw_targets = data.get('targets', [])
        if not isinstance(raw_targets, list) or not raw_targets or any((not str(p).strip() for p in raw_targets)):
            raise ValueError(tr('请至少选择一个备份目录'))
        targets = [Path(p).expanduser().resolve() for p in raw_targets]
        for target in targets:
            if under(target, source) or under(source, target):
                raise ValueError(tr('源目录和备份目录不能相同或相互包含'))
            if under(self.state_dir, source) or under(self.state_dir, target) or under(target, self.state_dir):
                raise ValueError(tr('备份路径不能包含应用的任务数据目录'))
        if any(under(a, b) or under(b, a) for i, a in enumerate(targets) for b in targets[i + 1:]):
            raise ValueError(tr('备份目录不能重复或相互包含'))
        mode = data.get('filter', 'all')
        duplicate = data.get('duplicate', 'rename')
        organize = data.get('organize', 'original')
        if mode not in {'all', 'photo', 'video', 'custom'} or duplicate not in {'rename', 'skip', 'overwrite'} or organize not in {'original', 'date', 'type', 'date_type', 'device'}:
            raise ValueError(tr('无效的备份选项'))
        if data.get('verification', 'per_file') not in {'per_file', 'batch'}:
            raise ValueError(tr('无效的备份选项'))
        if data.get('hash_algorithm', 'sha256') not in {'sha256', 'md5'}:
            raise ValueError(tr('无效的备份选项'))
        extensions = {'.' + s.strip().lower().lstrip('.') for s in str(data.get('extensions', '')).replace(',', ' ').replace('，', ' ').split()}
        if mode == 'custom' and (not extensions):
            raise ValueError(tr('请填写自定义扩展名，例如 jpg, mp4'))
        project = clean_name(str(data.get('project', '')).strip()) if data.get('project', '').strip() else ''
        job = {'id': uuid.uuid4().hex, 'name': project or source.name or str(source), 'source': str(source), 'targets': [str(t) for t in targets], 'filter': mode, 'extensions': sorted(extensions), 'duplicate': duplicate, 'organize': organize, 'rename': bool(data.get('rename', False)), 'project': project, 'retries': min(5, max(0, int(data.get('retries', 2)))), 'workers': min(8, max(1, int(data.get('workers', 3)))), 'verification': data.get('verification', 'per_file'), 'hash_algorithm': data.get('hash_algorithm', 'sha256'), 'status': 'queued', 'created': datetime.now().isoformat(timespec='seconds'), 'files': [], 'events': [], 'scanned': False, 'total_files': 0, 'total_bytes': 0, 'done_bytes': 0, 'copied': 0, 'skipped': 0, 'failed': 0, 'speed': 0, 'current': '', 'message': tr('等待开始'), 'scan_warnings': 0}
        with self.lock:
            for other in self.jobs.values():
                if other['status'] in {'queued', 'checking', 'scanning', 'copying', 'verifying', 'pausing'}:
                    if any((under(a, Path(b)) or under(Path(b), a) for a in targets for b in other['targets'])):
                        raise ValueError(tr('该目标目录已有任务正在写入，请使用独立子目录或等待完成'))
                    if any((under(a, Path(other['source'])) or under(Path(other['source']), a) for a in targets)) or any((under(source, Path(b)) or under(Path(b), source) for b in other['targets'])):
                        raise ValueError(tr('当前路径与其他运行中任务的源目录交叉，已阻止写入'))
            self.jobs[job['id']] = job
        self.save(job, force=True)
        if start:
            self.submit(job)
        return self.snapshot(job)

    def submit(self, job):
        self.stops[job['id']] = threading.Event()
        self.pool.submit(self.run, job)

    def pause(self, ident):
        event = self.stops.get(ident)
        if event is not None:
            event.set()
        with self.lock:
            job = self.jobs[ident]
            if job['status'] in {'queued', 'checking', 'scanning', 'copying', 'verifying'}:
                if event is not None:
                    event.set()
                job['status'] = 'pausing'
                job['message'] = tr('正在保存进度…')
            return self.snapshot(job)

    def resume(self, ident):
        with self.lock:
            job = self.jobs[ident]
            if job['status'] not in {'paused', 'failed', 'partial'}:
                raise ValueError(tr('当前任务不能恢复'))
            for other in self.jobs.values():
                if other['id'] != ident and other['status'] in {'queued', 'checking', 'scanning', 'copying', 'verifying', 'pausing'}:
                    if any((under(Path(a), Path(b)) or under(Path(b), Path(a)) for a in job['targets'] for b in other['targets'])):
                        raise ValueError(tr('目标目录正在被其他任务使用'))
                    if any((under(Path(a), Path(other['source'])) or under(Path(other['source']), Path(a)) for a in job['targets'])) or any((under(Path(job['source']), Path(b)) or under(Path(b), Path(job['source'])) for b in other['targets'])):
                        raise ValueError(tr('路径与其他运行中任务的源目录交叉，请等待任务结束'))
            for item in job['files']:
                if item['status'] == 'failed':
                    item['status'] = 'pending'
                    item.pop('error', None)
            job['status'] = 'queued'
            job['speed'] = 0
        self.save(job, force=True)
        self.submit(job)
        return self.snapshot(job)

    def checkpoint(self, job):
        if self.stops.get(job['id'], threading.Event()).is_set() or self.aborts.get(job['id'], threading.Event()).is_set():
            raise Paused()

    def scan(self, job):
        source = Path(job['source'])
        if not source.is_dir():
            raise OSError(tr('源存储卡已断开，请重新连接后继续'))
        job.update(status='scanning', message=tr('正在扫描文件…'), files=[], scan_warnings=0)
        allowed = PHOTO if job['filter'] == 'photo' else VIDEO if job['filter'] == 'video' else set(job['extensions'])
        planned = []

        def scan_error(error):
            raise error
        for root, dirs, names in os.walk(source, followlinks=False, onerror=scan_error):
            self.checkpoint(job)
            kept = []
            for d in sorted(dirs):
                p = Path(root) / d
                if linklike(p):
                    job['scan_warnings'] += 1
                    self.log(job, 'warning', tr('未跟随目录链接：{v0}', v0=p.relative_to(source)))
                elif d not in {'System Volume Information', '$RECYCLE.BIN'}:
                    kept.append(d)
            dirs[:] = kept
            for name in sorted(names):
                self.checkpoint(job)
                path = Path(root) / name
                if linklike(path):
                    job['scan_warnings'] += 1
                    self.log(job, 'warning', tr('未跟随文件链接：{v0}', v0=path.relative_to(source)))
                    continue
                if job['filter'] != 'all' and path.suffix.lower() not in allowed:
                    continue
                stat = path.stat()
                relative = path.relative_to(source)
                stamp = datetime.fromtimestamp(stat.st_mtime)
                category = tr('照片') if path.suffix.lower() in PHOTO else tr('视频') if path.suffix.lower() in VIDEO else tr('其他')
                folder = {'original': relative.parent, 'date': Path(stamp.strftime('%Y-%m-%d')), 'type': Path(category), 'date_type': Path(stamp.strftime('%Y-%m-%d')) / category, 'device': Path(clean_name(source.name or source.drive)) / relative.parent}[job['organize']]
                if job['rename']:
                    name = f"{job['project'] or tr('素材')}_{stamp:%Y%m%d}_{len(planned) + 1:04d}{path.suffix}"
                output = folder / name
                planned.append({'relative': str(relative), 'output': str(output), 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns, 'status': 'pending', 'copies': {}})
                job['total_files'] = len(planned)
        job['files'] = planned
        job['total_files'] = len(planned)
        job['total_bytes'] = sum((f['size'] for f in planned)) * len(job['targets'])
        job['scanned'] = True
        self.save(job, force=True)
        self.log(job, 'info', tr('扫描完成：{v0} 个文件，{v1} 个副本', v0=len(planned), v1=len(job['targets'])))

    def checked_dest(self, job, target, relative):
        base = Path(target)
        destination = base / relative
        resolved = normalized_path(destination.resolve())
        if not under(resolved, base) or resolved == normalized_path(base) or under(resolved, Path(job['source'])):
            raise ValueError(tr('目标路径越界或指向源卡，已阻止写入'))
        current = destination
        while current != base.parent:
            if linklike(current):
                raise ValueError(tr('目标路径包含链接，已阻止写入'))
            current = current.parent
        return destination

    def space_check(self, job):
        volumes = {}
        for target in job['targets']:
            if target in job.get('target_errors', {}):
                continue
            base = self.checked_dest(job, target, '.space-check').parent
            if os.name == 'nt' and (not Path(base.anchor).exists()):
                raise OSError(tr('目标磁盘未连接：{v0}', v0=base.anchor))
            base.mkdir(parents=True, exist_ok=True)
            device = os.stat(base).st_dev
            needed = 0
            for item in job['files']:
                if target in item['copies']:
                    continue
                staged = item.get('staged', {}).get(target)
                allocated = 0
                if staged:
                    partial = self.checked_dest(job, target, staged['staging'])
                    if partial.is_file():
                        allocated = min(item['size'], partial.stat().st_size)
                needed += item['size'] - allocated
            if device in volumes:
                volumes[device][1] += needed
            else:
                volumes[device] = [base, needed]
        for base, needed in volumes.values():
            if shutil.disk_usage(base).free < needed + 16 * 1024 * 1024:
                raise OSError(tr('目标磁盘空间不足：{v0}，需约 {v1} GB（另留 16 MB）', v0=base, v1=format(needed / 1024 ** 3, f'.2f')))
        if len(job['targets']) > 1 and len(volumes) < len(job['targets']) and (not job.get('target_errors')):
            self.log(job, 'warning', tr('部分目标位于同一磁盘卷；建议使用独立硬盘降低设备故障风险'))

    def probe_target(self, job, target):
        """Exercise creation, durable write, read, publication and cleanup before copying."""
        probe = self.checked_dest(job, target, f'.cardvault-writecheck-{uuid.uuid4().hex}.tmp')
        published = probe.with_suffix('.checked')
        if os.name == 'nt' and (not Path(probe.anchor).exists()):
            raise OSError(tr('目标磁盘未连接'))
        probe.parent.mkdir(parents=True, exist_ok=True)
        payload = os.urandom(1024)
        try:
            with probe.open('xb') as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            if probe.read_bytes() != payload:
                raise OSError(tr('目标读写自检不一致'))
            os.rename(probe, published)
            published.unlink()
        finally:
            for temporary in (probe, published):
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    self.log(job, 'warning', tr('无法清理读写自检文件：{v0}', v0=temporary))

    def check_targets(self, job):
        job.update(status='checking', message=tr('检查目标目录是否可以创建、写入和提交文件…'), target_errors={})
        self.save(job)
        for target in job['targets']:
            self.checkpoint(job)
            try:
                self.probe_target(job, target)
            except OSError as error:
                message = target_error(target, error)
                job['target_errors'][target] = message
                self.log(job, 'error', message)
        if len(job['target_errors']) == len(job['targets']):
            raise TargetUnavailable('\n\n'.join(job['target_errors'].values()))

    def stopped(self, job):
        return any(event is not None and event.is_set() for event in (self.stops.get(job['id']), self.aborts.get(job['id'])))

    def read_io(self, job, path, operation):
        try:
            return self.io_guard.call(job['id'], path, lambda: self.stopped(job), operation)
        except ReadCancelled:
            raise Paused() from None

    def digest(self, path, job, limit=None):
        def progress(amount):
            with self.lock:
                index = self.verify_threads.get((job['id'], threading.get_ident()))
                if index is not None:
                    self.verifications[job['id']][index]['read'] += amount
                    self.refresh_counts(job)
        try:
            return self.hash_processes.digest(path, job.get('hash_algorithm', 'sha256'), limit,
                                             job['id'], lambda: self.stopped(job), progress)
        except ReadCancelled:
            raise Paused() from None

    def refresh_counts(self, job):
        with self.lock:
            job['copied'] = sum((f['status'] == 'done' for f in job['files']))
            job['skipped'] = sum((f['status'] == 'skipped' for f in job['files']))
            job['failed'] = sum((f['status'] == 'failed' for f in job['files']))
            active = self.transfers.get(job['id'], {})
            job['done_bytes'] = sum((f['size'] * len(f['copies']) for f in job['files'])) + sum(f['size'] * len(f.get('staged', {})) for f in job['files']) + sum((v[0] for v in active.values()))
            job['speed'] = sum((v[1] for v in active.values()))
            # Count empty files as one unit. Verification includes target and source reads.
            job['progress_total'] = sum(max(f['size'], 1) for f in job['files']) * len(job['targets'])
            job['copy_progress'] = sum(max(f['size'], 1) * (len(f['copies']) + len(f.get('staged', {}))) for f in job['files']) + sum(v[0] for v in active.values())
            job['verify_progress'] = sum(max(f['size'], 1) * len(f['copies']) for f in job['files'])
            for record in self.verifications.get(job['id'], {}).values():
                if record['target'] not in record['item']['copies']:
                    job['verify_progress'] += min(record['read'] / 2, record['item']['size'] * .99)
            job['copy_progress'] = min(job['progress_total'], job['copy_progress'])
            job['verify_progress'] = min(job['progress_total'], job['verify_progress'])

    def check_source(self, source, item):
        if linklike(source) or normalized_path(source.resolve()) != normalized_path(source):
            raise OSError(tr('源路径已变化或包含链接，请创建新任务'))
        stat = source.stat()
        if stat.st_size != item['size'] or stat.st_mtime_ns != item['mtime_ns']:
            raise OSError(tr('源文件自扫描后发生变化，请创建新任务，避免混合不同版本'))

    def plan_destinations(self, job):
        """Reserve every output before dispatch; persist names for crash recovery."""
        for target in job['targets']:
            reserved = set()
            for item in job['files']:
                saved = item.get('destinations', {}).get(target)
                copied = item['copies'].get(target)
                relative = copied['path'] if copied else saved['path'] if saved else item['output']
                dest = self.checked_dest(job, target, relative)
                collision = str(dest).casefold() in reserved
                original = dest
                counter = 1
                while str(dest).casefold() in reserved or (not copied and (not saved) and (job['duplicate'] == 'rename') and dest.exists()):
                    dest = original.with_name(f'{original.stem} ({counter}){original.suffix}')
                    counter += 1
                reserved.add(str(dest).casefold())
                item.setdefault('destinations', {})[target] = {'path': str(dest.relative_to(target)), 'collision': collision or bool(saved and saved['collision'])}
        self.save(job, force=True)

    def copy_one(self, job, item, target, index):
        algorithm = job.get('hash_algorithm', 'sha256')
        source = Path(job['source']) / item['relative']
        self.check_source(source, item)
        staged = item.get('staged', {}).get(target)
        if job.get('verification') == 'batch' and staged and not staged.get('verify_failed'):
            partial = self.checked_dest(job, target, staged['staging'])
            if partial.is_file() and partial.stat().st_size == item['size']:
                return
        job['status'] = 'verifying'
        job['message'] = tr('计算源文件 {v0}', v0=algorithm.upper())
        expected = self.digest(source, job)
        if item.get(algorithm) and item[algorithm] != expected:
            raise OSError(tr('源文件内容已变化，请创建新任务'))
        with self.lock:
            item[algorithm] = expected
        existing = item['copies'].get(target)
        if existing:
            dest = self.checked_dest(job, target, existing['path'])
            if dest.is_file() and dest.stat().st_size == item['size'] and (self.digest(dest, job) == expected):
                return
            with self.destination_lock:
                with self.lock:
                    del item['copies'][target]
                allocation = item['destinations'][target]
                if job['duplicate'] == 'rename' or allocation['collision']:
                    reserved = {str(Path(target) / other['destinations'][target]['path']).casefold() for other in job['files'] if other is not item}
                    original, counter = dest, 1
                    while dest.exists() or str(dest).casefold() in reserved:
                        dest = original.with_name(f'{original.stem} ({counter}){original.suffix}')
                        counter += 1
                    allocation['path'] = str(dest.relative_to(target))
            self.log(job, 'warning', tr('已完成副本发生变化，重新备份：{v0}', v0=item['relative']))
        with self.lock:
            item.get('staged', {}).pop(target, None)
        allocation = item['destinations'][target]
        relative, collision = (allocation['path'], allocation['collision'])
        dest = self.checked_dest(job, target, relative)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and (job['duplicate'] == 'rename' or collision):
            # A crash can occur after publication but before the manifest save.
            # Adopt only a fully verified file at this item's reserved path.
            if dest.is_file() and dest.stat().st_size == item['size'] and self.digest(dest, job) == expected:
                self.check_source(source, item)
                with self.lock:
                    item['copies'][target] = {'path': relative, algorithm: expected, 'action': 'copied'}
                return
            with self.destination_lock:
                reserved = {str(Path(target) / other['destinations'][target]['path']).casefold() for other in job['files'] if other is not item}
                original, counter = dest, 1
                while dest.exists() or str(dest).casefold() in reserved:
                    dest = original.with_name(f'{original.stem} ({counter}){original.suffix}')
                    counter += 1
                relative = str(dest.relative_to(target))
                allocation['path'] = relative
            self.save(job, force=True)
        if dest.exists() and (not collision) and (job['duplicate'] == 'skip'):
            if dest.is_file() and dest.stat().st_size == item['size'] and (self.digest(dest, job) == expected):
                self.check_source(source, item)
                with self.lock:
                    item['copies'][target] = {'path': relative, algorithm: expected, 'action': 'skipped'}
                return
            raise OSError(tr('同名文件内容不同，已保留原文件；请选择自动改名或覆盖策略'))
        staging = self.checked_dest(job, target, str(dest.parent.relative_to(target) / f".cardvault-{job['id']}-{index}.part"))
        offset = staging.stat().st_size if staging.exists() else 0
        if offset > item['size'] or (offset and self.digest(staging, job) != self.digest(source, job, offset)):
            staging.unlink()
            offset = 0
            self.log(job, 'warning', tr('临时文件校验不符，从头重拷：{v0}', v0=item['relative']))
        job.update(status='copying', message=tr('正在复制到 ') + target)
        started, transferred = (time.monotonic(), 0)
        self.refresh_counts(job)
        with self.lock:
            self.transfers.setdefault(job['id'], {})[index] = (offset, 0)
        with source.open('rb') as src, staging.open('ab' if offset else 'wb') as dst:
            src.seek(offset)
            while True:
                self.checkpoint(job)
                block = self.read_io(job, source, lambda: src.read(CHUNK))
                if not block:
                    break
                dst.write(block)
                transferred += len(block)
                with self.lock:
                    self.transfers[job['id']][index] = (offset + transferred, transferred / max(time.monotonic() - started, 0.001))
                    self.refresh_counts(job)
            dst.flush()
            os.fsync(dst.fileno())
        with self.lock:
            item.setdefault('staged', {})[target] = {'path': relative, 'staging': str(staging.relative_to(target)), algorithm: expected, 'collision': collision}
            self.transfers.get(job['id'], {}).pop(index, None)
            self.refresh_counts(job)
        self.save(job)
        if job.get('verification', 'per_file') != 'batch':
            self.verify_one(job, item, target, index)

    def verify_one(self, job, item, target, index):
        with self.lock:
            self.verifications.setdefault(job['id'], {})[index] = {'item': item, 'target': target, 'read': 0}
            self.verify_threads[(job['id'], threading.get_ident())] = index
        try:
            self._verify_one(job, item, target, index)
        except HashTimeout:
            raise
        except (OSError, ValueError):
            with self.lock:
                if target in item.get('staged', {}):
                    item['staged'][target]['verify_failed'] = True
            raise
        finally:
            with self.lock:
                self.verifications.get(job['id'], {}).pop(index, None)
                self.verify_threads.pop((job['id'], threading.get_ident()), None)
                self.refresh_counts(job)

    def _verify_one(self, job, item, target, index):
        algorithm = job.get('hash_algorithm', 'sha256')
        record = item['staged'][target]
        source = Path(job['source']) / item['relative']
        relative, collision, expected = record['path'], record['collision'], record[algorithm]
        dest = self.checked_dest(job, target, relative)
        staging = self.checked_dest(job, target, record['staging'])
        self.check_source(source, item)
        with self.lock:
            self.transfers.get(job['id'], {}).pop(index, None)
            job.update(status='verifying', message=tr('校验目标副本 {v0}', v0=algorithm.upper()))
            self.refresh_counts(job)
        if self.digest(staging, job) != expected:
            raise OSError(tr('{v0} 校验不一致，目标副本未提交', v0=algorithm.upper()))
        if self.digest(source, job) != expected:
            raise OSError(tr('复制期间源文件发生变化，目标副本未提交'))
        self.check_source(source, item)
        self.checkpoint(job)
        self.checked_dest(job, target, relative)
        if job['duplicate'] == 'overwrite' and (not collision):
            os.replace(staging, dest)
        elif os.name == 'nt':
            os.rename(staging, dest)
        else:
            os.link(staging, dest)
            staging.unlink()
        try:
            os.utime(dest, ns=(item['mtime_ns'], item['mtime_ns']))
        except OSError:
            self.log(job, 'warning', tr('无法保留文件时间：{v0}', v0=dest.name))
        with self.lock:
            item.get('staged', {}).pop(target, None)
            item['copies'][target] = {'path': relative, algorithm: expected, 'action': 'copied'}
            self.transfers.get(job['id'], {}).pop(index, None)

    def process_file(self, job, index, item, verify_only=False):
        self.checkpoint(job)
        with self.lock:
            job['current'] = item['relative']
            item['status'] = 'pending'
        errors = list(item.get('copy_errors', [])) if verify_only else []
        for target in job['targets']:
            if verify_only and target not in item.get('staged', {}):
                continue
            if target in job['target_errors']:
                errors.append(job['target_errors'][target])
                continue
            for attempt in range(job['retries'] + 1):
                try:
                    self.checkpoint(job)
                    with self.lock:
                        failure = job['target_errors'].get(target)
                    if failure:
                        errors.append(failure)
                        break
                    if verify_only:
                        self.verify_one(job, item, target, index)
                    else:
                        self.copy_one(job, item, target, index)
                    with self.lock:
                        self.transfers.get(job['id'], {}).pop(index, None)
                    self.save(job)
                    break
                except (Paused, HashTimeout):
                    raise
                except (OSError, ValueError) as error:
                    with self.lock:
                        self.transfers.get(job['id'], {}).pop(index, None)
                    self.log(job, 'error', tr('{v0} → {v1}：{v2}（尝试 {v3}）', v0=item['relative'], v1=target, v2=error, v3=attempt + 1))
                    filename = getattr(error, 'filename', None)
                    if isinstance(error, PermissionError) and filename and under(Path(filename).resolve(), Path(target)):
                        message = target_error(target, error)
                        with self.lock:
                            job['target_errors'][target] = message
                        errors.append(message)
                        self.log(job, 'error', tr('停止对此目标重复尝试：') + message)
                        break
                    if attempt == job['retries']:
                        errors.append(f'{target}: {error}')
                    elif self.stops[job['id']].wait(min(attempt + 1, 3)):
                        raise Paused()
        with self.lock:
            if not verify_only:
                item['copy_errors'] = list(errors)
            if errors:
                item.update(status='failed', error='；'.join(errors))
            elif item.get('staged'):
                item['status'] = 'awaiting_verification'
            else:
                item['status'] = 'skipped' if all((c['action'] == 'skipped' for c in item['copies'].values())) else 'done'
                item.pop('error', None)
        if not errors and not item.get('staged'):
            self.log(job, 'success', tr('校验完成：{v0}', v0=item['relative']))
        with self.lock:
            self.transfers.get(job['id'], {}).pop(index, None)
        self.refresh_counts(job)
        self.save(job)
        if len(job['target_errors']) == len(job['targets']):
            raise TargetUnavailable('\n\n'.join(job['target_errors'].values()))

    def run(self, job):
        paused = False
        self.aborts[job['id']] = threading.Event()
        try:
            self.checkpoint(job)
            self.check_targets(job)
            if not job['scanned']:
                self.scan(job)
            self.space_check(job)
            self.log(job, 'info', tr('任务开始；所有副本启用 {v0} 校验', v0=job.get('hash_algorithm', 'sha256').upper()))
            self.plan_destinations(job)
            self.transfers[job['id']] = {}
            for verify_only in ([False, True] if job.get('verification') == 'batch' else [False]):
                job['phase'] = 'verification' if verify_only else 'transfer'
                items = iter(enumerate(job['files']))
                workers = 1 if verify_only else min(8, max(1, int(job.get('workers', 3))))
                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='copy-' + job['id'][:6]) as pool:
                    pending = set()
    
                    def fill():
                        self.checkpoint(job)
                        while len(pending) < workers:
                            pair = next(items, None)
                            if pair is None:
                                break
                            pending.add(pool.submit(self.process_file, job, *pair, verify_only=verify_only))
                    try:
                        fill()
                        while pending:
                            finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                            for future in finished:
                                future.result()
                            fill()
                    except BaseException:
                        self.aborts[job['id']].set()
                        for future in pending:
                            future.cancel()
                        raise
            job['status'] = 'partial' if job['failed'] else 'completed'
            job['message'] = tr('完成：{v0} 个已复制，{v1} 个相同文件已跳过，{v2} 个失败', v0=job['copied'], v1=job['skipped'], v2=job['failed'])
            self.log(job, 'warning' if job['failed'] else 'success', job['message'])
        except Paused:
            paused = True
            job.update(status='pausing', message=tr('正在保存进度…'))
            self.log(job, 'info', tr('任务已暂停'))
        except Exception as error:
            job.update(status='failed', message=str(error))
            self.log(job, 'error', str(error))
        finally:
            self.aborts.pop(job['id'], None)
            self.transfers.pop(job['id'], None)
            self.verifications.pop(job['id'], None)
            job['speed'] = 0
            self.refresh_counts(job)
            self.save(job, force=True, paused=paused)

    def report(self, ident, format='json'):
        with self.lock:
            job = json.loads(json.dumps(self.jobs[ident]))
        job['summary'] = {'success': job['copied'] + job['skipped'], 'failed': job['failed'], 'skipped': job['skipped'], 'pending': job['total_files'] - job['copied'] - job['skipped'] - job['failed']}
        if format == 'csv':
            out = io.StringIO(newline='')
            writer = csv.writer(out)
            writer.writerow([tr('成功'), job['summary']['success'], tr('失败'), job['failed'], tr('已跳过'), job['skipped'], tr('未完成'), job['summary']['pending']])
            writer.writerow([])
            writer.writerow([tr('源文件'), tr('大小（字节）'), tr('状态'), tr('目标目录'), tr('目标文件'), job.get('hash_algorithm', 'sha256').upper(), tr('动作'), tr('错误')])
            for item in job['files']:
                for target in job['targets']:
                    copy = item['copies'].get(target, {})
                    row = [item['relative'], item['size'], item['status'], target, copy.get('path', ''), copy.get(job.get('hash_algorithm', 'sha256'), ''), copy.get('action', ''), item.get('error', '')]
                    writer.writerow(["'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else v for v in row])
            return ('\ufeff' + out.getvalue()).encode('utf-8')
        return json.dumps(job, ensure_ascii=False, indent=2).encode('utf-8')

    def shutdown(self):
        for event in self.stops.values():
            event.set()
        self.pool.shutdown(wait=True)
        self.io_guard.close()
