"""Exercise the scheduled runner using the accepted offline source corpus."""
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import classic_publication as pub
import classic_daily as daily


class ClassicDailyTests(unittest.TestCase):
    def test_actual_date_idempotency_pending_and_namespace_isolation(self):
        before = {p: p.read_bytes() for folder in ('research', 'public/data')
                  for p in (ROOT / folder).rglob('*') if p.is_file()}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'public/classics'
            first = daily.run(root, now=datetime.fromisoformat('2026-10-04T06:06:52+08:00'))
            self.assertEqual(first['editionDate'], '2026-10-04')
            self.assertEqual(first['publishedDayCount'], 1)
            self.assertEqual(len(first['paperIds']), 2)
            pointer = (root / 'release.json').read_bytes()
            again = daily.run(root, now=datetime.fromisoformat('2026-10-04T19:00:00+08:00'))
            self.assertEqual(again, first)
            self.assertEqual((root / 'release.json').read_bytes(), pointer)
            pending = daily.run(root, now=datetime.fromisoformat('2026-10-18T08:00:00+08:00'))
            self.assertEqual(pending['state'], 'pending')
            self.assertEqual(pending['editionDate'], '2026-10-04')
            self.assertTrue(pending['lowStock'])
            self.assertEqual(set(pub.read_current(root)['archive']['editions']), {'2026-10-04'})
        self.assertTrue(all(p.read_bytes() == data for p, data in before.items()))

    def test_invalid_queue_does_not_create_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'public/classics'
            queue = Path(tmp) / 'bad-queue.json'
            queue.write_text(json.dumps({'schemaVersion': 900}))
            with self.assertRaises(ValueError):
                daily.run(root, queue_path=queue, now=datetime.fromisoformat('2026-10-04T08:00:00+08:00'))
            self.assertFalse((root / 'release.json').exists())
