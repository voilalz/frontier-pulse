"""Regressions for the review's real failure modes, without a live model call."""
import copy
import json
import sys
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from deepread_editorial import build_daily_deepread
from deepread_quality import choose_readable_deepread, validate_readable
from evidence_trace import make_evidence, prose_translation_issue

NOW = datetime(2026, 10, 8, 1, tzinfo=timezone.utc)


def story(news_id, title, category='AI', source='Lab Journal', body=None, **fields):
    url = f'https://example.org/{news_id}'
    body = body or ('Aster Labs plans to test its new autonomous navigation model in a limited simulation before any field deployment. '
                    'The company has not published field results or independent validation, and the present release describes only the test protocol.')
    records = make_evidence(body, url, NOW.isoformat())
    return dict(id=news_id, eventId='evt-'+news_id, title=title, originalTitle=title,
                summary=records[0]['text'], evidenceRecords=records,
                summaryEvidenceRefs=[records[0]['evidenceId']], evidenceText=body,
                evidenceFetchedAt=NOW.isoformat(), publishedAt='2026-10-08T00:00:00Z',
                source=source, sources=[dict(name=source, url=url)], url=url,
                contentType='news', category=category, score=80, **fields)


class ReviewRegressions(unittest.TestCase):
    def test_abbreviations_do_not_split_a_source_claim(self):
        text = 'The U.S. Navy said Dr. Smith and Adm. Brown tested a sensor. The U.K. team reported results.'
        records = make_evidence(text, 'https://example.org/source', NOW.isoformat())
        self.assertEqual([r['text'] for r in records], [
            'The U.S. Navy said Dr. Smith and Adm. Brown tested a sensor.',
            'The U.K. team reported results.'])

    def test_some_and_capability_could_have_chinese_synonyms(self):
        source = 'Some onboard sensors could detect obstacles in a simulation.'
        refs = ['evd-'+'1'*20]
        value = dict(version=1, language='zh-CN', provider='deepseek',
                     text='有些机载传感器可以在仿真中探测障碍物。',
                     sourceText=source, sourceEvidenceRefs=refs)
        self.assertEqual(prose_translation_issue(value, source, refs), '')
        value['text'] = '所有机载传感器已经在实际环境中探测到障碍物。'
        self.assertTrue(prose_translation_issue(value, source, refs))

    def test_old_complete_edition_cannot_be_retained_for_two_days(self):
        previous = json.loads((ROOT/'public/data/deepread.json').read_text())
        self.assertEqual(previous['editionDate'], '2026-10-07')
        result = choose_readable_deepread({'generationStatus':'failed'}, [previous], '2026-10-09')
        self.assertNotEqual(result['readerStatus'], 'retained')

    def test_different_ids_for_identical_investment_merge_before_topic_selection(self):
        a = story('anduril-a', 'Anduril invests $6.6 billion in new manufacturing', '军事动态')
        b = story('anduril-b', 'Anduril invests $6.6 billion in new manufacturing', '军事动态', source='Second Journal')
        report = build_daily_deepread([a,b], {}, NOW)
        self.assertEqual(report['candidateCount'], 1)
        self.assertEqual(len(report['events'][0]['sources']), 2)

    def test_commentary_and_football_activity_are_not_deepread_topics(self):
        opinion = story('opinion', 'Why modular acquisition matters', articleType='opinion')
        activity = story('nfl', 'NASA astronaut joins NFL fans in Philadelphia', '航空航天')
        report = build_daily_deepread([opinion,activity], {}, NOW)
        self.assertEqual(report['candidateCount'], 0)

    def test_illustrations_and_routine_military_exercises_are_not_topics(self):
        image = story('image','NASA’s PRIMA Spacecraft (Artist’s Concept)','航空航天')
        routine = story('exercise','British Commandos Emerge From German Submarine During Major NATO Exercise','军事动态')
        self.assertEqual(build_daily_deepread([image,routine],{},NOW)['candidateCount'],0)


BODY = ('Aster Labs tested its autonomous navigation model in a closed simulation using recorded images, and the release describes only this limited evaluation rather than a field deployment. '
        'The evaluation compares the proposed navigation model with the previous baseline on the same recorded image sequences; the company has not published independent validation or flight results.')
