"""Real artifact regression tests for the publication boundary."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
try:
    import publication as pub
except ImportError:
    pub = None


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')


class PublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.sample = Path(cls.fixture.name) / 'public'
        data = cls.sample / 'data'
        command = [sys.executable, str(ROOT / 'scripts/update_news.py'),
                   '--fixture', str(ROOT / 'tests/fixtures/articles.json'),
                   '--research-fixture', str(ROOT / 'tests/fixtures/papers.json'),
                   '--skip-ai', '--now', '2026-07-16T00:00:00Z']
        paths = {'output':'news.json', 'status-output':'status.json', 'stream-output':'stream.json',
                 'stream-status-output':'stream-status.json', 'research-output':'research.json',
                 'events-output':'events.json', 'weekly-output':'weekly.json', 'weekly-dir':'weekly',
                 'signals-output':'signals.json', 'archive-dir':'archive',
                 'archive-index':'archive/index.json', 'search-index':'archive/search-index.json'}
        for key, value in paths.items():
            command.extend(['--' + key, str(data / value)])
        command.extend(['--feed-output', str(cls.sample / 'feed.xml')])
        subprocess.run(command, cwd=ROOT, check=True, capture_output=True)
        from batch1_fixtures import localize_stage
        localize_stage(cls.sample)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.assertIsNotNone(pub, 'publication boundary is not implemented')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.public = Path(self.temp.name) / 'public'
        self.stage = Path(self.temp.name) / 'stage'
        pub.prepare_stage(self.sample, self.public)
        pub.prepare_stage(self.sample, self.stage)

    def state(self):
        return {str(p.relative_to(self.public)): p.read_bytes()
                for p in self.public.rglob('*') if p.is_file()}

    def promote(self, release='r-001', **options):
        return pub.promote(self.stage, self.public, 'daily', release, 'test-commit', **options)

    def test_rejects_bad_fields_dates_references_without_touching_public(self):
        for fault in ['field', 'date', 'reference']:
            with self.subTest(fault=fault):
                pub.prepare_stage(self.sample, self.stage)
                path = self.stage / 'data/deepread.json'
                data = load(path)
                if fault == 'field':
                    del data['chapters']
                elif fault == 'date':
                    data['editionDate'] = '2026-07-15'
                else:
                    data['chapters'][0]['newsIds'] = ['missing-evidence']
                save(path, data)
                before = self.state()
                with self.assertRaises(ValueError):
                    self.promote()
                self.assertEqual(before, self.state())

    def test_snapshot_ids_hashes_and_archive_are_coherent(self):
        self.promote()
        manifest = load(self.public / 'data/release.json')
        self.assertEqual(manifest['releaseId'], 'r-001')
        self.assertEqual(manifest['editionDate'], '2026-07-16')
        self.assertEqual(manifest['basePath'], './releases/r-001/')
        for name in ['news.json', 'deepread.json', 'archive/2026-07-16.json', 'deepread/2026-07-16.json', 'archive/search-index.json']:
            self.assertEqual(load(self.public / 'releases/r-001/data' / name)['releaseId'], 'r-001')
        pub.verify_snapshot(self.public / 'releases/r-001')

    def add_legacy_deepread_archive(self):
        # Production's 2026-09-26 edition nests events inside schema-1 sections.
        archived = load(ROOT / 'tests/fixtures/deepread-legacy-2026-09-26.json')
        path = self.stage / 'data/deepread/2026-09-26.json'
        save(path, archived)
        index_path = self.stage / 'data/deepread/index.json'
        index = load(index_path)
        index['editions'].append({'editionDate': '2026-09-26'})
        save(index_path, index)
        return path

    def test_legacy_section_archive_does_not_block_current_daily_publication(self):
        path = self.add_legacy_deepread_archive()
        original = load(path)
        self.promote()
        self.assertEqual(load(self.public / 'data/release.json')['editionDate'], '2026-07-16')
        retained = load(self.public / 'data/deepread/2026-09-26.json')
        self.assertEqual(retained['schemaVersion'], 1)
        self.assertEqual(retained['sections'], original['sections'])
        pub.verify_snapshot(self.public / 'releases/r-001')

    def test_malformed_legacy_section_archive_still_blocks_publication(self):
        path = self.add_legacy_deepread_archive()
        original = load(path)
        for fault in ['sections', 'section', 'events', 'event']:
            with self.subTest(fault=fault):
                archived = copy.deepcopy(original)
                if fault == 'sections':
                    archived['sections'] = {}
                elif fault == 'section':
                    archived['sections'][0] = None
                elif fault == 'events':
                    archived['sections'][0]['events'] = {}
                else:
                    archived['sections'][0]['events'][0] = None
                save(path, archived)
                before = self.state()
                with self.assertRaises(ValueError):
                    self.promote()
                self.assertEqual(self.state(), before)

    def test_corrupt_referenced_search_shard_cannot_replace_readable_content(self):
        self.promote()
        before = self.state()
        index = load(self.stage / 'data/archive/search-index.json')
        shard = self.stage / index['shards'][0]['file']
        original = shard.read_bytes()
        for fault in ['malformed', 'date', 'reference']:
            with self.subTest(fault=fault):
                shard.write_bytes(original)
                if fault == 'malformed':
                    shard.write_text('{MALFORMED JSON')
                else:
                    data = load(shard)
                    data['items'][0]['editionDate' if fault == 'date' else 'id'] = ('2026-08-01' if fault == 'date' else 'missing-article')
                    save(shard, data)
                with self.assertRaises(ValueError): self.promote('r-bad')
                self.assertEqual(self.state(), before)

    def test_retains_seven_snapshots_and_restores_exact_bundle(self):
        for index in range(9):
            pub.prepare_stage(self.sample, self.stage)
            from batch1_fixtures import advance_day
            advance_day(self.stage, f'2026-07-{16+index:02}')
            self.promote(f'r-{index:03}')
        releases = self.public / 'releases'
        self.assertEqual(sorted(p.name for p in releases.iterdir()), [f'r-{i:03}' for i in range(2, 9)])
        pub.restore(self.public, 'r-003')
        self.assertEqual(load(self.public / 'data/release.json')['releaseId'], 'r-003')
        for p in (releases / 'r-003/data').rglob('*.json'):
            self.assertEqual(p.read_bytes(), (self.public / 'data' / p.relative_to(releases / 'r-003/data')).read_bytes())

    def test_corrupt_snapshot_cannot_restore(self):
        self.promote()
        (self.public / 'releases/r-001/data/news.json').write_text('{}')
        before = self.state()
        with self.assertRaises(ValueError):
            pub.restore(self.public, 'r-001')
        self.assertEqual(before, self.state())

    def test_release_id_cannot_escape_snapshot_directory(self):
        for release in ['../escape', 'a/b', '', '.']:
            with self.assertRaises(ValueError):
                self.promote(release)

    def test_failure_only_updates_status_and_preserves_last_success(self):
        self.promote()
        before = self.state()
        previous = load(self.public / 'data/status.json')['lastSuccessAt']
        pub.record_failure(self.public, 'daily', '验证失败')
        after = self.state()
        changed = [key for key in after if before.get(key) != after[key]]
        self.assertEqual(changed, ['data/status.json'])
        self.assertEqual(load(self.public / 'data/status.json')['lastSuccessAt'], previous)
        self.assertEqual(load(self.public / 'data/status.json')['state'], 'failed')

    def test_stream_promotion_does_not_change_daily_snapshot(self):
        self.promote()
        before = (self.public / 'data/release.json').read_bytes()
        data = load(self.stage / 'data/stream.json')
        data['generatedAt'] = '2026-07-16T03:00:00Z'
        save(self.stage / 'data/stream.json', data)
        pub.promote(self.stage, self.public, 'stream', 'ignored', 'test')
        self.assertEqual((self.public / 'data/release.json').read_bytes(), before)
        self.assertEqual(load(self.public / 'data/stream.json')['generatedAt'], '2026-07-16T03:00:00Z')
        self.assertEqual(load(self.public / 'releases/r-001/data/stream.json')['generatedAt'], '2026-07-16T00:00:00Z')

    def test_partial_file_install_rolls_back_all_canonical_files(self):
        self.promote()
        before = {p: b for p, b in self.state().items() if not p.startswith('releases/')}
        original = pub.install_file
        count = 0
        def fail_once(source, target):
            nonlocal count
            count += 1
            if count == 3:
                raise OSError('disk failed')
            return original(source, target)
        with patch.object(pub, 'install_file', side_effect=fail_once):
            with self.assertRaises(OSError):
                self.promote('r-002', revision_reason='演练原子安装的中断恢复', base_release_id='r-001')
        after = {p: b for p, b in self.state().items() if not p.startswith('releases/')}
        self.assertEqual(before, after)

    def test_rejects_archive_mismatch_and_unhealthy_status(self):
        save(self.stage / 'data/archive/2026-07-16.json', {})
        with self.assertRaises(ValueError):
            self.promote()
        pub.prepare_stage(self.sample, self.stage)
        status = load(self.stage / 'data/status.json')
        status['state'] = 'failed'
        save(self.stage / 'data/status.json', status)
        with self.assertRaises(ValueError):
            self.promote()

    def test_expected_date_and_existing_snapshot_are_immutable(self):
        with self.assertRaises(ValueError):
            pub.validate_publication(self.stage, 'daily', '2026-07-17')
        self.promote()
        old = load(self.stage / 'data/news.json')
        old['brief']['headline'] = 'changed'
        save(self.stage / 'data/news.json', old)
        with self.assertRaises(ValueError):
            self.promote()
