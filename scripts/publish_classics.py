#!/usr/bin/env python3
"""Offline classic preparation/publication CLI (Linux/POSIX).

Exit 0: complete operation/inspection (prepare may report an honest short queue).
Exit 2: invalid input or failed operation. Exit 3: pending publication committed.
"""
from __future__ import annotations

import argparse
import copy
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import classic_papers as cp
import classic_publication as pub

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_QUEUE = PROJECT / 'research/classic-publishing/queue.json'


def _path(value):
    path = Path(value).absolute()
    for parent in (path, *path.parents):
        cp.require(not parent.is_symlink(), 'Symlinked CLI path or parent refused')
    return path.resolve()


def _root(value):
    path = _path(value)
    cp.require(not path.is_relative_to(PROJECT) or path == PROJECT / 'public/classics',
               'Classic publication cannot write trusted project inputs')
    return pub._namespace(path)


def _output(value):
    path = _path(value)
    cp.require(path.suffix == '.json', 'Queue output must be a JSON file')
    cp.require(not path.is_relative_to(PROJECT) or path == DEFAULT_QUEUE,
               'Queue output cannot overwrite trusted project inputs or news')
    cp.require(not any((p.name in {'data', 'releases'} and p.parent.name == 'public') or p.name == 'classics'
                       for p in path.parents), 'Queue output cannot overwrite a public namespace')
    if path.exists():
        cp.require(path.is_file() and path.stat().st_nlink == 1, 'Hardlinked/non-file queue output refused')
        cp.validate_queue(cp.read_json(path))
    return path


def _write_queue(path, queue):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.queue-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as file:
            file.write(cp.canonical(queue))
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _summary(state):
    status = state['status']
    return dict(status, releaseId=state['manifest']['releaseId'],
                publishedDayCount=len(state['archive']['editions']),
                queueDayCount=len(state['queue']['slots']),
                paperIds=[p['id'] for p in state['edition']['items']])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'publish', 'restore', 'inspect'):
        command = sub.add_parser(name)
        command.add_argument('--root', type=Path, default=PROJECT / 'public/classics')
        command.add_argument('--now', help='Aware ISO clock; omit for current Beijing time')
        if name in ('prepare', 'publish'):
            command.add_argument('--date', help='ISO recommendation date; defaults to Beijing clock date')
            command.add_argument('--queue', type=Path, default=DEFAULT_QUEUE)
        if name == 'prepare':
            command.add_argument('--output', type=Path, default=DEFAULT_QUEUE)
        if name == 'restore':
            command.add_argument('--release-id', required=True)
    args = parser.parse_args(argv)
    try:
        now = datetime.fromisoformat(args.now) if args.now else datetime.now(cp.BEIJING)
        today = cp.beijing_date(now)
        root = _root(args.root)
        if args.command == 'prepare':
            output = _output(args.output)
            target = cp.beijing_date(args.date) if args.date else today
            pool = cp.load_ready_pool(PROJECT, today)
            current = pub.read_current(root)
            archive = current['archive'] if current else cp.envelope('classicArchive', editions={})
            existing = current['queue'] if current else cp.envelope('classicQueue', slots={})
            source = _path(args.queue)
            existing = copy.deepcopy(existing)
            for path in dict.fromkeys((output, source)):
                if not path.exists():
                    continue
                incoming = cp.read_json(path)
                cp.validate_queue(incoming, pool, archive)
                for day, slot in incoming['slots'].items():
                    cp.require(day not in existing['slots'] or existing['slots'][day] == slot,
                               'Cannot replace an active locked queue slot')
                    existing['slots'][day] = slot
            queue, stock = cp.prepare_queue(pool, target, existing_queue=existing, archive=archive)
            _write_queue(output, queue)
            result = dict(command='prepare', readyPoolCount=len(pool), queueDayCount=len(queue['slots']),
                          inventory=stock)
            code = 0
        elif args.command == 'publish':
            target = cp.beijing_date(args.date) if args.date else today
            queue = cp.read_json(_path(args.queue))
            pool = cp.load_ready_pool(PROJECT, today)
            state = pub.publish(root, target, queue, pool, now=now)
            result = _summary(state)
            code = 3 if state['status']['state'] == 'pending' else 0
        elif args.command == 'restore':
            result = _summary(pub.restore(root, args.release_id, now=now))
            code = 0
        else:
            state = pub.read_current(root)
            cp.require(state is not None, 'No current classic publication')
            result = _summary(state)
            code = 0
        sys.stdout.buffer.write(cp.canonical(result))
        return code
    except (ValueError, TypeError, OSError, OverflowError) as exc:
        print('classic operation failed: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