FACTS = [
    '据材料披露，Aster Labs只在封闭仿真中测试了自主导航模型，评估使用已经记录的图像；这次发布所描述的范围仍仅限于这项模拟评估，并不是在实际飞行环境中开展部署。',
    '据材料披露，该项评估把拟议导航模型与此前基线放在相同的图像序列上进行比较；公司尚未公布独立验证或飞行结果，目前披露的对比范围仍只涉及这些已有记录。']
ANALYSIS = ('这项材料需要讨论的具体问题，是同一批图像上的模型比较能够说明什么。'
    '相同输入给方法比较提供了共同起点，读者仍需区分模型处理记录与传感器实际采集之间的差别。'
    '封闭仿真中的问题可以被重复检查，现场环境中的光照、遮挡与运动条件是否同样成立，在本次材料中还没有相应记录。'
    '把当前结果理解为对特定输入的评价，比直接据此判断整套导航系统是否成熟更有依据。'
    '在阅读比较结果时，还应查看基线选择、输入处理与评估条件是否公开；缺少这些信息，读者难以判断不同方法的差别来自何处，也难以复现同样的比较过程。')
WATCH = ('后续需要核对的是，公开材料是否补上实际飞行的输入和结果，是否说明图像记录与现场环境之间的差别，以及是否提供独立复核所需的条件。'
         '这些问题用于界定本次报告的适用范围，并不预先假定后续测试能够成功，也不把材料尚未说明的事项写成已经被证明不存在。')


class EditorialProvider:
    """The only fake is the external model boundary; validation remains real."""
    def __init__(self, fail=None, semantic=False, checker_down=False, shallow=False):
        self.fail, self.semantic, self.checker_down = fail, semantic, checker_down
        self.shallow=shallow
        self.written = []
        self.feedback = []

    def __call__(self, runtime, **kwargs):
        data = json.loads(kwargs['input_text'])
        if kwargs['schema_name'] == 'deepread_topics_v13':
            return {'topics':[{'title':'自主导航仿真结果的适用边界', 'angle':'从记录图像上的对比出发，核对本次评估的条件，以及实际飞行和独立复核还需要补充的证据。',
                'newsIds':[e['newsId']]} for e in data['candidates'][:2]]}
        if kwargs['schema_name'] == 'deepread_topic_write_v13':
            event = data['events'][0]; news = event['newsId']; self.written.append(news)
            self.feedback.extend(data['validationFeedback'])
            refs = [r['evidenceId'] for r in event['evidenceRecords']]
            texts = list(FACTS)
            if news == self.fail:
                texts[1] += '该系统已经获得正式飞行认证。' if self.semantic else '已经完成9999次飞行认证。'
            return {'title':'自主导航仿真结果的适用边界', 'angle':'从记录图像上的对比出发，核对本次评估的条件，以及实际飞行和独立复核还需要补充的证据。',
                'framingEvidenceIds':refs[:2], 'blocks':[
                    {'type':'paragraph','newsIds':[news],'sentences':[{'text':texts[0],'evidenceIds':refs[:1]}]},
                    {'type':'paragraph','newsIds':[news],'sentences':[{'text':texts[1],'evidenceIds':refs[1:2]}]},
                    {'type':'analysis','newsIds':[news],'sentences':[{'text':ANALYSIS,'evidenceIds':refs[:2]}]},
                    {'type':'watch','newsIds':[news],'sentences':[{'text':WATCH,'evidenceIds':refs[:2]}]}]}
        if kwargs['schema_name'] == 'deepread_topic_check_v13':
            if self.checker_down:
                raise RuntimeError('private provider response must not reach public status')
            return {'checks':[{'id':c['id'],'verdict':'unsupported' if '已经获得正式飞行认证' in c['text'] else 'supported',
                'reason':'引文没有提供认证事实。' if '已经获得正式飞行认证' in c['text'] else ''} for c in data['claims']],
                'editorialReview':{'verdict':'rewrite' if self.shallow else 'ready',
                    'reason':'仍在复述消息，缺少具体方法或约束解释。' if self.shallow else ''}}
        raise AssertionError(kwargs['schema_name'])


