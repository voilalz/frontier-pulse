"""Reader completion follows verified content, including recovered/legacy prose."""
import copy
import json
import unittest
from datetime import datetime, timezone

import test_batch1_deepread_quality as quality_tests
import test_news_reading as reading_tests
import test_publication as publication_tests
from deepread_quality import choose_readable_deepread, validate_complete
from unittest.mock import patch


class DeepreadRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        quality_tests.DeepreadQualityTests.setUpClass()
        cls.good = copy.deepcopy(quality_tests.DeepreadQualityTests.good)

    def test_complete_recovered_content_is_not_rejected_by_partial_generation_label(self):
        draft = copy.deepcopy(self.good)
        draft['generationStatus'] = 'partial'
        validate_complete(draft)
        result = choose_readable_deepread(draft, [], draft['editionDate'])
        self.assertEqual(result['readerStatus'], 'complete')
        self.assertEqual(result['generationStatus'], 'ok')
        self.assertEqual(result['generationAttemptStatus'], 'partial')

    def test_partial_label_does_not_authorize_a_short_or_unbound_chapter(self):
        for fault in ('short', 'unbound'):
            draft = copy.deepcopy(self.good)
            draft['generationStatus'] = 'partial'
            if fault == 'short':
                draft['chapters'][0]['blocks'] = draft['chapters'][0]['blocks'][:1]
            else:
                draft['chapters'][0]['blocks'][0]['evidenceIds'] = ['missing']
            result = choose_readable_deepread(draft, [], draft['editionDate'])
            self.assertEqual(result['readerStatus'], 'unavailable')
            self.assertNotEqual(result['qualityFailures'], ['generation-incomplete'])
            self.assertEqual(result['generationDiagnostics']['candidateCount'], draft['candidateCount'])

    def test_legacy_metadata_filler_is_removed_only_when_bound_translation_remains_valid(self):
        previous = copy.deepcopy(self.good)
        previous['events'][0]['displayTranslation']['summary'] += '现有元数据未提供更多摘要。'
        original = copy.deepcopy(previous)
        result = choose_readable_deepread({'generationStatus':'failed'}, [previous], '2026-07-17')
        self.assertEqual(result['readerStatus'], 'retained')
        self.assertNotIn('现有元数据', result['events'][0]['displayTranslation']['summary'])
        self.assertEqual(previous, original)
        previous['events'][0]['displayTranslation']['sourceSummary'] = 'Unrelated source.'
        rejected = choose_readable_deepread({'generationStatus':'failed'}, [previous], '2026-07-17')
        self.assertEqual(rejected['readerStatus'], 'unavailable')

    def test_legacy_complete_archive_without_reader_status_renders_verified_content(self):
        case = reading_tests.NewsReadingTests(); case.setUp()
        original = copy.deepcopy(self.good)
        normalized = case.browser_result('normalizeDeepreadForReader('+json.dumps(original)+')')
        self.assertEqual(normalized['readerStatus'], 'complete')
        rendered = case.browser_result('normalizeDeepreadForReader('+json.dumps(original)+').then(renderDeepreadArticle)')
        self.assertIn('deepread-article', rendered)
        self.assertEqual(original, self.good)

    def test_legacy_archive_cannot_infer_completion_after_losing_source_binding(self):
        case = reading_tests.NewsReadingTests(); case.setUp()
        draft=copy.deepcopy(self.good)
        draft['chapters'][0]['blocks'][0]['evidenceIds']=['evd-'+'0'*20]
        normalized=case.browser_result('normalizeDeepreadForReader('+json.dumps(draft)+')')
        self.assertEqual(normalized['readerStatus'],'unavailable')
        rendered=case.browser_result('normalizeDeepreadForReader('+json.dumps(draft)+').then(renderDeepreadArticle)')
        self.assertIn('深读生成失败',rendered)
        self.assertNotIn('<article',rendered)

    def test_traceable_old_short_edition_is_only_readable_as_a_historical_simple_edition(self):
        case=reading_tests.NewsReadingTests();case.setUp()
        draft=copy.deepcopy(self.good)
        draft['generationStatus']='partial'
        draft['chapters'][0]['blocks']=draft['chapters'][0]['blocks'][:1]
        expression='normalizeDeepreadForReader('+json.dumps(draft)+')'
        self.assertEqual(case.browser_result(expression)['readerStatus'],'legacy')
        self.assertNotIn('<article',case.browser_result(expression+'.then(renderDeepreadArticle)'))
        rendered=case.browser_result("(state.historicalSelection=true,"+expression+".then(renderDeepreadArticle))")
        self.assertIn('历史简版',rendered)
        self.assertIn('deepread-article',rendered)
        self.assertEqual(choose_readable_deepread(draft,[],draft['editionDate'])['readerStatus'],'unavailable')

    def test_legacy_completion_rejects_forged_framing_comparison_and_evidence_hash(self):
        case=reading_tests.NewsReadingTests();case.setUp()
        for fault in ('headline','angle','comparison','evidence','event-title'):
            with self.subTest(fault=fault):
                draft=copy.deepcopy(self.good)
                forged='卫星已经发射9999枚载荷，所有测试均已获得成功。'
                if fault=='headline': draft['headline']=forged
                elif fault=='angle': draft['chapters'][0]['angle']=forged
                elif fault=='evidence': draft['events'][0]['evidenceRecords'][0]['text']+=' Uncaptured claim.'
                elif fault=='event-title':
                    draft['events'][0]['title']=forged
                    draft['events'][0].pop('displayTranslation',None)
                    draft['chapters'][0]['title']=forged
                else:
                    left,right=draft['chapters'][:2]
                    left.update(kind='comparison',comparisonKey='ai-agent',title='AI 智能体：两项独立进展',
                        angle='分别核对两项报道在AI 智能体上披露的事实与未知事项',newsIds=left['newsIds']+right['newsIds'],
                        blocks=left['blocks']+right['blocks']+[{'type':'comparison','text':forged,
                            'newsIds':left['newsIds']+right['newsIds'],'evidenceIds':['evd-'+'0'*20]}])
                    draft['chapters'].pop(1)
                normalized=case.browser_result('normalizeDeepreadForReader('+json.dumps(draft)+')')
                self.assertEqual(normalized['readerStatus'],'unavailable')

    def test_failed_deepread_is_independently_recorded_without_marking_daily_failed(self):
        from deepread_quality import deepread_status
        reader = choose_readable_deepread({'generationStatus':'failed','candidateCount':12}, [], '2026-07-17')
        state = deepread_status(reader, '2026-07-17')
        self.assertEqual(state['state'], 'failed')
        self.assertEqual(state['errorCode'], 'deepread-unavailable')
        self.assertEqual(state['diagnostics']['candidateCount'], 12)

    def test_chapter_recovery_retries_only_bad_chapters_and_completes_observations(self):
        from deepread_editorial import build_daily_deepread
        from evidence_trace import make_evidence, trace_claim
        now = datetime(2026,7,16,tzinfo=timezone.utc)
        items=[]
        for i,actor in enumerate('甲乙丙丁'):
            title=actor+'团队公布卫星载荷试验结果'
            first=title+'，报告列出本次测试的运行条件以及测量记录，便于后续核对已完成的工作。'
            second=actor+'团队介绍卫星载荷后续试验安排，工程人员将依据已有记录继续开展受控试验，核对设备在不同条件下的表现。'
            url=f'https://publisher.example/satellite-{i}'
            records=make_evidence(first+' '+second,url,now.isoformat(),'body')
            items.append({'id':f'satellite-{i}','eventId':f'evt-{i:012x}','title':title,'originalTitle':title,
                'summary':first,'summaryEvidenceRefs':trace_claim(first,records),'evidenceRecords':records,
                'url':url,'sources':[{'name':actor+'团队','url':url}],'category':'航空航天',
                'publishedAt':'2026-07-15T23:00:00Z','score':90-i})
        attempts={}
        prose_case="empty"
        def provider(runtime, **kwargs):
            material=json.loads(kwargs['input_text'])
            schema=kwargs['schema_name']
            if schema=='deepread_outline_v2':
                ids=material['fixedSelectedNewsIds']
                return {'selectedNewsIds':ids,'chapters':[{'title':next(x['title'] for x in items if x['id']==key),
                    'angle':'追踪本次报道中的具体变化','newsIds':[key],'kind':'event','comparisonKey':''} for key in ids]}
            if schema=='deepread_prose_v2':
                if prose_case=='empty': return {}
                chapters={c['id']:{'blocks':[{'type':'paragraph','text':r['text'],'sourceText':r['text'],
                    'newsIds':[e['newsId']],'evidenceIds':[r['evidenceId']]} for e in material['events']
                    if e['newsId'] in c['newsIds'] for r in e['evidenceRecords']]} for c in material['outline'][:-1]}
                # Missing a chapter and malformed framing must not erase valid chapters.
                return {'headline':'坏','chapters':chapters}

            if schema=='deepread_chapter_v2':
                key=material['chapterId'];attempts[key]=attempts.get(key,0)+1
                blocks=[{'type':'paragraph','text':r['text'],'sourceText':r['text'],'newsIds':[e['newsId']],
                    'evidenceIds':[r['evidenceId']]} for e in material['events'] for r in e['evidenceRecords']]
                if key=='chapter-1' and attempts[key]==1: blocks=blocks[:1]
                return {'blocks':blocks}
            if schema=='deepread_observations_v2':
                candidates=list({c['newsId']:c for c in reversed(material['candidates'])}.values())[:2]
                return {'observations':[{'text':c['sourceText'],'sourceText':c['sourceText'],
                    'newsIds':[c['newsId']],'supports':[{'newsId':c['newsId'],'supportQuote':c['sourceText']}]}
                    for c in candidates]}
            raise AssertionError(schema)
        result=build_daily_deepread(items,{'deepread_core_events':4},now,{'provider':'deepseek'},provider)
        self.assertEqual(attempts, {'chapter-1':2,'chapter-2':1,'chapter-3':1,'chapter-4':1})
        self.assertEqual(result['generationStatus'],'ok')
        validate_complete(result)
        attempts.clear();prose_case='missing-last'
        result=build_daily_deepread(items,{'deepread_core_events':4},now,{'provider':'deepseek'},provider)
        self.assertEqual(attempts,{'chapter-4':1})
        self.assertEqual(result['generationStatus'],'ok')
        self.assertEqual(result['recoveryDiagnostics']['chapters']['chapter-1'],{'state':'reused','attempts':0})
        validate_complete(result)


