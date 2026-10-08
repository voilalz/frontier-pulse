"""Version lifetime, idempotence, correction, lock and publication clock faults."""
import copy
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest.mock import patch

import test_publication as baseline
load, save, pub = baseline.load, baseline.save, baseline.pub
from batch1_fixtures import advance_day


class BatchPublicationTests(unittest.TestCase):
    setUpClass = classmethod(baseline.PublicationTests.setUpClass.__func__)
    tearDownClass = classmethod(baseline.PublicationTests.tearDownClass.__func__)
    setUp = baseline.PublicationTests.setUp
    promote = baseline.PublicationTests.promote
    state = baseline.PublicationTests.state

    def test_same_day_retry_preserves_formal_bytes_even_when_status_failed(self):
        self.promote()
        before = self.state()
        news = load(self.stage/'data/news.json')
        news['brief']['headline'] = '重新生成的选稿'
        save(self.stage/'data/news.json', news)
        save(self.stage/'data/archive/2026-07-16.json', news)
        status = load(self.public/'data/status.json')
        status['state'] = 'failed'
        save(self.public/'data/status.json', status)
        expected = self.state()
        result = self.promote('r-retry')
        self.assertEqual(result['releaseId'], 'r-001')
        self.assertEqual(self.state(), expected)
        self.assertFalse((self.public/'releases/r-retry').exists())

    def test_correction_requires_current_base_and_preserves_initial_version(self):
        self.promote()
        news = load(self.stage/'data/news.json')
        news['items'][0]['displayTranslation']['summary'] += '报告所列测量结果将用于后续受控演示。'
        save(self.stage/'data/news.json', news)
        save(self.stage/'data/archive/2026-07-16.json', news)
        revised = self.promote('r-correction', revision_reason='补充来源支持的测量安排', base_release_id='r-001')
        self.assertEqual(revised['revision']['number'], 1)
        self.assertEqual(revised['revision']['initialReleaseId'], 'r-001')
        self.assertEqual(revised['revision']['changes']['corrected'], [news['items'][0]['id']])
        self.assertNotIn('报告所列测量结果将用于后续受控演示。',
            load(self.public/'releases/r-001/data/news.json')['items'][0]['displayTranslation']['summary'])
        with self.assertRaises(ValueError):
            self.promote('r-stale', revision_reason='再次补充来源支持安排', base_release_id='r-001')

    def test_same_day_revisions_do_not_accumulate_full_snapshots(self):
        self.promote('r-001')
        current = 'r-001'
        for number in range(10):
            current = self.promote(f'r-rev-{number:02}', revision_reason=f'第{number}次恢复当日深读',
                                   base_release_id=current)['releaseId']
        kept = sorted(p.name for p in (self.public/'releases').iterdir())
        self.assertEqual(len(kept), 7)
        self.assertIn('r-001', kept)
        self.assertIn('r-rev-09', kept)
        self.assertIn('r-rev-08', kept)
        self.assertNotIn('r-rev-00', kept)
        self.assertEqual(load(self.public/'data/edition-versions/r-rev-00.json')['manifest']['releaseId'], 'r-rev-00')

    def test_concurrent_same_day_promotions_create_only_one_formal_edition(self):
        def publish(index):
            return self.promote(f'r-concurrent-{index}')['releaseId']
        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(publish, [1,2]))
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(len(list((self.public/'releases').iterdir())), 1)

    def test_edition_links_survive_eight_new_promotions_without_retaining_all_snapshots(self):
        self.promote('r-original')
        original = load(self.public/'releases/r-original/data/news.json')
        for day in range(17,25):
            pub.prepare_stage(self.sample, self.stage)
            advance_day(self.stage, f'2026-07-{day}')
            self.promote(f'r-day-{day}')
        self.assertFalse((self.public/'releases/r-original').exists())
        self.assertEqual(len(list((self.public/'releases').iterdir())), 7)
        compact = load(self.public/'data/edition-versions/r-original.json')
        self.assertEqual(compact['news'], original)
        self.assertEqual(compact['manifest']['releaseId'], 'r-original')
        self.assertEqual(compact['news']['editionDate'], '2026-07-16')

    def test_delay_is_recorded_for_attempt_date_without_relabeling_previous_content(self):
        self.promote()
        pub.record_failure(self.public, 'daily', '正文校验失败', expected_date='2026-07-17',
            now=datetime(2026,7,17,0,16,tzinfo=timezone.utc))
        status = load(self.public/'data/status.json')
        self.assertEqual(status['editionDate'], '2026-07-16')
        self.assertEqual(status['attemptEditionDate'], '2026-07-17')
        self.assertTrue(status['delayed'])
        self.assertEqual(status['delayMinutes'], 16)

    def test_force_refresh_cannot_replace_formal_edition_without_explicit_correction(self):
        from check_daily_refresh import decide_refresh
        args = dict(today='2026-07-16', event_name='workflow_dispatch', force_refresh=True,
            release={'releaseId':'r-formal','editionDate':'2026-07-16'})
        self.assertEqual(decide_refresh({'state':'failed'}, **args), (False, 'formal_edition_exists'))
        self.assertEqual(decide_refresh({'state':'failed'}, revision_reason='修正来源支持的安排', **args), (True,'explicit_revision'))

    def test_target_and_delay_deadline_use_beijing_calendar(self):
        from publication_clock import publication_timing
        before = publication_timing('2026-07-17', datetime(2026,7,16,23,59,tzinfo=timezone.utc))
        self.assertEqual(before['waitSeconds'], 60)
        self.assertFalse(before['delayed'])
        deadline = publication_timing('2026-07-17', datetime(2026,7,17,0,15,tzinfo=timezone.utc))
        self.assertFalse(deadline['delayed'])
        self.assertTrue(publication_timing('2026-07-17', datetime(2026,7,17,0,16,tzinfo=timezone.utc))['delayed'])
