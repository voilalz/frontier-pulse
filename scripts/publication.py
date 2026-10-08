#!/usr/bin/env python3
"""Validate staged output, promote complete releases, and restore retained snapshots.

Only GitHub's final commit exposes canonical file changes to the static host.
The browser uses immutable snapshots and the manifest is the last file installed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import fcntl
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from update_news import validate_report, validate_stream_report, write_json_atomic
from news_boundary import safe_path, owns, NEWS_TOP, NEWS_SCOPE

RELEASE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}')
RETAINED_SNAPSHOTS = 7
STREAM_FILES = ('data/stream.json', 'data/stream-status.json', 'data/events.json', 'data/source-health.json')


def read_json(path: Path):
    path = safe_path(path, allow_releases=True)
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError(f'Unreadable publication artifact: {path.name}') from exc


def require(condition, message):
    if not condition:
        raise ValueError(message)



def checked_root(root, *, write=False, releases=False):
    root = safe_path(root, write=write, allow_releases=releases)
    require(not root.exists() or root.is_dir(), 'Publication root is not a directory')
    safe_path(root / 'data', write=write, allow_releases=releases)
    return root


def copy_news(source, target):
    paths = artifacts(source)
    # Preflight the complete target before any mkdir, cleanup or copy.
    for path in paths:
        safe_path(target / path.relative_to(source), write=True, allow_releases=True)
    for path in paths:
        dest = target / path.relative_to(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)


def prepare_stage(public: Path, stage: Path):
    public, stage = checked_root(public), checked_root(stage, write=True)
    require(public != stage and public not in stage.parents and stage not in public.parents,
            'Stage must be outside the publication directory')
    source_paths, old_paths = artifacts(public), artifacts(stage)
    for path in [*(stage / p.relative_to(public) for p in source_paths), *old_paths]:
        safe_path(path, write=True)
    for path in old_paths:
        path.unlink()
    stage.mkdir(parents=True, exist_ok=True)
    copy_news(public, stage)


def validate_publication(stage: Path, mode: str, expected_date: str | None = None, *, snapshot=False):
    stage = checked_root(stage, releases=snapshot)
    artifacts(stage)  # Guard every owned path, without reading unrelated content.
    try:
        _validate(stage, mode, expected_date)
    except (KeyError, TypeError, AssertionError, IndexError) as exc:
        raise ValueError(f'Publication contract failed: {exc}') from exc


def _validate(stage, mode, expected_date):
    require(mode in {'daily', 'stream'}, 'Invalid publication mode')
    data = stage / 'data'
    stream = read_json(data / 'stream.json')
    validate_stream_report(stream)
    require(stream.get('itemCount') == len(stream['items']) > 0, 'Invalid stream count')
    registry = read_json(data / 'events.json')
    require(registry.get('schemaVersion') == 2 and registry.get('eventCount') == len(registry['items']),
            'Invalid event registry')
    known = {n for event in registry['items'] for n in event['newsIds']}
    require(all(item['id'] in known and item.get('eventId') and item.get('eventIdentity')
                for item in stream['items']), 'Missing stream event reference')
    health = read_json(data / 'source-health.json')
    require(health.get('qualifiedCandidateCount') == stream.get('qualifiedCandidateCount'), 'Source counts differ')
    require(read_json(data / 'stream-status.json').get('state') == 'ok', 'Stream generation failed')
    if mode == 'stream':
        return
    news, deep = read_json(data / 'news.json'), read_json(data / 'deepread.json')
    validate_report(news, 10)
    edition = news.get('editionDate')
    require(bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(edition))), 'Missing edition date')
    if expected_date:
        require(edition == expected_date, 'Wrong publication date')
    require(news.get('schemaVersion') == 11 and news.get('timezone') == 'Asia/Shanghai', 'Invalid news schema/timezone')
    require(all(x.get('summaryRevision') == 5 and x.get('eventId') and x['id'] in known
                and isinstance(x.get('keyFacts'), list) and x.get('sources')
                and x.get('eventDossier') and x.get('evidenceMatrix')
                and isinstance(x.get('historyContext'), dict) and x['historyContext'].get('outlook')
                for x in news['items']), 'Invalid news detail contract')
    require(news.get('translatedItemCount') == sum(bool(x.get('translationProvider')) for x in news['items']),
            'Translation count mismatch')
    require(news.get('historyLinkedItemCount') == sum(x['historyContext'].get('status') == 'linked' for x in news['items']),
            'History count mismatch')
    require(len(set(news.get('spotlightIds', []))) == min(3,len(news['items'])) and set(news['spotlightIds']) <= {x['id'] for x in news['items']},
            'Invalid spotlight references')
    require(deep.get('schemaVersion') == 2 and deep.get('generationRevision') in {12, 13}, 'Invalid deepread revision')
    from evidence_trace import validate_news_trace, valid_display_translation
    from reader_quality import assess_admissibility, chinese_reader_text
    from deepread_quality import validate_readable
    for item in news['items']:
        validate_news_trace(item)
        require(assess_admissibility(item)['eligible'], 'Featured story is not a body event')
        display = item['displayTranslation'] if valid_display_translation(item) else item
        require(chinese_reader_text(display.get('title')) and chinese_reader_text(display.get('summary')), 'Featured Chinese reader quality failed')
    validate_readable(deep, edition)
    deep_date = deep.get('editionDate')
    events, chapters = deep['events'], deep['chapters']
    ids = {x['newsId'] for x in events}
    require(len(events) == deep.get('eventCount') <= 6 and deep.get('candidateCount', 13) <= 12,
            'Invalid deepread counts')
    require(len(ids) == len(events) == len({x['eventId'] for x in events}), 'Repeated deepread event')
    require(deep.get('readerStatus') == 'retained' or ids <= known, 'Deepread references absent from event registry')
    chapter_ids = [n for chapter in chapters for n in chapter['newsIds']]
    if deep.get('generationRevision') == 13:
        chapter_ids += [n for brief in deep.get('briefs', []) for n in brief['newsIds']]
    require(set(chapter_ids) == ids and len(chapter_ids) == len(ids), 'Invalid chapter references')
    for chapter in chapters:
        require(chapter.get('kind') in {'event', 'comparison'}, 'Invalid chapter kind')
        if chapter['kind'] == 'comparison':
            require(2 <= len(chapter['newsIds']) <= 3 and chapter.get('comparisonNote') == '并列比较不代表事件之间存在因果关系。',
                    'Missing comparison limitation')
        require(bool(chapter.get('blocks')), 'Chapter has no blocks')
        for block in chapter['blocks']:
            require(bool(block.get('text')) and bool(block.get('newsIds'))
                    and set(block['newsIds']) <= set(chapter['newsIds']), 'Invalid paragraph references')
    for event in events:
        require(event.get('sources') and all(urlsplit(s.get('url', '')).scheme in {'http', 'https'} for s in event['sources']),
                'Missing/invalid source URL')
    observations = deep.get('observations')
    require(isinstance(observations, list), 'Missing observations')
    require(deep.get('generationRevision') == 13 or deep.get('generationStatus') != 'ok' or 2 <= len(observations) <= 3, 'Incomplete observations')
    for observation in observations:
        refs = set(observation.get('newsIds', []))
        require(bool(refs) and refs <= ids and {x.get('newsId') for x in observation.get('supports', [])} == refs,
                'Invalid observation references')
    status = read_json(data / 'status.json')
    require(status.get('state') == 'ok' and status.get('editionDate') == edition, 'Unhealthy daily generation')
    require(read_json(data / f'archive/{edition}.json') == news, 'Daily archive differs from current report')
    def deep_content(value):
        from deepread_quality import normalize_legacy_deepread, validate_complete
        value = normalize_legacy_deepread(value)
        try:
            validate_complete(value)
            value['generationStatus'] = 'ok'
        except (ValueError, TypeError, KeyError):
            pass
        return {k:v for k,v in value.items() if k not in {'releaseId','readerStatus','publicationEditionDate',
            'qualityFailures','generationAttemptStatus','generationDiagnostics'}}
    require(deep_content(read_json(data / f'deepread/{deep_date}.json')) == deep_content(deep), 'Deepread archive differs from current report')
    archive_ids = {}
    for name in ['archive/index.json', 'deepread/index.json']:
        index = read_json(data / name)
        require(isinstance(index.get('editions'), list), 'Invalid archive index')
        seen_dates = set()
        required_date = edition if name.startswith('archive/') else deep_date
        require(required_date in {x['editionDate'] for x in index['editions']}, 'Edition missing from archive index')
        for entry in index['editions']:
            date = entry['editionDate']
            require(bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', date)), 'Invalid archive date')
            datetime.fromisoformat(date)
            require(date not in seen_dates, 'Repeated archive date')
            seen_dates.add(date)
            archived = read_json(data / Path(name).parent / f'{date}.json')
            require(isinstance(archived, dict) and archived.get('editionDate') == date, 'Archive date mismatch')
            if name.startswith('archive/'):
                rows = archived.get('items')
                require(isinstance(rows, list) and (rows or archived.get('coverageStatus') == 'insufficient')
                        and all(isinstance(row, dict) and row.get('id') for row in rows), 'Invalid archived items')
                ids = {row['id'] for row in rows}
                require(len(ids) == len(rows) and archived.get('itemCount', len(rows)) == len(rows), 'Invalid archive count')
                archive_ids[date] = ids
            else:
                # Schema 1 stores historical events inside sections. The reader
                # still supports that format; it must not block a new edition.
                if archived.get('schemaVersion') == 1 and 'sections' in archived:
                    sections = archived['sections']
                    require(isinstance(sections, list) and all(
                        isinstance(section, dict)
                        and isinstance(section.get('events'), list)
                        and all(isinstance(event, dict) for event in section['events'])
                        for section in sections
                    ), f'Invalid deepread archive: {date}')
                else:
                    require(isinstance(archived.get('events', archived.get('items')), list),
                            f'Invalid deepread archive: {date}')
    search = read_json(data / 'archive/search-index.json')
    require(search.get('schemaVersion') == 2 and isinstance(search.get('shards'), list), 'Invalid search index')
    seen_rows, seen_months = set(), set()
    total = 0
    for shard in search['shards']:
        file = shard.get('file', '')
        require(bool(re.fullmatch(r'\./data/archive/search-\d{4}-\d{2}\.json', file)), 'Invalid search shard path')
        payload = read_json(stage / file)
        month = shard.get('month')
        require(month not in seen_months and file == f'./data/archive/search-{month}.json', 'Invalid shard month')
        seen_months.add(month)
        rows = payload.get('items')
        require(payload.get('schemaVersion') == 2 and payload.get('month') == month and isinstance(rows, list), 'Invalid search shard')
        require(len(rows) == payload.get('itemCount') == shard.get('itemCount'), 'Search count mismatch')
        for row in rows:
            date, news_id = row.get('editionDate', ''), row.get('id')
            require(date.startswith(month + '-') and news_id in archive_ids.get(date, set()), 'Invalid search archive reference')
            require((date, news_id) not in seen_rows, 'Repeated search row')
            seen_rows.add((date, news_id))
        dates = sorted({row['editionDate'] for row in rows})
        require(bool(dates) and len(dates) == shard.get('editionCount') and dates[0] == shard.get('fromDate') and dates[-1] == shard.get('toDate'), 'Search date bounds mismatch')
        total += len(rows)
    require(search.get('itemCount') == total and search.get('editionCount') == len({date for date, _ in seen_rows}), 'Search index count mismatch')
    weekly, signals = read_json(data / 'weekly.json'), read_json(data / 'signals.json')
    require(weekly.get('weekId') and weekly.get('eventCount') == len(weekly['events']), 'Weekly count mismatch')
    require(signals.get('signalCount') == len(signals['signals']), 'Signal count mismatch')
    from xml.etree import ElementTree
    try:
        ElementTree.parse(stage / 'feed.xml')
    except (OSError, ElementTree.ParseError) as exc:
        raise ValueError('Invalid Atom feed') from exc


def artifacts(root: Path, *, include_versions=False):
    root = checked_root(root, releases=True)
    candidates = [root/'feed.xml', *(root/'data'/name for name in sorted(NEWS_TOP))]
    for folder in ['archive', 'deepread', 'weekly', *(['edition-versions'] if include_versions else [])]:
        directory = safe_path(root/'data'/folder, allow_releases=True)
        if directory.exists():
            require(directory.is_dir(), 'News archive is not a directory')
            candidates.extend(p for p in directory.iterdir() if owns(p.relative_to(root).as_posix()))
    result = []
    for path in candidates:
        safe_path(path, allow_releases=True)
        if path.exists():
            require(path.is_file(), 'Owned news artifact is not a file')
            result.append(path)
    return sorted(result)


def artifact_name(path):
    for parent in path.parents:
        if parent.name == 'data':
            return 'data/' + path.relative_to(parent).as_posix()
    return 'feed.xml' if path.name == 'feed.xml' else ''


def pure_news_snapshot(snapshot):
    # Unlike restoration, deletion requires every descendant to be ours.
    allowed_dirs = {'data', 'data/archive', 'data/deepread', 'data/weekly', 'data/edition-versions'}
    for directory, folders, files in os.walk(snapshot, followlinks=False):
        base = Path(directory)
        for name in folders:
            path = base/name
            if path.is_symlink() or path.relative_to(snapshot).as_posix() not in allowed_dirs:
                return False
        for name in files:
            path = base/name
            relative = path.relative_to(snapshot).as_posix()
            if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
                return False
            if relative != 'manifest.json' and not owns(relative):
                return False
    return True


def install_file(source: Path, target: Path):
    source = safe_path(source, allow_releases=True)
    target = safe_path(target, write=True, allow_releases=True)
    require(owns(artifact_name(source)) and owns(artifact_name(target)), 'Unowned news file install')
    require(source.is_file(), 'Missing news source')
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.' + target.name + '-', suffix='.install', dir=target.parent)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(source.read_bytes())
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def install_bundle(source: Path, public: Path, files: list[str], manifest=None):
    """Rollback only canonical news writes; preflight all paths before beforeimages."""
    source = checked_root(source, releases=True)
    public = checked_root(public, write=True)
    require(all(owns(name) for name in files), 'Unowned news install path')
    targets = set(files)
    if manifest is not None:
        require(manifest.get('artifactScope') == NEWS_SCOPE and set(manifest.get('files', {})) == targets,
                'Invalid news install manifest')
        targets |= {p.relative_to(public).as_posix() for p in artifacts(public)} | {'data/release.json'}
    for name in files:
        require(safe_path(source/name, allow_releases=True).is_file(), 'Missing news source')
    for name in targets:
        path = safe_path(public/name, write=True, allow_releases=True)
        require(not path.exists() or path.is_file(), 'News target is not a file')
    before = {name: (public/name).read_bytes() if (public/name).is_file() else None for name in targets}
    try:
        for name in files:
            install_file(source/name, public/name)
        if manifest is not None:
            for name in targets - set(files) - {'data/release.json'}:
                (public/name).unlink(missing_ok=True)
            write_json_atomic(public/'data/release.json', manifest)
    except BaseException:
        for name, content in before.items():
            target = safe_path(public/name, write=True, allow_releases=True)
            if content is None:
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
        raise


def verify_snapshot(snapshot: Path):
    snapshot = checked_root(snapshot, releases=True)
    manifest = read_json(snapshot/'manifest.json')
    require(isinstance(manifest, dict) and manifest.get('schemaVersion') == 1
            and manifest.get('releaseId') == snapshot.name and bool(RELEASE_ID.fullmatch(snapshot.name)),
            'Invalid snapshot manifest')
    scope = manifest.get('artifactScope')
    require(scope is None or scope == NEWS_SCOPE, 'Unknown snapshot artifact scope')
    entries = manifest.get('files')
    require(isinstance(entries, dict) and bool(entries), 'Missing snapshot files')
    expected = {}
    for name, digest in entries.items():
        if name == 'data/research.json' and 'artifactScope' not in manifest:
            continue  # Historical paper bytes are outside the news restore contract.
        require(owns(name), 'Unowned snapshot path')
        require(isinstance(digest, str) and bool(re.fullmatch(r'[0-9a-f]{64}', digest)), 'Invalid news checksum')
        expected[name] = digest
    actual = {p.relative_to(snapshot).as_posix() for p in artifacts(snapshot, include_versions=True)}
    require(bool(expected) and set(expected) == actual, 'Snapshot file set differs')
    for name, digest in expected.items():
        require(hashlib.sha256(safe_path(snapshot/name, allow_releases=True).read_bytes()).hexdigest() == digest,
                'Snapshot checksum differs')
    require(manifest.get('basePath') == f'./releases/{snapshot.name}/', 'Invalid snapshot base path')
    return {**manifest, 'artifactScope': NEWS_SCOPE, 'files': expected}


def preflight_public(public):
    public = checked_root(public, write=True)
    for path in [*artifacts(public, include_versions=True), public/'data/release.json', public/'releases']:
        safe_path(path, write=True, allow_releases=True)
    return public


@contextmanager
def publication_lock(public):
    root = Path(tempfile.gettempdir()) / f'frontier-news-locks-{os.getuid()}'
    try:
        root.mkdir(mode=0o700)
    except FileExistsError:
        pass
    require(not root.is_symlink() and root.is_dir() and root.stat().st_uid == os.getuid()
            and root.stat().st_mode & 0o777 == 0o700, 'Unsafe publication lock directory')
    key = hashlib.sha256(str(safe_path(public)).encode()).hexdigest()
    fd = os.open(root / (key + '.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        require(os.fstat(fd).st_nlink == 1 and os.fstat(fd).st_uid == os.getuid(), 'Unsafe publication lock file')
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def revision_changes(previous, current):
    old = {item['id']:item for item in previous['items']}
    new = {item['id']:item for item in current['items']}
    fields = ['title','originalTitle','summary','displayTranslation','sources','keyFacts']
    return {'added':sorted(new.keys()-old.keys()), 'removed':sorted(old.keys()-new.keys()),
            'corrected':sorted(k for k in old.keys() & new.keys()
                               if any(old[k].get(f) != new[k].get(f) for f in fields))}


def promote(stage: Path, public: Path, mode: str, release_id: str, code_revision: str,
            *, revision_reason='', base_release_id='', now=None, base_stream_hashes=None):
    with publication_lock(public):
        return _promote(stage, public, mode, release_id, code_revision,
                        revision_reason=revision_reason, base_release_id=base_release_id, now=now,
                        base_stream_hashes=base_stream_hashes)


def stream_hashes(public):
    return {name:hashlib.sha256(safe_path(public/name).read_bytes()).hexdigest() for name in STREAM_FILES}


def _promote(stage, public, mode, release_id, code_revision, *, revision_reason='', base_release_id='', now=None,
             base_stream_hashes=None):
    stage = checked_root(stage)
    public = preflight_public(public)
    if base_stream_hashes is not None:
        require(base_stream_hashes == stream_hashes(public), 'Deepread recovery base stream changed; retry from current data')
    validate_publication(stage, mode)
    if mode == 'stream':
        install_bundle(stage, public, list(STREAM_FILES))
        return None
    require(bool(RELEASE_ID.fullmatch(release_id)), 'Invalid release ID')
    target = public / 'releases' / release_id
    safe_path(target, write=True, allow_releases=True)
    require(not target.exists(), 'Release IDs are immutable')
    incoming = read_json(stage/'data/news.json')
    current = read_json(public/'data/release.json') if (public/'data/release.json').exists() else None
    now = now or datetime.now(timezone.utc)
    revision = None
    if current:
        current = verify_snapshot(public/'releases'/current['releaseId'])
        require(incoming['editionDate'] >= current['editionDate'], 'Cannot replace a newer formal edition')
        if incoming['editionDate'] == current['editionDate'] and not revision_reason.strip():
            return current
    if revision_reason.strip():
        require(current and incoming['editionDate'] == current['editionDate']
                and base_release_id == current['releaseId'] and 4 <= len(revision_reason.strip()) <= 220,
                'Correction requires same day, current base and a meaningful reason')
        old_revision = current.get('revision') or {}
        revision = {'number':old_revision.get('number',0)+1,
                    'initialReleaseId':old_revision.get('initialReleaseId', current['releaseId']),
                    'previousReleaseId':current['releaseId'], 'reason':revision_reason.strip(),
                    'updatedAt':now.isoformat(),
                    'changes':revision_changes(read_json(public/'releases'/current['releaseId']/'data/news.json'), incoming)}
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.building-', dir=target.parent))
    try:
        copy_news(stage, temporary)
        news = read_json(temporary / 'data/news.json')
        edition = news['editionDate']
        if revision:
            news['publicationRevision'] = revision
            write_json_atomic(temporary/'data/news.json', news, allow_releases=True)
            write_json_atomic(temporary/f'data/archive/{edition}.json', news, allow_releases=True)
        deep_date = read_json(temporary/'data/deepread.json')['editionDate']
        for path in [*(temporary/'data'/name for name in sorted(NEWS_TOP)),
                     temporary / f'data/archive/{edition}.json', temporary / 'data/archive/index.json', temporary / 'data/archive/search-index.json',
                     *([temporary / f'data/deepread/{edition}.json'] if deep_date == edition else []), temporary / 'data/deepread/index.json']:
            content = read_json(path)
            content['releaseId'] = release_id
            write_json_atomic(path, content, allow_releases=True)
        manifest = {'schemaVersion': 1, 'artifactScope': NEWS_SCOPE, 'releaseId': release_id, 'editionDate': edition,
                    'publishedAt': now.isoformat(), 'codeRevision': code_revision,
                    'deepreadEditionDate':deep_date, 'revision':revision,
                    'generationRevision': read_json(temporary / 'data/deepread.json')['generationRevision'],
                    'basePath': f'./releases/{release_id}/'}
        from publication_clock import publication_timing
        manifest.update({k:v for k,v in publication_timing(edition, now).items() if k != 'waitSeconds'})
        # A compact, immutable edition keeps copied links alive after the seven
        # full browsing snapshots expire. It does not duplicate all archives.
        version = {'schemaVersion':1, 'manifest':dict(manifest),
                   'news':read_json(temporary/'data/news.json'),
                   'deepread':read_json(temporary/'data/deepread.json')}
        write_json_atomic(temporary/f'data/edition-versions/{release_id}.json', version, allow_releases=True)
        manifest['files'] = {str(p.relative_to(temporary)):hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in artifacts(temporary, include_versions=True)}
        write_json_atomic(temporary / 'manifest.json', manifest, allow_releases=True)
        os.replace(temporary, target)
        verify_snapshot(target)
        install_bundle(target, public, list(manifest['files']), manifest)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        # An unreferenced complete snapshot is safe and can be inspected after a failed install.
        raise
    prune_snapshots(target.parent, release_id, revision)
    return manifest


def prune_snapshots(releases: Path, release_id: str, revision=None):
    """Keep seven full snapshots, always including the current release and its revision bases.

    Older revisions stay readable through data/edition-versions, so only the
    current chain needs full snapshots (deepread recovery reads its initial one).
    """
    snapshots = []
    protected = {release_id}
    if revision:
        protected.update([revision['initialReleaseId'], revision['previousReleaseId']])
    for path in releases.iterdir():
        if path.is_symlink() or not path.is_dir() or not RELEASE_ID.fullmatch(path.name) or not pure_news_snapshot(path):
            continue
        try:
            retained = verify_snapshot(path)
            published_at = datetime.fromisoformat(retained['publishedAt'])
            require(published_at.tzinfo is not None, 'Missing snapshot timezone')
        except (ValueError, OSError, KeyError, TypeError):
            continue  # Foreign or damaged releases are not ours to remove.
        snapshots.append((published_at, path.name, path))
    ordinary = [entry for entry in sorted(snapshots, reverse=True) if entry[1] not in protected]
    for _, _, path in ordinary[max(0, RETAINED_SNAPSHOTS - len(protected)):]:
        shutil.rmtree(path)


def restore(public: Path, release_id: str):
    with publication_lock(public):
        return _restore(public, release_id)


def _restore(public, release_id):
    public = preflight_public(public)
    require(bool(RELEASE_ID.fullmatch(release_id)), 'Invalid release ID')
    snapshot = public / 'releases' / release_id
    manifest = verify_snapshot(snapshot)
    validate_publication(snapshot, 'daily', manifest['editionDate'], snapshot=True)
    install_bundle(snapshot, public, list(manifest['files']), manifest)
    return manifest


def record_failure(public: Path, mode: str, message: str, *, expected_date=None, now=None):
    with publication_lock(public):
        return _record_failure(public, mode, message, expected_date=expected_date, now=now)


def _record_failure(public, mode, message, *, expected_date=None, now=None):
    require(mode in {'daily', 'stream'}, 'Invalid publication mode')
    public = checked_root(public, write=True)
    path = public / 'data' / ('stream-status.json' if mode == 'stream' else 'status.json')
    path = safe_path(path, write=True)
    try:
        previous = read_json(path)
    except ValueError:
        previous = {}
    now = now or datetime.now(timezone.utc)
    previous.update(state='failed', lastAttemptAt=now.isoformat(), message=message)
    if mode == 'daily':
        from publication_clock import publication_timing
        from zoneinfo import ZoneInfo
        attempt_date = expected_date or now.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
        previous['attemptEditionDate'] = attempt_date
        previous.update({k:v for k,v in publication_timing(attempt_date,now).items() if k != 'waitSeconds'})
        current = read_json(public/'data/release.json') if (public/'data/release.json').exists() else {}
        if current.get('releaseId') and current.get('editionDate') == attempt_date:
            previous.update(delayed=False, delayMinutes=0)
    write_json_atomic(path, previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'validate', 'promote', 'fail', 'restore'])
    parser.add_argument('--public', type=Path, default=Path('public'))
    parser.add_argument('--stage', type=Path)
    parser.add_argument('--mode', choices=['daily', 'stream'], default='daily')
    parser.add_argument('--release-id')
    parser.add_argument('--code-revision', default=os.getenv('GITHUB_SHA', 'local'))
    parser.add_argument('--expected-date')
    parser.add_argument('--revision-reason', default='')
    parser.add_argument('--base-release-id', default='')
    parser.add_argument('--message', default='本次生成或发布校验失败，已保留上一期合格内容。')
    args = parser.parse_args()
    try:
        if args.action in {'prepare', 'validate', 'promote'}:
            require(args.stage is not None, '--stage is required')
        if args.action == 'prepare':
            prepare_stage(args.public, args.stage)
        elif args.action == 'validate':
            validate_publication(args.stage, args.mode, args.expected_date)
        elif args.action == 'promote':
            validate_publication(args.stage, args.mode, args.expected_date)
            rid = args.release_id or datetime.now(timezone.utc).strftime('r%Y%m%dT%H%M%S-') + uuid4().hex[:8]
            promote(args.stage, args.public, args.mode, rid, args.code_revision,
                    revision_reason=args.revision_reason, base_release_id=args.base_release_id)
        elif args.action == 'restore':
            require(bool(args.release_id), '--release-id is required')
            restore(args.public, args.release_id)
        else:
            record_failure(args.public, args.mode, args.message, expected_date=args.expected_date)
    except (ValueError, OSError) as exc:
        print(f'Publication refused: {exc}')
        return 1
    print(f'Publication {args.action}: OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
