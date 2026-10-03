#!/usr/bin/env python3
"""Publish the actual Beijing day from accepted, offline classic inventory."""
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import classic_papers as cp
import classic_publication as pub
from publish_classics import PROJECT, DEFAULT_QUEUE, _root, _path, _summary


def run(root, queue_path=DEFAULT_QUEUE, now=None):
    now = now or datetime.now(cp.BEIJING)
    today = cp.beijing_date(now)
    root = _root(root)
    queue = cp.read_json(_path(queue_path))
    pool = cp.load_ready_pool(PROJECT, today)
    return _summary(pub.publish(root, today, queue, pool, now=now))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=PROJECT / 'public/classics')
    parser.add_argument('--queue', type=Path, default=DEFAULT_QUEUE)
    args = parser.parse_args(argv)
    try:
        result = run(args.root, args.queue)
        sys.stdout.buffer.write(cp.canonical(result))
        if result.get('lowStock'):
            print('::warning::Classic ready inventory is below 14 papers', file=sys.stderr)
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as output:
                output.write(f"Classic publication: {result['state']}\n\nRecommendation date: {result['editionDate']}\n\nReady papers: {result['readyPaperCount']}\n")
        return 0
    except (ValueError, TypeError, OSError, OverflowError) as exc:
        print('classic daily publication failed: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