class DeepreadOnlyPublicationTests(unittest.TestCase):
    setUpClass=classmethod(publication_tests.PublicationTests.setUpClass.__func__)
    tearDownClass=classmethod(publication_tests.PublicationTests.tearDownClass.__func__)
    setUp=publication_tests.PublicationTests.setUp
    promote=publication_tests.PublicationTests.promote

    def missing_reader(self):
        self.good=publication_tests.load(self.stage/'data/deepread.json')
        failed=choose_readable_deepread({'generationStatus':'failed'}, [], '2026-07-16')
        publication_tests.save(self.stage/'data/deepread.json',failed)
        publication_tests.save(self.stage/'data/deepread/2026-07-16.json',failed)
        self.promote('r-original')

    def recover(self, result):
        import recover_deepread
        now=datetime(2026,7,16,1,tzinfo=timezone.utc)
        with patch.object(recover_deepread,'build_daily_deepread',return_value=result) as build:
            state=recover_deepread.recover(self.public,self.stage,{'archive_retention_days':730},now,None,None,'test-revision')
        return state,build

    def test_deepread_only_correction_preserves_daily_content_and_initial_version(self):
        self.missing_reader()
        before=publication_tests.load(self.public/'data/news.json')
        state,build=self.recover(self.good)
        after=publication_tests.load(self.public/'data/news.json')
        self.assertEqual(state['state'],'ok')
        self.assertTrue(state['changed'])
        self.assertEqual(after['items'],before['items'])
        self.assertEqual(after['brief'],before['brief'])
        self.assertEqual(after['generatedAt'],before['generatedAt'])
        self.assertEqual(after['publicationRevision']['changes'],{'added':[],'removed':[],'corrected':[]})
        original=publication_tests.load(self.public/'data/edition-versions/r-original.json')
        self.assertEqual(original['news'],before)
        self.assertEqual(original['deepread']['readerStatus'],'unavailable')
        self.assertEqual(build.call_args.args[2],datetime(2026,7,16,tzinfo=timezone.utc))

    def test_failed_deepread_recovery_publishes_its_error_but_daily_stays_ok(self):
        self.missing_reader()
        state,_=self.recover({'generationStatus':'failed','candidateCount':12,'warnings':['恢复校验失败。']})
        status=publication_tests.load(self.public/'data/status.json')
        self.assertEqual(state['state'],'failed')
        self.assertTrue(state['changed'])
        self.assertEqual(status['state'],'ok')
        self.assertEqual(status['deepread']['errorCode'],'deepread-unavailable')
        self.assertEqual(status['deepread']['diagnostics']['candidateCount'],12)

    def test_complete_edition_is_not_regenerated(self):
        self.promote('r-original')
        state,build=self.recover({})
        self.assertEqual(state['state'],'ok')
        self.assertFalse(state['changed'])
        build.assert_not_called()

    def test_recovery_uses_formal_registry_and_preserves_newer_live_registry(self):
        self.missing_reader()
        original=publication_tests.load(self.public/'releases/r-original/data/events.json')
        live=copy.deepcopy(original);live['identityAliases']={'evt-later-alias':'evt-later-canonical'}
        publication_tests.save(self.public/'data/events.json',live)
        state,build=self.recover(self.good)
        self.assertEqual(state['state'],'ok')
        self.assertEqual(build.call_args.kwargs['event_registry'],original)
        self.assertEqual(publication_tests.load(self.public/'data/events.json')['identityAliases'],live['identityAliases'])

    def test_a_concurrent_stream_update_cannot_be_overwritten_by_deepread_recovery(self):
        import recover_deepread
        self.missing_reader()
        fresh_stage=self.stage.parent/'fresh-stream'
        publication_tests.pub.prepare_stage(self.public,fresh_stage)
        stream=publication_tests.load(fresh_stage/'data/stream.json')
        stream['generatedAt']='2026-07-16T01:00:00Z'
        publication_tests.save(fresh_stage/'data/stream.json',stream)
        def generate(*args,**kwargs):
            publication_tests.pub.promote(fresh_stage,self.public,'stream','ignored','test')
            return self.good
        with patch.object(recover_deepread,'build_daily_deepread',side_effect=generate):
            with self.assertRaisesRegex(ValueError,'base stream changed'):
                recover_deepread.recover(self.public,self.stage,{},datetime(2026,7,16,1,tzinfo=timezone.utc),None,None)
        self.assertEqual(publication_tests.load(self.public/'data/stream.json')['generatedAt'],'2026-07-16T01:00:00Z')
        self.assertEqual(publication_tests.load(self.public/'data/release.json')['releaseId'],'r-original')


if __name__ == '__main__': unittest.main()