class TopicPublicationTests(unittest.TestCase):
    def inputs(self):
        return [story('navigation','Aster Labs navigation simulation results',body=BODY),
                story('sensor','Optical sensing benchmark protocol','前沿技术',body=BODY)]

    def build(self, provider, **kwargs):
        return build_daily_deepread(self.inputs(),{},NOW,{'provider':'deepseek'},provider,**kwargs)

    def test_one_bad_topic_does_not_discard_the_supported_topic(self):
        provider = EditorialProvider(fail='sensor')
        draft = self.build(provider)
        reader = choose_readable_deepread(draft,[], '2026-10-08')
        self.assertEqual(reader['readerStatus'],'partial')
        self.assertEqual(len(reader['chapters']),1)
        self.assertIn('适用边界',reader['headline'])
        self.assertTrue(any(i['rule'].startswith('quantity:') for i in draft['contentFailures']))
        self.assertTrue(any(i['rule'].startswith('quantity:') for i in provider.feedback))
        validate_readable(reader,'2026-10-08')

    def test_independent_semantic_check_rejects_added_non_numeric_fact(self):
        draft = self.build(EditorialProvider(fail='sensor',semantic=True))
        self.assertEqual(len(draft['chapters']),1)
        self.assertTrue(any(i['rule']=='semantic-unsupported' for i in draft['contentFailures']))

    def test_checker_failure_never_publishes_unchecked_prose(self):
        draft = self.build(EditorialProvider(checker_down=True))
        self.assertEqual(draft['chapters'],[])
        self.assertTrue(any(i['rule']=='checker-request-failed' for i in draft['contentFailures']))
        self.assertNotIn('private provider',json.dumps(draft))

    def test_factually_supported_but_shallow_chapter_is_rewritten_and_rejected(self):
        provider=EditorialProvider(shallow=True)
        draft=self.build(provider)
        self.assertEqual(draft['chapters'],[])
        self.assertTrue(any(i['rule']=='editorial-depth' for i in draft['contentFailures']))
        self.assertTrue(any(i['rule']=='editorial-depth' for i in provider.feedback))

    def test_recovery_reuses_supported_topic_and_only_writes_the_missing_one(self):
        initial = choose_readable_deepread(self.build(EditorialProvider(fail='sensor')),[],'2026-10-08')
        provider = EditorialProvider()
        recovered = self.build(provider,existing_article=initial)
        reader = choose_readable_deepread(recovered,[],'2026-10-08')
        self.assertEqual(provider.written,['sensor'])
        self.assertEqual(reader['chapters'][0]['blocks'],initial['chapters'][0]['blocks'])
        self.assertEqual(len(reader['chapters']),2)

    def test_changing_a_checked_fact_invalidates_its_binding(self):
        draft = self.build(EditorialProvider())
        draft['chapters'][0]['blocks'][0]['sentences'][0]['text'] = '据报道，模型已经可以在全球范围内安全部署。'
        draft['chapters'][0]['blocks'][0]['text'] = draft['chapters'][0]['blocks'][0]['sentences'][0]['text']
        reader = choose_readable_deepread(draft,[],'2026-10-08')
        self.assertEqual(len(reader['chapters']),1)

    def test_brief_title_and_links_must_match_the_source_bound_catalog(self):
        items=self.inputs()
        for item in items:
            item['displayTranslation']={'version':1,'language':'zh-CN','provider':'deepseek',
                'title':'自主导航仿真评估结果','summary':FACTS[0],
                'sourceTitle':item['originalTitle'],'sourceSummary':item['summary'],
                'sourceEvidenceRefs':item['summaryEvidenceRefs']}
        draft=build_daily_deepread(items,{},NOW)
        reader=choose_readable_deepread(draft,[],'2026-10-08')
        self.assertEqual(reader['readerStatus'],'brief')
        validate_readable(reader,'2026-10-08')
        for fault in ('title','link','id'):
            with self.subTest(fault=fault):
                broken=copy.deepcopy(reader)
                if fault=='title': broken['briefs'][0]['title']='系统已经完成全球商业部署'
                elif fault=='link': broken['briefs'][0]['sources'][0]['url']='https://example.org/unrelated'
                else: broken['briefs'][0]['newsIds']=['foreign-news']
                with self.assertRaises(ValueError): validate_readable(broken,'2026-10-08')

    def test_failed_recovery_keeps_same_day_accepted_partial_content(self):
        previous = choose_readable_deepread(self.build(EditorialProvider(fail='sensor')),[],'2026-10-08')
        failed = {'schemaVersion':2,'generationRevision':13,'editionDate':'2026-10-08',
                  'generationStatus':'failed','events':[],'chapters':[],'eventCount':0,'candidateCount':0}
        result = choose_readable_deepread(failed,[previous],'2026-10-08')
        self.assertEqual(result['readerStatus'],'partial')
        self.assertEqual(result['chapters'],previous['chapters'])

    def test_recovery_keeps_accepted_topic_missing_from_stream_cap(self):
        previous = choose_readable_deepread(self.build(EditorialProvider(fail='sensor')),[],'2026-10-08')
        provider = EditorialProvider()
        result = build_daily_deepread(self.inputs()[1:],{},NOW,{'provider':'deepseek'},provider,existing_article=previous)
        result = choose_readable_deepread(result,[],'2026-10-08')
        self.assertEqual(len(result['chapters']),2)
        self.assertEqual(result['chapters'][0]['blocks'],previous['chapters'][0]['blocks'])
        self.assertEqual(provider.written,['sensor'])

    def test_recovery_keeps_failed_topic_inputs_missing_from_live_stream(self):
        previous = choose_readable_deepread(self.build(EditorialProvider(fail='sensor')),[],'2026-10-08')
        self.assertNotIn('sensor',[e['newsId'] for e in previous['events']])
        provider = EditorialProvider()
        recovered = build_daily_deepread(self.inputs()[:1],{},NOW,{'provider':'deepseek'},provider,existing_article=previous)
        self.assertEqual(provider.written,['sensor'])
        self.assertEqual(len(recovered['chapters']),2)

    def test_recovery_uses_original_capture_when_live_source_has_changed(self):
        previous = choose_readable_deepread(self.build(EditorialProvider(fail='sensor')),[],'2026-10-08')
        altered = story('navigation','Aster Labs navigation simulation results',body=BODY.replace('closed simulation','field deployment'))
        provider = EditorialProvider()
        recovered = build_daily_deepread([altered,self.inputs()[1]],{},NOW,{'provider':'deepseek'},provider,existing_article=previous)
        self.assertEqual(provider.written,['sensor'])
        self.assertEqual(recovered['chapters'][0]['blocks'],previous['chapters'][0]['blocks'])

    def test_project_history_uses_captured_sources_and_prior_watch_questions(self):
        prior = story('old-m51','M51 missile prepares a test','军事动态',body=BODY)
        prior['editionDate']='2026-10-07'
        prior['watchFor']=['是否公开实际测试条件？']
        current = story('new-m51','M51 missile reports a test','军事动态',body=BODY)
        seen=[]
        def provider(runtime,**kwargs):
            if kwargs['schema_name']=='deepread_topic_write_v13':
                seen.extend(json.loads(kwargs['input_text'])['events'])
            return EditorialProvider()(runtime,**kwargs)
        draft=build_daily_deepread([current],{},NOW,{'provider':'deepseek'},provider,history_items=[prior])
        self.assertEqual(len(draft['chapters']),1)
        self.assertEqual(seen[0]['previousProject'][0]['evidenceRecords'],prior['evidenceRecords'])
        self.assertEqual(seen[0]['previousWatchFor'],prior['watchFor'])

    def test_generation_time_budget_preserves_finished_topics_and_bounds_provider_calls(self):
        clock=[0.0]; provider=EditorialProvider(); observed=[]
        def request(runtime,**kwargs):
            observed.append(runtime)
            result=provider(runtime,**kwargs)
            if kwargs['schema_name']=='deepread_topic_check_v13': clock[0]=31.0
            return result
        with patch('time.monotonic',side_effect=lambda:clock[0]):
            draft=build_daily_deepread(self.inputs(),{'deepread_generation_budget_seconds':30},NOW,
                {'provider':'deepseek'},request)
        self.assertEqual(provider.written,['navigation'])
        self.assertEqual(len(draft['chapters']),1)
        self.assertTrue(any(i['rule']=='generation-time-budget-exhausted' for i in draft['contentFailures']))
        self.assertTrue(all(r['httpAttempts']==1 and r['requestTimeoutSeconds']<=30 for r in observed))

    def test_different_products_from_same_company_are_not_duplicate_reports(self):
        a = story('ghost','Anduril unveils Ghost autonomous drone for military reconnaissance')
        b = story('anvil','Anduril unveils Anvil autonomous drone for military reconnaissance')
        result = build_daily_deepread([a,b],{},NOW)
        self.assertEqual(result['candidateCount'],2)


if __name__ == '__main__':
    unittest.main()
