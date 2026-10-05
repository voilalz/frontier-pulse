"""Reader and admission regressions at the provider/selection boundaries."""
import copy
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import update_news as news
from evidence_trace import make_evidence, valid_display_translation
from event_identity import same_event


class ReaderSelectionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 5, tzinfo=timezone.utc)
        self.config = news.load_config(ROOT / 'config' / 'news_config.json')
        self.runtime = {'provider': 'deepseek', 'model': 'fixture-model'}

    def article(self, title='NASA plans a lunar satellite launch', description=None, key='nasa'):
        text = description if description is not None else 'NASA scheduled the satellite launch for Monday. The spacecraft will collect lunar observations.'
        article = news.Article(key, title, text, f'https://example.org/{key}', 'Publisher', 'example.org', '美国', self.now)
        article.source_evidence = make_evidence(text, article.url, self.now.isoformat(), 'body')
        article.evidence_quality = {'status': 'body' if text else 'title-only'}
        return article

    def response(self, summary):
        return {'items': [{'index': 1, 'titleZh': '美国航天局计划发射月球卫星', 'summary': summary, 'tags': []}]}

    def test_mixed_english_provider_output_cannot_enter_or_survive_cache(self):
        article = self.article()
        mixed = '美国航天局 NASA scheduled the satellite launch for Monday. The spacecraft will collect lunar observations.'
        for request in (news.request_stream_translation_batch, news.request_daily_translation_batch):
            with self.subTest(request=request.__name__), patch.object(news, 'request_structured_json', return_value=self.response(mixed)):
                with self.assertRaises(news.TranslationContentRejected):
                    request([article], self.config, self.runtime)
        # An old cache record must be disqualified even when its binding/hash match.
        raw = news.item_from_article(article, self.config)
        raw['translationProvider'] = 'deepseek'
        raw['displayTranslation'] = {'version': 1, 'language': 'zh-CN', 'provider': 'deepseek',
            'title': '美国航天局计划发射月球卫星', 'summary': mixed,
            'sourceTitle': raw['originalTitle'], 'sourceSummary': raw['summary'],
            'sourceEvidenceRefs': raw['summaryEvidenceRefs']}
        cache = {'items': [raw], 'translationProvider': 'deepseek', 'translationModel': 'fixture-model'}
        self.assertFalse(valid_display_translation(raw))
        self.assertEqual(news.reusable_stream_translations(cache, [article], self.runtime), {})
        with patch.object(news, 'request_structured_json', return_value=self.response('美国航天局计划于周一发射卫星，航天器将收集月球观测资料。')):
            translated = news.request_stream_translation_batch([article], self.config, self.runtime)
        item = news.item_from_article(article, self.config, translated[article.id])
        cache['items'] = [item]
        reused = news.reusable_stream_translations(cache, [article], self.runtime)
        self.assertEqual(reused['nasa']['summary'], '美国航天局计划于周一发射卫星，航天器将收集月球观测资料。')

    def test_metadata_filler_is_rejected_but_supported_event_absence_is_allowed(self):
        article = self.article()
        for summary in ['现有元数据未提供更多摘要。', '美国航天局未提取到可引用的正文。']:
            with patch.object(news, 'request_structured_json', return_value=self.response(summary)):
                with self.assertRaises(news.TranslationContentRejected):
                    news.request_stream_translation_batch([article], self.config, self.runtime)
        from reader_quality import chinese_reader_text
        self.assertTrue(chinese_reader_text('警方尚未公布伤亡人数。'))

    def test_title_only_has_empty_summary_and_can_cache_translated_title(self):
        article = self.article(description='')
        raw = news.item_from_article(article, self.config)
        self.assertEqual(raw['summary'], '')
        self.assertEqual(raw['contentAvailability'], 'title-only')
        with patch.object(news, 'request_structured_json', return_value=self.response('')):
            result = news.request_stream_translation_batch([article], self.config, self.runtime)
        item = news.item_from_article(article, self.config, result['nasa'])
        self.assertTrue(valid_display_translation(item))
        self.assertEqual(item['displayTranslation']['summary'], '')
        cache = {'items':[item], 'translationProvider':'deepseek', 'translationModel':'fixture-model'}
        self.assertIn('nasa', news.reusable_stream_translations(cache, [article], self.runtime))

    def test_terminal_auth_failure_stops_batch_splitting(self):
        articles = [self.article(key=f'item-{i}') for i in range(6)]
        attempts = []
        def denied(batch):
            attempts.append(len(batch))
            raise news.ProviderRequestError('provider rejected credentials', status_code=401)
        result, _, diagnostics = news.run_resilient_ai_batches(articles, label='翻译',
            initial_batch_size=2, retry_rounds=2, request_batch=denied)
        self.assertEqual(result, {})
        self.assertEqual(attempts, [2])
        self.assertEqual(diagnostics['requestCount'], 1)

    def test_featured_pool_excludes_containers_and_title_or_lead_only(self):
        from reader_quality import assess_admissibility
        cases = [('Mars mission: live', 'live-container'), ('Weekly roundup of space missions', 'roundup'),
            ('Q&A: satellite mission explained', 'qa'), ('On this day: NASA archive', 'historical-column'),
            ('Sponsored: buy this spacecraft now', 'marketing')]
        for title, reason in cases:
            item = news.item_from_article(self.article(title), self.config)
            self.assertEqual(assess_admissibility(item)['reason'], reason)
        for title, text in [('NASA mission', ''), ('NASA mission', 'NASA plans a lunar mission.')]:
            article = self.article(title, text)
            article.source_evidence = make_evidence(text, article.url, self.now.isoformat(), 'feed')
            self.assertFalse(assess_admissibility(news.item_from_article(article, self.config))['eligible'])
        item = news.item_from_article(self.article('NASA introduces live telemetry for lunar satellite'), self.config)
        self.assertTrue(assess_admissibility(item)['eligible'])

    def test_scarce_featured_pool_reports_actual_count_instead_of_filling(self):
        articles = [self.article(key='nasa'), self.article('OpenAI releases new agent toolkit',
            'OpenAI released an agent toolkit for developers. The toolkit includes a new evaluation interface.', 'openai'),
            self.article('Mars mission: live', key='container')]
        report = news.build_report(articles, self.config, self.now, True)
        self.assertEqual(report['itemCount'], 2)
        self.assertEqual(report['coverageStatus'], 'insufficient')
        self.assertEqual(len(report['items']), 2)
        news.validate_report(report, 10)
        empty = news.build_report([self.article(description='')], self.config, self.now, True)
        self.assertEqual(empty['items'], [])
        news.validate_report(empty, 10)

    def test_named_departure_merges_same_person_but_preserves_distinct_actions(self):
        def item(title, person='Alex Robinson', date='2026-10-05'):
            text = f'{person} left OpenAI on Friday. The engineer discussed AI safety risks.'
            return {'id': title, 'originalTitle':title, 'url':'https://example.org/'+str(len(title)),
                'publishedAt': date+'T00:00:00Z', 'evidenceRecords':make_evidence(text, 'https://example.org/body', self.now.isoformat(), 'body')}
        outgoing = item('Outgoing OpenAI safety engineer warns about AI risks')
        same = item('Another OpenAI safety departure brings public warning')
        self.assertTrue(same_event(outgoing, same))
        self.assertFalse(same_event(outgoing, item('After OpenAI departure, Alex Robinson launches robotics startup')))
        self.assertFalse(same_event(outgoing, item('OpenAI safety engineer resigns and warns', 'Sam Smith')))
        self.assertFalse(same_event(outgoing, item('OpenAI safety departure brings warning', date='2026-10-12')))
        invented = copy.deepcopy(same)
        invented['evidenceRecords'] = []
        invented['summary'] = 'Alex Robinson left OpenAI on Friday.'
        self.assertFalse(same_event(outgoing, invented))
