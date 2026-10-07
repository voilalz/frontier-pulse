"""Repair only a formal edition's deep read, retaining its original news selection."""
from __future__ import annotations

import argparse
import copy
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import publication
from deepread_editorial import build_daily_deepread
from deepread_quality import choose_readable_deepread, deepread_status, validate_readable
from update_news import archive_deepread, load_config, resolve_ai_runtime, request_structured_json, write_json_atomic


def recover(public, stage, config, now, runtime, request_json, code_revision=''):
    edition = now.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
    public = publication.preflight_public(public)
    release_path = public / 'data/release.json'
    if not release_path.exists():
        return {'state':'skipped', 'changed':False, 'reason':'formal-edition-missing'}
    release = publication.read_json(release_path)
    if release.get('editionDate') != edition:
        return {'state':'skipped', 'changed':False, 'reason':'formal-edition-not-current'}
    publication.verify_snapshot(public / 'releases' / release['releaseId'])
    source_release_id = (release.get('revision') or {}).get('initialReleaseId', release['releaseId'])
    snapshot = public / 'releases' / source_release_id
    publication.verify_snapshot(snapshot)
    current = publication.read_json(public / 'data/deepread.json')
    try:
        validate_readable(current, edition)
        if current.get('readerStatus') == 'complete':
            return {'state':'ok', 'changed':False, 'reason':'deepread-already-complete'}
    except (ValueError, KeyError, TypeError):
        pass
    publication.prepare_stage(public, stage)
    base_stream_hashes = publication.stream_hashes(stage)
    report = publication.read_json(snapshot / 'data/news.json')
    stream = publication.read_json(snapshot / 'data/stream.json')
    # Reuse the original publication's source window and immutable evidence.
    # A newer stream update must not silently change this edition's material.
    selection_time = datetime.fromisoformat(report['generatedAt'].replace('Z', '+00:00'))
    if selection_time.tzinfo is None or selection_time.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat() != edition:
        raise ValueError('Formal edition has an invalid source window')
    items = {item['id']:copy.deepcopy(item) for item in stream['items']}
    items.update({item['id']:copy.deepcopy(item) for item in report['items']})
    registry = publication.read_json(snapshot / 'data/events.json')
    try:
        draft = build_daily_deepread(items.values(), config, selection_time, runtime, request_json,
                                     event_registry=registry)
    except Exception as exc:
        logging.warning('Deepread recovery failed: %s', type(exc).__name__)
        # Do not expose provider exception bodies or credentials in public data.
        draft = {'generationStatus':'failed', 'warnings':['深读恢复请求未成功完成。'],
                 'contentFailures':['deepread-recovery-exception']}
    draft['generatedAt'] = now.isoformat().replace('+00:00', 'Z')
    previous = [current]
    index = publication.read_json(stage / 'data/deepread/index.json')
    for entry in index.get('editions', []):
        date = entry.get('editionDate', '')
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', date) and date <= edition:
            previous.append(publication.read_json(stage / 'data/deepread' / f'{date}.json'))
    reader = choose_readable_deepread(draft, previous, edition)
    write_json_atomic(stage / 'data/deepread.json', reader)
    if reader['readerStatus'] != 'retained':
        archive_deepread(reader, stage / 'data/deepread', config)
    status = publication.read_json(stage / 'data/status.json')
    status['deepread'] = deepread_status(reader, edition)
    status['deepread']['lastAttemptAt'] = draft['generatedAt']
    write_json_atomic(stage / 'data/status.json', status)
    # Promotion creates a dated correction with the initial release intact;
    # its compare-and-swap rejects recovery based on a superseded edition.
    publication.validate_publication(stage, 'daily', edition)
    incoming = publication.read_json(stage / 'data/news.json')
    if incoming['items'] != report['items'] or incoming['brief'] != report['brief']:
        raise ValueError('Deepread recovery cannot change the daily selection')
    release_id = 'r' + now.strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
    promoted = publication.promote(stage, public, 'daily', release_id, code_revision,
        revision_reason='单独恢复当日深读正文与观察，保留日报选稿。', base_release_id=release['releaseId'], now=now,
        base_stream_hashes=base_stream_hashes)
    return {**status['deepread'], 'changed':True, 'releaseId':promoted['releaseId']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public', type=Path, default=Path('public'))
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path('config/news_config.json'))
    parser.add_argument('--code-revision', default='')
    parser.add_argument('--github-output', type=Path)
    args = parser.parse_args()
    config = load_config(args.config)
    result = recover(args.public, args.stage, config, datetime.now(timezone.utc), resolve_ai_runtime(config),
                     request_structured_json, args.code_revision)
    if args.github_output:
        with args.github_output.open('a') as handle:
            handle.write(f"state={result['state']}\nchanged={str(result['changed']).lower()}\n")
    print(json.dumps(result, ensure_ascii=False))
    # The workflow commits an independent failure status before failing its
    # final check. It must not discard diagnostics or fail the daily job.


if __name__ == '__main__':
    main()
