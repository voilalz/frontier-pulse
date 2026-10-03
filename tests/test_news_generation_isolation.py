"""News main must not consume paper state or write through protected aliases."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import update_news as news


def state(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*')
            if p.is_file() and not p.is_symlink()}


class NewsGenerationIsolationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.public = self.root / 'public'
        self.data = self.public / 'data'
        self.data.mkdir(parents=True)
        self.classics = self.public / 'classics'
        self.classics.mkdir()
        (self.classics / 'release.json').write_bytes(b'{broken classic pointer')
        self.legacy = self.data / 'research.json'
        config = json.loads((ROOT / 'config/news_config.json').read_text())
        config['article_text_enabled'] = False
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps(config))

    def run_news(self, *extra, live=False):
        args = ['--config', str(self.config), '--skip-ai', '--now', '2026-07-16T00:00:00Z']
        if not live:
            args += ['--fixture', str(ROOT / 'tests/fixtures/articles.json')]
        paths = {'output':'news.json', 'status-output':'status.json', 'stream-output':'stream.json',
                 'stream-status-output':'stream-status.json', 'research-output':'research.json',
                 'events-output':'events.json', 'deepread-output':'deepread.json',
                 'source-health-output':'source-health.json', 'weekly-output':'weekly.json',
                 'weekly-dir':'weekly', 'signals-output':'signals.json', 'archive-dir':'archive',
                 'archive-index':'archive/index.json', 'search-index':'archive/search-index.json'}
        for key, value in paths.items():
            args += ['--'+key, str(self.data / value)]
        return news.main(args + ['--feed-output', str(self.public / 'feed.xml'), *extra])

    def test_bad_or_missing_paper_fixture_does_not_block_news(self):
        bad = self.root / 'papers.json'
        bad.write_bytes(b'{invalid')
        for path in [bad, self.root / 'absent.json']:
            with self.subTest(path=path.name):
                self.assertEqual(self.run_news('--research-fixture', str(path)), 0)
                self.assertEqual(len(json.loads((self.data / 'news.json').read_text())['items']), 10)

    def test_corrupt_book_and_skip_flag_do_not_affect_news(self):
        for content, flags in [(b'{bad book', []), (b'{"items":[42]}', ['--skip-research'])]:
            self.legacy.write_bytes(content)
            self.assertEqual(self.run_news(*flags), 0)
            self.assertEqual(self.legacy.read_bytes(), content)

    def test_paper_fixture_never_creates_books_or_links(self):
        self.assertEqual(self.run_news('--research-fixture', str(ROOT / 'tests/fixtures/papers.json')), 0)
        self.assertFalse(self.legacy.exists())
        report = json.loads((self.data / 'news.json').read_text())
        self.assertEqual(report['paperLinkedItemCount'], 0)
        self.assertTrue(all(item['relatedPapers'] == [] for item in report['items']))

    def test_success_clears_old_paper_diagnostics(self):
        (self.data / 'status.json').write_text(json.dumps({'researchItemCount':99,
             'researchWarnings':['old'], 'researchEditorialStatus':'partial',
             'researchEditorialDiagnostics':{'old':True}}))
        self.assertEqual(self.run_news(), 0)
        report = json.loads((self.data / 'status.json').read_text())
        self.assertEqual(report['researchItemCount'], 0)
        self.assertEqual(report['researchWarnings'], [])
        self.assertIsNone(report['researchEditorialStatus'])
        self.assertEqual(report['researchEditorialDiagnostics'], {})

    def test_stream_preserves_daily_and_books_with_missing_paper_input(self):
        (self.data / 'news.json').write_bytes(b'{"items":[]}')
        self.legacy.write_bytes(b'legacy-book')
        before = state(self.classics)
        self.assertEqual(self.run_news('--stream-only', '--research-fixture', str(self.root/'absent')), 0)
        self.assertEqual((self.data / 'news.json').read_bytes(), b'{"items":[]}')
        self.assertEqual(self.legacy.read_bytes(), b'legacy-book')
        self.assertEqual(state(self.classics), before)

    def test_live_news_never_invokes_paper_collector(self):
        articles = news.collect_fixture(ROOT/'tests/fixtures/articles.json', datetime(2026,7,16,tzinfo=timezone.utc))
        with patch.object(news, 'collect_rss', return_value=articles), \
             patch.object(news, 'collect_gdelt', return_value=[]), \
             patch.object(news, 'collect_arxiv', side_effect=AssertionError('paper collector reached')):
            self.assertEqual(self.run_news(live=True), 0)
        self.assertFalse(self.legacy.exists())

    def test_bad_paper_configuration_is_unused(self):
        config = json.loads(self.config.read_text())
        config['research'] = None
        self.config.write_text(json.dumps(config))
        self.assertEqual(self.run_news(), 0)

    def test_protected_paths_are_rejected_before_first_write(self):
        for flag, path in [('--output', self.classics/'edition.json'),
                           ('--status-output', self.classics/'release.json'),
                           ('--feed-output', self.legacy),
                           ('--archive-dir', self.classics/'archive')]:
            with self.subTest(flag=flag):
                before = state(self.root)
                self.assertEqual(self.run_news(flag, str(path)), 2)
                self.assertEqual(state(self.root), before)

    def test_symlinked_parent_is_rejected_before_first_write(self):
        self.data.rmdir()
        self.data.symlink_to(self.classics, target_is_directory=True)
        before = state(self.classics)
        self.assertEqual(self.run_news(), 2)
        self.assertEqual(state(self.classics), before)

    def test_hardlinked_news_output_is_rejected(self):
        self.legacy.write_bytes(b'legacy bytes')
        os.link(self.legacy, self.data/'news.json')
        before = state(self.root)
        self.assertEqual(self.run_news(), 2)
        self.assertEqual(state(self.root), before)
        self.assertEqual(self.legacy.stat().st_nlink, 2)

    def test_symlinked_feed_cannot_replace_classic_pointer(self):
        (self.public/'feed.xml').symlink_to(self.classics/'release.json')
        before = state(self.root)
        self.assertEqual(self.run_news(), 2)
        self.assertEqual(state(self.root), before)

    def test_news_failure_preserves_classics_and_books(self):
        empty = self.root / 'empty.json'
        empty.write_text('[]')
        self.legacy.write_bytes(b'book')
        before = state(self.classics)
        self.assertEqual(self.run_news('--fixture', str(empty)), 2)
        self.assertEqual(state(self.classics), before)
        self.assertEqual(self.legacy.read_bytes(), b'book')
        self.assertEqual(json.loads((self.data/'status.json').read_text())['state'], 'failed')

    def test_derived_archive_cannot_overwrite_configuration_input(self):
        target = self.data/'archive/2026-07-16.json'
        target.parent.mkdir()
        self.config.replace(target)
        self.config = target
        before = state(self.root)
        self.assertEqual(self.run_news(), 2)
        self.assertEqual(state(self.root), before)

    def test_derived_archive_cannot_overwrite_fixture_input(self):
        target = self.data/'archive/2026-07-16.json'
        target.parent.mkdir()
        target.write_bytes((ROOT/'tests/fixtures/articles.json').read_bytes())
        before = state(self.root)
        self.assertEqual(self.run_news('--fixture',str(target)), 2)
        self.assertEqual(state(self.root), before)

    def test_input_alias_with_dotdot_is_normalized_consistently(self):
        child = self.root/'child'
        child.mkdir()
        original = self.config
        self.config = child/'../config.json'
        before = state(self.root)
        self.assertEqual(self.run_news('--output',str(original)), 2)
        self.assertEqual(state(self.root), before)

    def test_separate_search_shard_alias_refused_before_any_write(self):
        search = self.root/'separate-search/search-index.json'
        search.parent.mkdir()
        (search.parent/'search-2026-07.json').symlink_to(self.classics/'release.json')
        before = state(self.root)
        self.assertEqual(self.run_news('--search-index',str(search)), 2)
        self.assertEqual(state(self.root), before)

    def test_unowned_search_shards_are_preserved(self):
        archive = self.data/'archive'
        archive.mkdir()
        for name in ['search-nota-da.json', 'search-2026-99.json']:
            (archive/name).write_bytes(b'foreign shard bytes')
        self.assertEqual(self.run_news(), 0)
        for name in ['search-nota-da.json', 'search-2026-99.json']:
            self.assertTrue((archive/name).exists())
            self.assertEqual((archive/name).read_bytes(),b'foreign shard bytes')

    def test_unrelated_archive_links_are_ignored(self):
        archive = self.data/'archive'
        archive.mkdir()
        (archive/'foreign.json').symlink_to(self.classics/'release.json')
        self.assertEqual(self.run_news(), 0)
        self.assertTrue((archive/'foreign.json').is_symlink())

    def test_invalid_historical_month_does_not_create_or_replace_unowned_shard(self):
        archive = self.data/'archive'
        archive.mkdir()
        (archive/'index.json').write_text(json.dumps({'editions':[{'editionDate':'2026-99-16'}]}))
        (archive/'search-index.json').write_text(json.dumps({'items':[
            {'id':'old', 'editionDate':'2026-99-16', 'score':1}]}))
        foreign = archive/'search-2026-99.json'
        foreign.write_bytes(b'foreign bytes')
        self.assertEqual(self.run_news(), 0)
        self.assertEqual(foreign.read_bytes(),b'foreign bytes')

    def test_non_directory_archive_is_rejected_before_any_write(self):
        target = self.root/'archive-file'
        target.write_bytes(b'keep')
        before = state(self.root)
        self.assertEqual(self.run_news('--archive-dir',str(target)), 2)
        self.assertEqual(state(self.root), before)

    def test_repository_inputs_guard_keeps_compatible_news_and_stages(self):
        import news_boundary as boundary
        repo = self.root/'repo'
        repo.mkdir()
        paths = ['public/index.html', 'public/assets/app.js', 'public/sw.js',
                 '.github/workflows/daily-news.yml', 'package.json', 'src/new_source.py']
        for name in paths:
            path = repo/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(b'trusted bytes')
        with patch.object(boundary,'REPO',repo):
            for name in paths:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    boundary.safe_path(repo/name,write=True)
            for name in ['public/data/news.json', 'public/feed.xml', '.build/news-stage/data/news.json']:
                self.assertEqual(boundary.safe_path(repo/name,write=True), repo/name)
            self.assertEqual(boundary.safe_path(self.root/'external/news.json',write=True),
                             self.root/'external/news.json')
