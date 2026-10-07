"""The published reader gate rejects incomplete or untraceable deep reads."""
import copy
import json
import unittest
from datetime import datetime, timezone

from batch1_fixtures import ROOT, full_deep, translate_item
import update_news as news


class DeepreadQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.now = datetime(2026,7,16,tzinfo=timezone.utc)
        config = news.load_config(ROOT/'config/news_config.json')
        candidates = news.score_articles(news.collect_fixture(ROOT/'tests/fixtures/articles.json', cls.now), config, cls.now)
        report = news.build_report(candidates, config, cls.now, True)
        cls.good = full_deep([translate_item(i) for i in report['items']], '2026-07-16')

    def test_real_provider_pipeline_produces_a_traceable_complete_reader(self):
        from deepread_quality import validate_complete
        self.assertEqual(self.good['generationStatus'], 'ok')
        validate_complete(self.good)

    def test_english_truncation_repetition_missing_evidence_and_empty_chapter_are_rejected(self):
        from deepread_quality import choose_readable_deepread, validate_complete
        for fault in ['english', 'half-sentence', 'repeated-paragraph', 'evidence', 'two-chapters', 'one-paragraph', 'filler']:
            with self.subTest(fault=fault):
                draft = copy.deepcopy(self.good)
                block = draft['chapters'][0]['blocks'][0]
                if fault == 'english': block.pop('displayTranslation', None)
                elif fault == 'half-sentence': block['displayTranslation']['text'] = '本次技术报告说明已完成的测试以及后续计划，但仍需'
                elif fault == 'repeated-paragraph': draft['chapters'][1]['blocks'][0] = copy.deepcopy(block)
                elif fault == 'evidence': block['evidenceIds'] = ['missing']
                elif fault == 'two-chapters': draft['chapters'] = draft['chapters'][:2]
                elif fault == 'one-paragraph': draft['chapters'][0]['blocks'] = [block]
                else: block['displayTranslation']['text'] = '现有元数据尚未提供这条新闻的详细正文，需查阅原始报道。'
                with self.assertRaises(ValueError): validate_complete(draft)
                reader = choose_readable_deepread(draft, [self.good], '2026-07-17')
                self.assertEqual(reader['readerStatus'], 'retained')
                self.assertEqual(reader['editionDate'], '2026-07-16')
                self.assertEqual(reader['publicationEditionDate'], '2026-07-17')

    def test_no_valid_history_is_an_explicit_empty_reader(self):
        from deepread_quality import choose_readable_deepread, validate_readable
        reader = choose_readable_deepread({'generationStatus':'failed'}, [], '2026-07-17')
        self.assertEqual(reader['readerStatus'], 'unavailable')
        self.assertEqual(reader['chapters'], [])
        validate_readable(reader, '2026-07-17')

    def test_two_comparison_outline_is_repaired_before_fixed_prose_ids(self):
        from deepread_editorial import build_daily_deepread
        from deepread_quality import validate_complete
        from evidence_trace import make_evidence, trace_claim
        items = []
        for index, actor in enumerate('甲乙丙丁'):
            title = actor+'团队发布人工智能智能体测评结果'
            first = title+'，报告列出模型在受控环境中的任务执行过程，并公开测试条件供后续核对。'
            second = actor+'团队说明人工智能智能体评估的后续安排，团队将依据已公开的测量记录开展复测，核对不同任务条件下的结果。'
            url = f'https://publisher.example/agent-{index}'
            records = make_evidence(first+' '+second,url,self.now.isoformat(),'body')
            items.append({'id':f'agent-{index}','eventId':f'evt-{index:012x}', 'title':title,'originalTitle':title,
                'summary':first,'summaryEvidenceRefs':trace_claim(first,records),'evidenceRecords':records,
                'url':url,'source':actor+'团队','sources':[{'name':actor+'团队','url':url}],
                'category':'AI','publishedAt':'2026-07-15T23:00:00Z','score':90-index})
        observed_chapters = []
        def provider(runtime, **kwargs):
            material = json.loads(kwargs['input_text'])
            if kwargs['schema_name'] == 'deepread_outline_v2':
                ids = material['fixedSelectedNewsIds']
                return {'selectedNewsIds':ids,'chapters':[
                    {'title':'AI 智能体：两项独立进展','angle':'分别核对两项报道在AI 智能体上披露的事实与未知事项',
                     'newsIds':members,'kind':'comparison','comparisonKey':'ai-agent'} for members in [ids[:2],ids[2:]]]}
            self.assertEqual(kwargs['schema_name'],'deepread_prose_v2')
            observed_chapters.append(len(material['outline']))
            by_id={e['newsId']:e for e in material['events']}
            chapters={}
            for chapter in material['outline']:
                blocks=[{'type':'paragraph','text':r['text'],'sourceText':r['text'],'newsIds':[key],
                    'evidenceIds':[r['evidenceId']]} for key in chapter['newsIds'] for r in by_id[key]['evidenceRecords']]
                if chapter['kind']=='comparison':
                    method=chapter['comparisonText']
                    blocks.append({'type':'comparison','text':method,'sourceText':method,'newsIds':chapter['newsIds'],
                        'evidenceIds':[r['evidenceId'] for key in chapter['newsIds'] for r in by_id[key]['evidenceRecords']]})
                chapters[chapter['id']]={'blocks':blocks}
            observations=[{'text':e['evidenceRecords'][0]['text'],'sourceText':e['evidenceRecords'][0]['text'],
                'newsIds':[e['newsId']],'supports':[{'newsId':e['newsId'],'supportQuote':e['evidenceRecords'][0]['text']}]}
                for e in material['events'][:2]]
            return {'headline':'智能体测评的具体结果与复测安排',
                'lead':'本期分别核对来自不同团队的智能体测评材料，所有段落均对应原文公开记录，保留受控环境和后续复测的条件，不把并列报道解释为因果关系。',
                'chapters':chapters,'observations':observations}
        article=build_daily_deepread(items,{'deepread_core_events':4},self.now,{'provider':'deepseek'},provider)
        self.assertEqual(observed_chapters,[3])
        self.assertEqual(len(article['chapters']),3)
        self.assertEqual(article['generationStatus'],'ok')
        validate_complete(article)
