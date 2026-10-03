"""Independent classic snapshots; release.json is the sole commit point.

POSIX writer locking supports the current Linux runtime and future Linux CI.
Readers see an entire verified old or new snapshot, never a mixed canonical set.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import os
import re
import shutil
import stat
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import classic_papers as cp

FILES = ('edition.json', 'archive.json', 'queue.json', 'status.json')
RELEASE = re.compile(r'c-[0-9a-f]{64}')


def _clock(now):
    cp.require(isinstance(now, datetime), 'Aware datetime clock required')
    return cp.beijing_date(now)


def _namespace(root):
    try:
        root = Path(root).absolute()
    except (TypeError, ValueError) as exc:
        raise ValueError('Dedicated classics path required') from exc
    cp.require(root.name == 'classics', 'Publisher requires a dedicated classics directory')
    for path in (root, *root.parents):
        cp.require(not path.is_symlink(), 'Symlinked classic namespace or parent refused')
    root = root.resolve()
    cp.require(not any(path.name in {'data', 'releases'} and path.parent.name == 'public'
                       for path in root.parents), 'Classic namespace cannot be inside news public/data or public/releases')
    cp.require(not root.exists() or root.is_dir(), 'Classic namespace must be a directory')
    for name in ('releases', 'release.json', '.publish.lock'):
        cp.require(not (root / name).is_symlink(), 'Symlinked classic publication component refused')
    cp.require(not (root / 'releases').exists() or (root / 'releases').is_dir(), 'Invalid release storage')
    return root


@contextmanager
def _locked(root):
    root.mkdir(parents=True, exist_ok=True)
    fd = os.open(root / '.publish.lock', os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        cp.require(stat.S_ISREG(os.fstat(fd).st_mode) and os.fstat(fd).st_nlink == 1, 'Unsafe writer lock')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('Classic publisher already running') from exc
        yield
    finally:
        os.close(fd)


def _id(files):
    return 'c-' + hashlib.sha256(cp.canonical(files)).hexdigest()


def _validate_manifest(manifest, release_id=None):
    cp._header(manifest, 'classicRelease')
    cp.require(set(manifest) == cp.HEADER_KEYS | {'releaseId', 'basePath', 'recommendationDate',
               'latestPublishedDate', 'files'}, 'Invalid classic manifest fields')
    rid = manifest.get('releaseId')
    cp.require(isinstance(rid, str) and RELEASE.fullmatch(rid), 'Invalid release identity')
    cp.require(release_id is None or rid == release_id, 'Snapshot identity differs')
    cp.require(manifest['basePath'] == './releases/' + rid + '/', 'Unsafe snapshot base path')
    files = manifest['files']
    cp.require(isinstance(files, dict) and set(files) == set(FILES)
               and all(cp._sha(v) for v in files.values()), 'Invalid snapshot file set/hash')
    cp.require(rid == _id(files), 'Release identity is not content-bound')


def _empty_edition():
    return cp.envelope('classicEdition', recommendationDate=None, publishedAt=None, itemCount=0, items=[])


def _validate_state(state):
    cp.require(set(state) == {'edition', 'archive', 'queue', 'status'}, 'Invalid state file set')
    archive, queue, edition, status = (state[k] for k in ('archive', 'queue', 'edition', 'status'))
    cp.validate_queue(queue, archive=archive)
    cp._header(edition, 'classicEdition')
    day = edition.get('recommendationDate')
    if day is None:
        cp.require(edition == _empty_edition() and not archive['editions'], 'Empty edition cannot hide published history')
    else:
        cp.require(isinstance(day, str) and archive['editions'].get(day) == edition,
                   'Selected edition differs from archive')
    cp._header(status, 'classicStatus')
    inventory_keys = {'readyPaperCount', 'lowStock', 'completeDays', 'futureCompleteDays',
                      'futurePaperCount', 'firstMissingDate'}
    cp.require(set(status) == cp.HEADER_KEYS | inventory_keys | {'state', 'targetDate', 'inventoryDate',
               'editionDate', 'latestPublishedDate', 'message', 'lastAttemptAt'}, 'Invalid classic status fields')
    cp.require(status.get('state') in ('ok', 'pending', 'restored'), 'Invalid classic status')
    cp.require(day is not None or status['state'] == 'pending', 'Only pending can have no edition')
    cp.beijing_date(status['targetDate'])
    today = cp.beijing_date(status['inventoryDate'])
    cp.require(isinstance(status['lastAttemptAt'], str), 'Status timestamp required')
    cp.require(cp.beijing_date(datetime.fromisoformat(status['lastAttemptAt'])) == today,
               'Status clock/inventory date differs')
    latest = max(archive['editions'], default=None)
    cp.require(status['editionDate'] == day and status['latestPublishedDate'] == latest,
               'Status must retain actual selected/history dates')
    expected = cp.inventory(queue, archive, today)
    for key in inventory_keys:
        cp.require(type(status[key]) is type(expected[key]) and status[key] == expected[key],
                   'Incorrect ready-stock/coverage status')
    cp.require(cp._text(status['message']), 'Status message required')
    cp.canonical(state)


def _verify_snapshot(snapshot):
    cp.require(snapshot.is_dir() and not snapshot.is_symlink(), 'Missing or symlinked snapshot')
    cp.require({p.name for p in snapshot.iterdir()} == set(FILES) | {'manifest.json'}, 'Snapshot file set differs')
    for path in snapshot.iterdir():
        cp.require(path.is_file() and not path.is_symlink(), 'Unsafe snapshot member')
    manifest = cp.read_json(snapshot / 'manifest.json')
    _validate_manifest(manifest, snapshot.name)
    state = {}
    for name in FILES:
        path = snapshot / name
        cp.require(hashlib.sha256(path.read_bytes()).hexdigest() == manifest['files'][name], 'Snapshot checksum differs')
        state[name.removesuffix('.json')] = cp.read_json(path)
    _validate_state(state)
    cp.require(manifest['recommendationDate'] == state['edition']['recommendationDate']
               and manifest['latestPublishedDate'] == max(state['archive']['editions'], default=None),
               'Manifest dates differ from frozen state')
    return dict(manifest=manifest, **state)


def read_current(root: Path):
    root = _namespace(root)
    pointer = root / 'release.json'
    if not pointer.exists():
        return None
    cp.require(pointer.is_file(), 'Invalid classic pointer')
    manifest = cp.read_json(pointer)
    _validate_manifest(manifest)
    current = _verify_snapshot(root / 'releases' / manifest['releaseId'])
    cp.require(current['manifest'] == manifest, 'Pointer and snapshot differ')
    return current


def _write(path, raw):
    with path.open('xb') as file:
        file.write(raw)
        file.flush()
        os.fsync(file.fileno())


def _sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _commit(root, state):
    _validate_state(state)
    payloads = {key + '.json': cp.canonical(value) for key, value in state.items()}
    hashes = {name: hashlib.sha256(payloads[name]).hexdigest() for name in FILES}
    rid = _id(hashes)
    manifest = cp.envelope('classicRelease', releaseId=rid, basePath='./releases/' + rid + '/',
                           recommendationDate=state['edition']['recommendationDate'],
                           latestPublishedDate=max(state['archive']['editions'], default=None), files=hashes)
    releases = root / 'releases'
    releases.mkdir(exist_ok=True)
    target = releases / rid
    if target.exists():
        existing = _verify_snapshot(target)
        cp.require(existing == dict(manifest=manifest, **state), 'Existing orphan differs from intended state')
    else:
        temporary = Path(tempfile.mkdtemp(prefix='.building-', dir=releases))
        try:
            for name in FILES:
                _write(temporary / name, payloads[name])
            _write(temporary / 'manifest.json', cp.canonical(manifest))
            _sync_dir(temporary)
            os.replace(temporary, target)
            _sync_dir(releases)
            _verify_snapshot(target)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    pointer = root / ('.release-' + uuid4().hex + '.tmp')
    try:
        _write(pointer, cp.canonical(manifest))
        os.replace(pointer, root / 'release.json')
    finally:
        pointer.unlink(missing_ok=True)
    return dict(manifest=manifest, **copy.deepcopy(state))


def _merge_queue(current, incoming, pool, archive):
    cp.validate_queue(incoming, pool)
    merged = copy.deepcopy(current)
    for day, slot in incoming['slots'].items():
        cp.require(day not in merged['slots'] or merged['slots'][day] == slot,
                   'Cannot replace a locked future combination')
        merged['slots'][day] = copy.deepcopy(slot)
    merged['slots'] = dict(sorted(merged['slots'].items()))
    cp.validate_queue(merged, pool, archive)
    return merged


def _status(kind, target, edition, archive, queue, now):
    stock = cp.inventory(queue, archive, _clock(now))
    stock.pop('targetDate')
    message = {'ok': '经典论文已更新', 'pending': '今日待更新', 'restored': '已恢复历史版本'}[kind]
    return cp.envelope('classicStatus', state=kind, targetDate=target,
                       inventoryDate=_clock(now).isoformat(), editionDate=edition['recommendationDate'],
                       latestPublishedDate=max(archive['editions'], default=None), message=message,
                       lastAttemptAt=now.isoformat(), **stock)


def publish(root: Path, target_date, queue: dict, pool: list[dict], *, now: datetime) -> dict:
    target, today = cp.beijing_date(target_date), _clock(now)
    cp.require(target <= today, 'Cannot publish a future recommendation date')
    root = _namespace(root)
    with _locked(root):
        current = read_current(root)
        archive = copy.deepcopy(current['archive']) if current else cp.envelope('classicArchive', editions={})
        oldq = current['queue'] if current else cp.envelope('classicQueue', slots={})
        merged = _merge_queue(oldq, queue, pool, archive)
        day = target.isoformat()
        if day in archive['editions']:
            return current
        edition = copy.deepcopy(current['edition']) if current else _empty_edition()
        if day in merged['slots']:
            actual = cp._occurrences(None, archive)
            items = copy.deepcopy(merged['slots'][day]['items'])
            for paper in items:
                previous = [d for d in actual.get(paper['id'], set()) if d < target]
                prior = max(previous).isoformat() if previous else None
                paper.update(classicReread=prior is not None, previousRecommendationDate=prior)
            posted = cp.envelope('classicEdition', recommendationDate=day, publishedAt=now.isoformat(),
                                 itemCount=2, items=items)
            archive['editions'][day] = posted
            archive['editions'] = dict(sorted(archive['editions'].items()))
            cp.validate_queue(merged, pool, archive)
            if edition['recommendationDate'] is None or day > edition['recommendationDate']:
                edition = posted
            kind = 'ok'
        else:
            kind = 'pending'
        return _commit(root, dict(edition=edition, archive=archive, queue=merged,
                                 status=_status(kind, day, edition, archive, merged, now)))


def restore(root: Path, release_id: str, *, now: datetime) -> dict:
    today = _clock(now)
    cp.require(isinstance(release_id, str) and RELEASE.fullmatch(release_id), 'Invalid release identity')
    root = _namespace(root)
    with _locked(root):
        current = read_current(root)
        cp.require(current is not None, 'No current classic state to restore')
        target = _verify_snapshot(root / 'releases' / release_id)
        day = target['edition']['recommendationDate']
        cp.require(day is not None and cp.beijing_date(day) <= today, 'Cannot restore an empty/future edition')
        archive = copy.deepcopy(current['archive'])
        for key, edition in target['archive']['editions'].items():
            cp.require(key not in archive['editions'] or archive['editions'][key] == edition,
                       'Restoration cannot replace published history')
            archive['editions'][key] = copy.deepcopy(edition)
        archive['editions'] = dict(sorted(archive['editions'].items()))
        queue = copy.deepcopy(current['queue'])
        cp.validate_queue(queue, archive=archive)
        edition = copy.deepcopy(archive['editions'][day])
        return _commit(root, dict(edition=edition, archive=archive, queue=queue,
                                 status=_status('restored', today.isoformat(), edition, archive, queue, now)))
