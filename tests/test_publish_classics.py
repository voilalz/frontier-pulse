"""CLI contracts on accepted inputs, with publication confined to temporary dirs."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/publish_classics.py'
NOW = '2026-10-03T18:00:00+08:00'


class ClassicCLITests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(CLI.is_file(), 'independent classic CLI is not implemented')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'public/classics'
        self.queue = self.base / 'queue.json'
        news = self.base / 'public/data'
        news.mkdir(parents=True)
        (news / 'news.json').write_bytes(b'news sentinel\n')
        (news / 'research.json').write_bytes(b'research sentinel\n')

    def run_cli(self, command, *args, now=NOW, code=0, env=None):
        run = subprocess.run([sys.executable, str(CLI), command, '--root', str(self.root),
                              '--now', now, *map(str, args)], cwd=ROOT, env=env,
                             text=True, capture_output=True)
        self.assertEqual(run.returncode, code, run.stdout + run.stderr)
        if code == 0 or code == 3:
            return json.loads(run.stdout)
        self.assertTrue(run.stderr.strip(), 'errors must have a useful diagnostic')
        return run

    def prepare(self, **kw):
        return self.run_cli('prepare', '--output', self.queue, '--queue', self.queue, **kw)

    def publish(self, day='2026-10-03', **kw):
        return self.run_cli('publish', '--date', day, '--queue', self.queue, **kw)

    def assert_news(self):
        self.assertEqual((self.base / 'public/data/news.json').read_bytes(), b'news sentinel\n')
        self.assertEqual((self.base / 'public/data/research.json').read_bytes(), b'research sentinel\n')

    def test_prepare_publish_inspect_restore_and_idempotent_rerun(self):
        report = self.prepare()
        self.assertEqual(report['inventory']['futurePaperCount'], 28)
        q = json.loads(self.queue.read_text())
        self.assertEqual(len(q['slots']), 15)
        first = self.publish()
        first_id = first['releaseId']
        pointer = (self.root / 'release.json').read_bytes()
        self.publish(now='2026-10-05T12:00:00+08:00')
        self.assertEqual((self.root / 'release.json').read_bytes(), pointer)
        self.publish('2026-10-04', now='2026-10-04T12:00:00+08:00')
        restored = self.run_cli('restore', '--release-id', first_id,
                                now='2026-10-05T12:00:00+08:00')
        self.assertEqual(restored['editionDate'], '2026-10-03')
        inspected = self.run_cli('inspect', now='2026-10-05T12:00:00+08:00')
        self.assertEqual(inspected['latestPublishedDate'], '2026-10-04')
        self.assertEqual(inspected['publishedDayCount'], 2)
        self.assertEqual(inspected['queueDayCount'], 15)
        self.assert_news()

    def test_future_publication_is_rejected_without_install(self):
        self.prepare()
        self.publish('2026-10-04', code=2)
        self.assertFalse((self.root / 'release.json').exists())
        self.assert_news()

    def test_naive_clock_and_invalid_calendar_date_are_errors(self):
        self.prepare(now='2026-10-03T18:00:00', code=2)
        self.run_cli('prepare', '--date', '2026-02-30', '--output', self.queue, code=2)
        self.assertFalse(self.queue.exists())

    def test_pending_first_publication_has_explicit_status_and_exit_three(self):
        self.prepare()
        q = json.loads(self.queue.read_text())
        q['slots'] = {}
        self.queue.write_text(json.dumps(q))
        result = self.publish(code=3)
        self.assertEqual(result['state'], 'pending')
        self.assertIsNone(result['editionDate'])
        self.assertEqual(result['message'], '今日待更新')
        self.assert_news()

    def test_input_output_and_hardlink_alias_cannot_overwrite_frozen_guide(self):
        source = ROOT / 'research/classic-guides/AI.json'
        original = source.read_bytes()
        self.run_cli('prepare', '--output', source, code=2)
        alias = self.base / 'alias.json'
        os.link(source, alias)
        self.run_cli('prepare', '--output', alias, code=2)
        self.assertEqual(source.read_bytes(), original)

    def test_symlink_output_or_parent_is_refused(self):
        guide = ROOT / 'research/classic-guides/SLAM.json'
        self.queue.symlink_to(guide)
        self.prepare(code=2)
        self.queue.unlink()
        link = self.base / 'linked'
        link.symlink_to(ROOT / 'research/classic-guides', target_is_directory=True)
        self.run_cli('prepare', '--output', link / 'queue.json', code=2)
        self.assertFalse((ROOT / 'research/classic-guides/queue.json').exists())

    def test_existing_news_and_manifest_cannot_be_queue_output(self):
        for relative in ('public/data/news.json', 'public/data/research.json', 'public/data/queue.json'):
            with self.subTest(relative=relative):
                self.run_cli('prepare', '--output', self.base / relative, code=2)
        self.root.mkdir(parents=True)
        pointer = self.root / 'release.json'
        pointer.write_bytes(b'pointer sentinel')
        self.run_cli('prepare', '--output', pointer, code=2)
        self.assertEqual(pointer.read_bytes(), b'pointer sentinel')
        self.assert_news()

    def test_namespace_inside_news_or_trusted_inputs_is_refused(self):
        self.prepare()
        for root in (self.base / 'public/data/classics', ROOT / 'research/classic-guides/classics'):
            self.root = root
            self.publish(code=2)
            self.assertFalse(root.exists())

    def test_reprepare_retains_active_locked_slots_even_if_input_is_truncated(self):
        self.prepare()
        before = json.loads(self.queue.read_text())
        self.publish()
        missing = json.loads(self.queue.read_text())
        del missing['slots']['2026-10-10']
        self.queue.write_text(json.dumps(missing))
        self.prepare(now='2026-10-04T12:00:00+08:00')
        after = json.loads(self.queue.read_text())
        self.assertEqual(after['slots']['2026-10-10'], before['slots']['2026-10-10'])
        self.assertEqual(after['slots']['2026-10-03'], before['slots']['2026-10-03'])

    def test_distinct_source_and_output_preserve_all_output_reservations(self):
        missing = self.base / 'missing.json'
        self.run_cli('prepare', '--queue', missing, '--output', self.queue,
                     now='2026-10-08T12:00:00+08:00')
        before = self.queue.read_bytes()
        result = self.run_cli('prepare', '--queue', missing, '--output', self.queue)
        self.assertEqual(self.queue.read_bytes(), before)
        self.assertEqual(result['inventory']['firstMissingDate'], '2026-10-03')

    def test_conflicting_separate_source_cannot_replace_existing_output_slot(self):
        self.prepare()
        before = self.queue.read_bytes()
        incoming = json.loads(before)
        incoming['slots']['2026-10-08']['items'] = incoming['slots']['2026-10-13']['items']
        incoming['slots'] = {'2026-10-08': incoming['slots']['2026-10-08']}
        source = self.base / 'other.json'
        source.write_text(json.dumps(incoming))
        self.run_cli('prepare', '--queue', source, '--output', self.queue, code=2)
        self.assertEqual(self.queue.read_bytes(), before)

    def test_queue_output_and_publication_cannot_write_legacy_release_tree(self):
        self.prepare()
        legacy = self.base / 'public/releases/legacy'
        legacy.mkdir(parents=True)
        sentinel = legacy / 'news.json'
        sentinel.write_bytes(b'legacy snapshot\n')
        self.run_cli('prepare', '--output', legacy / 'queue.json', code=2)
        self.root = legacy / '..' / 'legacy' / 'classics'
        self.publish(code=2)
        self.assertEqual(list(legacy.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b'legacy snapshot\n')

    def test_exhausted_real_pool_reports_gap_without_fabricating_papers(self):
        self.prepare()
        before = self.queue.read_bytes()
        report = self.prepare(now='2026-10-18T12:00:00+08:00')
        self.assertEqual(report['inventory']['completeDays'], 0)
        self.assertEqual(report['inventory']['firstMissingDate'], '2026-10-18')
        self.assertTrue(report['inventory']['lowStock'])
        self.assertEqual(self.queue.read_bytes(), before)

    def test_duplicate_json_keys_and_changed_frozen_body_fail_closed(self):
        self.prepare()
        q = json.loads(self.queue.read_text())
        self.queue.write_text('{"kind":"classicQueue","kind":"classicQueue"}')
        self.publish(code=2)
        q['slots']['2026-10-03']['items'][0]['overview'] = '变' * 160
        self.queue.write_text(json.dumps(q))
        self.publish(code=2)
        self.assertFalse((self.root / 'release.json').exists())

    def test_offline_commands_work_when_network_is_disabled(self):
        blocker = self.base / 'sitecustomize.py'
        blocker.write_text('import socket\ndef blocked(*a, **k):\n    raise AssertionError("network forbidden")\nsocket.socket=blocked\nsocket.create_connection=blocked\n')
        env = dict(os.environ, PYTHONPATH=str(self.base))
        self.prepare(env=env)
        self.publish(env=env)
        self.assert_news()

    def test_inspect_without_current_or_restore_with_bad_id_has_explicit_error(self):
        self.run_cli('inspect', code=2)
        self.run_cli('restore', '--release-id', '../news', code=2)
        self.assertFalse((self.root / 'release.json').exists())


if __name__ == '__main__':
    unittest.main()
