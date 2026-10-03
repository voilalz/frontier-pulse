"""Publish two authored test dates from the accepted offline scholarly corpus."""
import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import classic_papers as cp
import classic_publication as pub
from build_fixture import build as build_news


def build(directory, news=False):
    directory = Path(directory)
    public = build_news(directory) if news else directory / 'public'
    if not news:
        public.mkdir(parents=True, exist_ok=True)
        for name in ('assets', 'index.html', 'sw.js', 'favicon.svg'):
            source = ROOT / 'public' / name
            if source.is_dir(): shutil.copytree(source, public / name, dirs_exist_ok=True)
            else: shutil.copy2(source, public / name)
    shutil.rmtree(public / 'classics', ignore_errors=True)
    pool = cp.load_ready_pool(ROOT, cp.beijing_date('2026-10-04'))
    queue = cp.read_json(ROOT / 'research/classic-publishing/queue.json')
    for day in ('2026-10-03', '2026-10-04'):
        pub.publish(public / 'classics', day, queue, pool,
                    now=datetime.fromisoformat(day + 'T08:10:00+08:00'))
    return public


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory')
    parser.add_argument('--news', action='store_true')
    args = parser.parse_args()
    print(build(args.directory, args.news))
