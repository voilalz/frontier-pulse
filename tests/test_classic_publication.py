"""Real-filesystem classic publication and interruption/recovery contracts."""
import copy
import fcntl
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from test_classic_papers import make_pool

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import classic_papers as cp
try:
    import classic_publication as pub
except ImportError:
    pub = None


def clock(day):
    return datetime.fromisoformat(day + 'T12:00:00+08:00')


class ClassicPublicationTests(unittest.TestCase):
    def test_classics_inside_legacy_release_snapshot_is_refused_before_writing(self):
        legacy = self.site / 'releases/legacy-snapshot'
        legacy.mkdir(parents=True)
        sentinel = legacy / 'news.json'
        sentinel.write_bytes(b'immutable legacy snapshot\n')
        self.root = legacy / 'classics'
        with self.assertRaises(ValueError):
            self.publish()
        self.assertFalse(self.root.exists())
        self.assertEqual(list(legacy.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b'immutable legacy snapshot\n')

    def test_post_restore_publication_compares_with_selected_date_and_keeps_latest_history(self):
        first = self.publish()
        self.publish('2026-10-06')
        pub.restore(self.root, first['manifest']['releaseId'], now=clock('2026-10-06'))
        newer = self.publish('2026-10-05', now=clock('2026-10-06'))
        self.assertEqual(newer['edition']['recommendationDate'], '2026-10-05')
        self.assertEqual(newer['status']['latestPublishedDate'], '2026-10-06')
        older = self.publish('2026-10-04', now=clock('2026-10-06'))
        self.assertEqual(older['edition'], newer['edition'])
        self.assertEqual(set(older['archive']['editions']),
                         {'2026-10-03', '2026-10-04', '2026-10-05', '2026-10-06'})

    def test_classics_nested_inside_news_namespace_is_refused(self):
        self.root = self.site / 'data' / 'classics'
        with self.assertRaises(ValueError):
            self.publish()
        self.assertFalse(self.root.exists())
        self.assert_news()

    def setUp(self):
        self.assertIsNotNone(pub, 'independent classic publisher is not implemented')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.site = Path(self.tmp.name) / 'public'
        (self.site / 'data').mkdir(parents=True)
        (self.site / 'data/news.json').write_bytes(b'news sentinel\n')
        (self.site / 'data/research.json').write_bytes(b'legacy research sentinel\n')
        self.root = self.site / 'classics'
        self.pool = make_pool()
        self.queue, _ = cp.prepare_queue(self.pool, '2026-10-03')

    def publish(self, day='2026-10-03', queue=None, now=None, pool=None):
        return pub.publish(self.root, day, self.queue if queue is None else queue,
                           self.pool if pool is None else pool, now=now or clock(day))

    def pointer(self):
        return (self.root / 'release.json').read_bytes()

    def assert_news(self):
        self.assertEqual((self.site / 'data/news.json').read_bytes(), b'news sentinel\n')
        self.assertEqual((self.site / 'data/research.json').read_bytes(), b'legacy research sentinel\n')

    def test_complete_snapshot_binds_full_edition_history_queue_and_status(self):
        state = self.publish()
        m = state['manifest']
        self.assertRegex(m['releaseId'], r'^c-[0-9a-f]{64}$')
        self.assertEqual(m['basePath'], './releases/' + m['releaseId'] + '/')
        self.assertEqual(set(m['files']), {'edition.json', 'archive.json', 'queue.json', 'status.json'})
        edition = state['edition']
        self.assertEqual(edition['recommendationDate'], '2026-10-03')
        self.assertEqual([p['id'] for p in edition['items']], ['fixture:SLAM:1', 'fixture:GNC:1'])
        self.assertEqual(edition['items'][0]['year'], 2000)
        self.assertEqual(state['archive']['editions']['2026-10-03'], edition)
        self.assertEqual(state['status']['readyPaperCount'], 28)
        self.assertEqual(state['queue'], self.queue)
        self.assertEqual(pub.read_current(self.root), state)

    def test_published_date_rerun_is_byte_identical_even_with_later_clock(self):
        self.publish()
        before = self.pointer()
        state = self.publish(now=clock('2026-10-04'))
        self.assertEqual(self.pointer(), before)
        self.assertEqual(state['edition']['publishedAt'], '2026-10-03T12:00:00+08:00')
        self.assertEqual(len(list((self.root / 'releases').iterdir())), 1)

    def test_old_date_backfill_records_history_without_replacing_newer_edition(self):
        self.publish('2026-10-05')
        old = copy.deepcopy(pub.read_current(self.root)['edition'])
        state = self.publish('2026-10-04', now=clock('2026-10-05'))
        self.assertEqual(state['edition'], old)
        self.assertEqual(set(state['archive']['editions']), {'2026-10-04', '2026-10-05'})
        self.assertEqual(state['manifest']['latestPublishedDate'], '2026-10-05')
        self.assertEqual(state['archive']['editions']['2026-10-04']['publishedAt'], '2026-10-05T12:00:00+08:00')

    def test_short_stock_keeps_previous_original_date_and_pending_status(self):
        short, _ = cp.prepare_queue(make_pool(1), '2026-10-03')
        self.publish(queue=short)
        state = self.publish('2026-10-05', queue=short)
        self.assertEqual(state['edition']['recommendationDate'], '2026-10-03')
        self.assertEqual(state['status']['state'], 'pending')
        self.assertEqual(state['status']['message'], '今日待更新')
        self.assertEqual(state['status']['targetDate'], '2026-10-05')
        self.assertEqual(set(state['archive']['editions']), {'2026-10-03'})

    def test_empty_first_publication_is_explicit_pending_not_legacy_or_fabricated(self):
        empty = cp.envelope('classicQueue', slots={})
        state = self.publish(queue=empty)
        self.assertIsNone(state['edition']['recommendationDate'])
        self.assertEqual(state['edition']['items'], [])
        self.assertEqual(state['archive']['editions'], {})
        self.assertEqual(state['status']['state'], 'pending')
        self.assert_news()

    def test_future_publication_and_naive_clock_do_not_change_pointer(self):
        self.publish()
        before = self.pointer()
        for day, now in [('2026-10-04', clock('2026-10-03')), ('2026-10-03', datetime(2026, 10, 3))]:
            with self.subTest(day=day), self.assertRaises(ValueError):
                self.publish(day, now=now)
            self.assertEqual(self.pointer(), before)

    def test_exact_ninety_day_reread_records_previous_real_recommendation(self):
        pool = make_pool(1)
        oldq, _ = cp.prepare_queue(pool, '2026-07-05', days=1)
        old = self.publish('2026-07-05', queue=oldq, pool=pool)
        q, _ = cp.prepare_queue(pool, '2026-10-03', days=1, existing_queue=oldq, archive=old['archive'])
        state = self.publish(queue=q, pool=pool)
        self.assertTrue(all(p['classicReread'] for p in state['edition']['items']))
        self.assertEqual([p['previousRecommendationDate'] for p in state['edition']['items']], ['2026-07-05'] * 2)

    def test_restore_preserves_later_history_and_all_future_reservations(self):
        first = self.publish()
        self.publish('2026-10-04')
        self.publish('2026-10-05')
        state = pub.restore(self.root, first['manifest']['releaseId'], now=clock('2026-10-05'))
        self.assertEqual(state['edition'], first['edition'])
        self.assertEqual(set(state['archive']['editions']), {'2026-10-03', '2026-10-04', '2026-10-05'})
        self.assertEqual(state['queue'], self.queue)
        self.assertEqual(state['manifest']['latestPublishedDate'], '2026-10-05')
        self.assertEqual(state['status']['state'], 'restored')
        self.assertNotEqual(state['manifest']['releaseId'], first['manifest']['releaseId'])

    def test_restore_does_not_reset_cooldown_for_recommendations_made_later(self):
        pool = make_pool(1)
        oldq, _ = cp.prepare_queue(pool, '2026-07-05', days=1)
        old = self.publish('2026-07-05', queue=oldq, pool=pool)
        q, _ = cp.prepare_queue(pool, '2026-10-03', days=1, existing_queue=oldq, archive=old['archive'])
        self.publish(queue=q, pool=pool)
        restored = pub.restore(self.root, old['manifest']['releaseId'], now=clock('2026-10-03'))
        q2, report = cp.prepare_queue(pool, '2026-10-08', days=1,
                                      existing_queue=restored['queue'], archive=restored['archive'])
        self.assertNotIn('2026-10-08', q2['slots'])
        self.assertEqual(report['firstMissingDate'], '2026-10-08')
        self.assertIn('2026-10-03', restored['archive']['editions'])

    def test_publishing_after_restore_uses_locked_next_day_without_repeating(self):
        first = self.publish()
        self.publish('2026-10-04')
        pub.restore(self.root, first['manifest']['releaseId'], now=clock('2026-10-04'))
        state = self.publish('2026-10-05')
        self.assertEqual([p['id'] for p in state['edition']['items']], ['fixture:AI:1', 'fixture:SLAM:2'])
        self.assertEqual(len(state['archive']['editions']), 3)

    def test_removed_incoming_reservation_cannot_erase_locked_future_slot(self):
        self.publish()
        incoming = copy.deepcopy(self.queue)
        del incoming['slots']['2026-10-04']
        state = self.publish('2026-10-04', queue=incoming)
        self.assertEqual([p['id'] for p in state['edition']['items']], ['fixture:CV:1', 'fixture:UAV:1'])

    def test_changed_locked_future_combination_fails_without_public_writes(self):
        self.publish()
        before = self.pointer()
        bad = copy.deepcopy(self.queue)
        bad['slots']['2026-10-04']['items'][0] = copy.deepcopy(next(p for p in self.pool if p['id'] == 'fixture:CV:6'))
        with self.assertRaises(ValueError): self.publish('2026-10-04', queue=bad)
        self.assertEqual(self.pointer(), before)

    def test_pointer_install_interruption_retains_old_readable_state_and_allows_verified_retry(self):
        first = self.publish()
        before = self.pointer()
        real_replace = os.replace
        def fail_pointer(source, target):
            if Path(target).name == 'release.json': raise OSError('simulated pointer install interruption')
            return real_replace(source, target)
        with patch.object(pub.os, 'replace', side_effect=fail_pointer):
            with self.assertRaises(OSError): self.publish('2026-10-04')
        self.assertEqual(self.pointer(), before)
        self.assertEqual(pub.read_current(self.root), first)
        self.assertEqual(len(list((self.root / 'releases').iterdir())), 2)
        state = self.publish('2026-10-04')
        self.assertEqual(state['edition']['recommendationDate'], '2026-10-04')
        self.assertEqual(len(list((self.root / 'releases').iterdir())), 2)

    def test_corrupt_orphan_is_not_reused_or_silently_replaced(self):
        first = self.publish()
        real_replace = os.replace
        def fail_pointer(source, target):
            if Path(target).name == 'release.json': raise OSError('simulated interruption')
            return real_replace(source, target)
        with patch.object(pub.os, 'replace', side_effect=fail_pointer):
            with self.assertRaises(OSError): self.publish('2026-10-04')
        orphan = next(p for p in (self.root / 'releases').iterdir() if p.name != first['manifest']['releaseId'])
        (orphan / 'edition.json').write_text('{}')
        before = self.pointer()
        with self.assertRaises(ValueError): self.publish('2026-10-04')
        self.assertEqual(self.pointer(), before)
        self.assertEqual((orphan / 'edition.json').read_text(), '{}')

    def test_snapshot_write_interruption_leaves_old_pointer_and_no_building_directory(self):
        first = self.publish()
        before = self.pointer()
        with patch.object(pub.os, 'fsync', side_effect=OSError('simulated disk flush failure')):
            with self.assertRaises(OSError): self.publish('2026-10-04')
        self.assertEqual(self.pointer(), before)
        self.assertEqual(pub.read_current(self.root), first)
        self.assertFalse(any(p.name.startswith('.building-') for p in (self.root / 'releases').iterdir()))

    def test_corrupt_target_snapshot_cannot_restore_or_modify_current(self):
        first = self.publish()
        self.publish('2026-10-04')
        (self.root / 'releases' / first['manifest']['releaseId'] / 'edition.json').write_text('{}')
        before = self.pointer()
        with self.assertRaises(ValueError): pub.restore(self.root, first['manifest']['releaseId'], now=clock('2026-10-04'))
        self.assertEqual(self.pointer(), before)

    def test_extra_snapshot_file_and_unsafe_manifest_path_fail_closed(self):
        first = self.publish()
        self.publish('2026-10-04')
        snap = self.root / 'releases' / first['manifest']['releaseId']
        before = self.pointer()
        (snap / 'extra.json').write_text('{}')
        with self.assertRaises(ValueError): pub.restore(self.root, snap.name, now=clock('2026-10-04'))
        (snap / 'extra.json').unlink()
        m = json.loads((snap / 'manifest.json').read_text())
        m['basePath'] = '../data/'
        (snap / 'manifest.json').write_text(json.dumps(m))
        with self.assertRaises(ValueError): pub.restore(self.root, snap.name, now=clock('2026-10-04'))
        self.assertEqual(self.pointer(), before)

    def test_invalid_release_id_or_wrong_namespace_cannot_write_news(self):
        self.publish()
        before = self.pointer()
        for rid in ['../data', '', '.', 'c-not-a-hash', []]:
            with self.subTest(rid=rid), self.assertRaises(ValueError):
                pub.restore(self.root, rid, now=clock('2026-10-03'))
        with self.assertRaises(ValueError): pub.publish(self.site, '2026-10-03', self.queue, self.pool, now=clock('2026-10-03'))
        self.assertEqual(self.pointer(), before)
        self.assert_news()

    def test_symlinked_root_or_parent_is_refused_without_writing_through_it(self):
        outside = Path(self.tmp.name) / 'outside'
        outside.mkdir()
        self.root.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError): self.publish()
        self.assertEqual(list(outside.iterdir()), [])
        self.root.unlink()
        link = Path(self.tmp.name) / 'link'
        link.symlink_to(self.site, target_is_directory=True)
        with self.assertRaises(ValueError): pub.publish(link / 'classics', '2026-10-03', self.queue, self.pool, now=clock('2026-10-03'))
        self.assertFalse(self.root.exists())

    def test_symlinked_pointer_does_not_modify_legacy_research(self):
        self.publish()
        (self.root / 'release.json').unlink()
        (self.root / 'release.json').symlink_to(self.site / 'data/research.json')
        with self.assertRaises(ValueError): self.publish('2026-10-04')
        self.assert_news()

    def test_corrupt_current_pointer_does_not_start_a_new_empty_history(self):
        self.publish()
        (self.root / 'release.json').write_text('{bad json')
        before = self.pointer()
        with self.assertRaises(ValueError): self.publish('2026-10-04')
        self.assertEqual(self.pointer(), before)

    def test_new_publisher_never_modifies_sibling_news_or_old_research(self):
        first = self.publish()
        self.publish('2026-10-04')
        pub.restore(self.root, first['manifest']['releaseId'], now=clock('2026-10-04'))
        self.assert_news()

    def test_overlapping_writer_is_refused_without_losing_published_history(self):
        self.publish()
        before = self.pointer()
        with (self.root / '.publish.lock').open('a+b') as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(ValueError): self.publish('2026-10-04')
        self.assertEqual(self.pointer(), before)
        self.assertEqual(set(pub.read_current(self.root)['archive']['editions']), {'2026-10-03'})


if __name__ == '__main__':
    unittest.main()
