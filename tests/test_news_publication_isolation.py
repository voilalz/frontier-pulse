"""Publication effects must be confined to the news-owned paths."""
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_publication as baseline
load, save, pub = baseline.load, baseline.save, baseline.pub


def tree(root):
    return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*')
            if p.is_file() and not p.is_symlink()}


class NewsPublicationIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        baseline.PublicationTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.public, self.stage = self.root/'public', self.root/'stage'
        shutil.copytree(self.sample, self.public)
        shutil.copytree(self.sample, self.stage)
        for root in [self.public, self.stage]:
            save(root/'classics/release.json', {'sentinel':True})
            save(root/'data/classics/archive.json', {'classic':True})
            (root/'data/research.json').write_bytes(b'{corrupt legacy')
            (root/'data/foreign.json').write_bytes(b'foreign')

    def paper_bytes(self, root):
        return {k:v for k,v in tree(root).items()
                if k.startswith(('classics/', 'data/classics/')) or k in ['data/research.json','data/foreign.json']}

    def promote(self, rid='n-1'):
        return pub.promote(self.stage, self.public, 'daily', rid, 'test')

    def test_prepare_only_copies_news_and_preserves_unowned_stage(self):
        before = self.paper_bytes(self.stage)
        pub.prepare_stage(self.public, self.stage)
        self.assertEqual(self.paper_bytes(self.stage), before)
        fresh = self.root/'fresh'
        pub.prepare_stage(self.public, fresh)
        self.assertEqual(self.paper_bytes(fresh), {})
        self.assertEqual((fresh/'data/news.json').read_bytes(), (self.public/'data/news.json').read_bytes())

    def test_prepare_ignores_unrelated_symlink_without_reading_target(self):
        (self.public/'data/foreign-link').symlink_to(self.root/'missing')
        fresh = self.root/'fresh'
        pub.prepare_stage(self.public, fresh)
        self.assertFalse((fresh/'data/foreign-link').is_symlink())

    def test_bad_legacy_or_classic_data_does_not_block_validation(self):
        pub.validate_publication(self.stage, 'daily', '2026-07-16')
        (self.stage/'data/research.json').unlink()
        pub.validate_publication(self.stage, 'daily', '2026-07-16')

    def test_promote_restore_stream_and_failure_preserve_paper_bytes(self):
        before = self.paper_bytes(self.public)
        manifest = self.promote()
        self.assertEqual(manifest['artifactScope'], 'news-only-v1')
        self.assertEqual(manifest['schemaVersion'], 1)
        self.assertNotIn('data/research.json', manifest['files'])
        self.assertEqual(self.paper_bytes(self.public), before)
        self.assertEqual(self.paper_bytes(self.public/'releases/n-1'), {})
        self.promote('n-2')
        pub.restore(self.public, 'n-1')
        pub.promote(self.stage, self.public, 'stream', 'unused', 'test')
        pub.record_failure(self.public, 'daily', 'fixture failure')
        self.assertEqual(self.paper_bytes(self.public), before)

    def legacy_snapshot(self):
        manifest = self.promote()
        snap = self.public/'releases/n-1'
        manifest.pop('artifactScope', None)
        manifest['files']['data/research.json'] = '0'*64
        save(snap/'manifest.json', manifest)
        return snap

    def test_legacy_research_hash_corruption_or_missing_is_ignored(self):
        snap = self.legacy_snapshot()
        stored = (snap/'manifest.json').read_bytes()
        before = self.paper_bytes(self.public)
        for content in [None, b'{malformed old research']:
            with self.subTest(content=content):
                if content is not None: (snap/'data/research.json').write_bytes(content)
                normalized = pub.restore(self.public, 'n-1')
                self.assertNotIn('data/research.json', normalized['files'])
                self.assertEqual(normalized['artifactScope'], 'news-only-v1')
                self.assertEqual(self.paper_bytes(self.public), before)
                self.assertEqual((snap/'manifest.json').read_bytes(), stored)

    def test_new_scope_cannot_claim_legacy_and_unknown_paths_fail(self):
        manifest = self.promote()
        snap = self.public/'releases/n-1'
        before = tree(self.public/'data')
        for name in ['data/research.json', 'classics/release.json', '../outside',
                     '/absolute', 'data/foreign.json', 'data/archive/../news.json', 'data\\news.json']:
            bad = dict(manifest, files={**manifest['files'], name:'0'*64})
            save(snap/'manifest.json', bad)
            with self.assertRaises(ValueError): pub.restore(self.public, 'n-1')
            self.assertEqual(tree(self.public/'data'), before)
        save(snap/'manifest.json', dict(manifest, artifactScope='unknown'))
        with self.assertRaises(ValueError): pub.restore(self.public, 'n-1')

    def test_owned_news_corruption_still_refuses_restore(self):
        snap = self.legacy_snapshot()
        (snap/'data/news.json').write_bytes(b'bad news')
        before = tree(self.public/'data')
        with self.assertRaises(ValueError): pub.restore(self.public, 'n-1')
        self.assertEqual(tree(self.public/'data'), before)

    def test_prepare_rejects_protected_stage_before_cleaning(self):
        for target in [self.public/'classics', self.public/'releases/existing',
                       self.root/'classics/stage']:
            target.mkdir(parents=True, exist_ok=True)
            (target/'sentinel').write_bytes(b'keep')
            before = tree(target)
            with self.assertRaises(ValueError): pub.prepare_stage(self.public, target)
            self.assertEqual(tree(target), before)

    def test_owned_source_and_destination_aliases_refused_before_mutation(self):
        for side in [self.stage, self.public]:
            target = side/'data/news.json'
            original = target.read_bytes()
            target.unlink()
            target.symlink_to(side/'classics/release.json')
            before = tree(self.public)
            with self.assertRaises(ValueError): self.promote('bad-alias')
            self.assertEqual(tree(self.public), before)
            target.unlink(); target.write_bytes(original)

    def test_install_rejects_unowned_lists_before_beforeimage_or_copy(self):
        before = tree(self.public)
        for files in [['data/news.json','data/research.json'], ['../escape'], ['data/classics/archive.json']]:
            with self.assertRaises(ValueError): pub.install_bundle(self.stage, self.public, files)
            self.assertEqual(tree(self.public), before)

    def test_hardlinked_target_refused_before_snapshot_creation(self):
        target = self.public/'data/news.json'
        target.unlink(); os.link(self.public/'data/research.json', target)
        before = tree(self.public)
        with self.assertRaises(ValueError): self.promote()
        self.assertEqual(tree(self.public), before)

    def test_fixed_install_alias_cannot_write_through_to_papers(self):
        alias = self.public/'data/news.json.install'
        alias.symlink_to(self.public/'classics/release.json')
        before = self.paper_bytes(self.public)
        pub.install_file(self.stage/'data/news.json', self.public/'data/news.json')
        self.assertEqual(self.paper_bytes(self.public), before)
        self.assertTrue(alias.is_symlink())

    def test_failed_install_rolls_back_news_and_keeps_papers(self):
        self.promote()
        before = {k:v for k,v in tree(self.public).items() if not k.startswith('releases/')}
        real = pub.install_file
        calls = 0
        def fail_after_one(source, target):
            nonlocal calls
            calls += 1
            if calls == 2: raise OSError('installation fault')
            return real(source,target)
        with patch.object(pub, 'install_file', side_effect=fail_after_one):
            with self.assertRaises(OSError): self.promote('n-fault')
        self.assertEqual({k:v for k,v in tree(self.public).items() if not k.startswith('releases/')}, before)

    def test_foreign_and_symlink_releases_survive_seven_news_pruning(self):
        releases = self.public/'releases'
        foreign = releases/'foreign-classic'
        save(foreign/'manifest.json', {'kind':'classic', 'publishedAt':'1900'})
        link = releases/'linked-classic'
        link.symlink_to(self.public/'classics', target_is_directory=True)
        before = tree(foreign)
        for n in range(9): self.promote(f'n-{n:02}')
        self.assertEqual(tree(foreign), before)
        self.assertTrue(link.is_symlink())
        self.assertEqual(sorted(p.name for p in releases.iterdir() if p.name.startswith('n-')),
                         [f'n-{n:02}' for n in range(2,9)])

    def test_parent_alias_and_failure_status_refused(self):
        shutil.rmtree(self.public/'data')
        (self.public/'data').symlink_to(self.public/'classics', target_is_directory=True)
        before = tree(self.public/'classics')
        with self.assertRaises(ValueError): pub.record_failure(self.public, 'daily', 'bad')
        self.assertEqual(tree(self.public/'classics'), before)

    def test_pruning_preserves_unowned_descendants_inside_news_snapshots(self):
        self.promote('n-mixed')
        mixed = self.public/'releases/n-mixed'
        save(mixed/'classics/foreign.json', {'classic':'keep'})
        (mixed/'data/research.json').write_bytes(b'legacy snapshot book')
        (mixed/'foreign-link').symlink_to(self.public/'classics',target_is_directory=True)
        before = tree(mixed)
        for n in range(8): self.promote(f'n-{n:02}')
        self.assertEqual(tree(mixed), before)
        self.assertTrue((mixed/'foreign-link').is_symlink())
        self.assertEqual(sorted(p.name for p in (self.public/'releases').iterdir() if p.name != 'n-mixed'),
                         [f'n-{n:02}' for n in range(1,8)])

    def test_install_file_refuses_unowned_source_and_destination(self):
        before = tree(self.public)
        for source, target in [(self.stage/'data/news.json', self.public/'data/foreign.json'),
                               (self.stage/'data/foreign.json', self.public/'data/news.json')]:
            with self.subTest(source=source.name,target=target.name), self.assertRaises(ValueError):
                pub.install_file(source,target)
            self.assertEqual(tree(self.public), before)
