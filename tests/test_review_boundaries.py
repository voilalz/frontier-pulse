"""Authored adversarial reproductions of independent review findings."""
import copy
import signal
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import evidence_trace as trace
import event_identity as identity
import update_news as news
from deepread_editorial import build_legacy_daily_deepread as build_daily_deepread, _validated_observations

class ReviewBoundaryTests(unittest.TestCase):
    now = datetime(2026, 9, 26, 2, tzinfo=timezone.utc)
    def setUp(self):
        def timeout(*_): raise AssertionError('source validation exceeded 2 seconds')
        previous = signal.signal(signal.SIGALRM, timeout)
        self.addCleanup(signal.signal, signal.SIGALRM, previous)
        self.addCleanup(signal.setitimer, signal.ITIMER_REAL, 0)
        signal.setitimer(signal.ITIMER_REAL, 2)

    def records(self, text):
        return trace.make_evidence(text, 'https://nasa.gov/a', self.now.isoformat())
    def item(self, source, title='NASA完成无人机导航试验', editorial=None, key='a'):
        raw = news.Article(key, title, source, 'https://nasa.gov/'+key,
              'NASA', 'nasa.gov', '国际', self.now, category='航空航天')
        # Authored body fixture isolates semantic gates from feed selection.
        raw.source_evidence = trace.make_evidence(source, raw.url, self.now.isoformat())
        return news.item_from_article(raw, {}, editorial)

    def test_numeric_ownership_and_negation_are_preserved(self):
        for source, claim in [
            ('NASA报告无人机飞行30分钟，ESA报告无人机飞行300分钟。', 'NASA报告无人机飞行300分钟。'),
            ('NASA测试结果并不支持导航系统可靠。', 'NASA测试结果支持导航系统可靠。')]:
            with self.subTest(claim=claim):
                records = self.records(source); refs = [r['evidenceId'] for r in records]
                self.assertFalse(trace.validate_claim_refs(claim, refs, records))

    def test_summary_fact_and_publication_gates_reject_owned_number_swap(self):
        source = 'NASA报告无人机飞行30分钟，ESA报告无人机飞行300分钟。'
        claim = 'NASA报告无人机飞行300分钟。'
        item = self.item(source, editorial={'summary':claim, 'keyFacts':[claim]})
        self.assertEqual(item['summary'], source)
        self.assertNotIn(claim, item['keyFacts'])
        trace.validate_news_trace(item)
        bad = copy.deepcopy(item); bad['summary'] = claim
        with self.assertRaises(ValueError): trace.validate_news_trace(bad)
        article = build_daily_deepread([item], {}, self.now)
        trace.validate_deepread_trace(article)
        article['chapters'][0]['blocks'][0]['text'] = claim
        with self.assertRaises(ValueError): trace.validate_deepread_trace(article)

    def test_truncated_repetitive_claim_is_bounded(self):
        source = 'NASA完成无人机导航试验，'+'团队记录飞行路径并分析导航传感器输出，'*20+'飞行持续30分钟。'
        records = self.records(source)
        self.assertFalse(trace.validate_claim_refs(source[:139]+'…', [r['evidenceId'] for r in records], records))
        item = self.item(source, editorial={'summary': source[:139]+'…'})
        trace.validate_news_trace(item)

    def test_long_fallback_keeps_whole_bounded_excerpts(self):
        source = 'NASA完成无人机导航试验，'+'团队记录飞行路径并分析导航传感器输出，'*20+'飞行持续30分钟。'
        source += 'ESA完成另一项导航试验，'+'团队记录飞行路径并分析导航传感器输出，'*20+'飞行持续40分钟。'
        item = self.item(source)
        self.assertLessEqual(len(item['summary']), 600)
        trace.validate_news_trace(item)
        trace.validate_deepread_trace(build_daily_deepread([item], {}, self.now))

    def test_live_url_bridges_do_not_join_distinct_payloads(self):
        generic = {'id':'generic', 'originalTitle':'SpaceX launches Starlink satellites',
                   'url':'https://fixture.invalid/live', 'publishedAt':self.now.isoformat()}
        identity.assign_event_ids([generic], {}, {})
        registry = {'items':[{'eventId':generic['eventId'], 'newsIds':['generic'],
                             'identityRepresentatives':[identity.event_identity_record(generic)]}]}
        a = {**generic,'id':'first','originalTitle':'SpaceX launches Starlink 9-28'}
        c = {**generic,'id':'second','originalTitle':'SpaceX launches Starlink 9-29'}
        for history, batch in [(registry,[a,c]), ({},[a,generic,c])]:
            with self.subTest(registry=bool(history)):
                batch = copy.deepcopy(batch); identity.assign_event_ids(batch,history,{})
                by_id = {i['id']:i['eventId'] for i in batch}
                self.assertNotEqual(by_id['first'], by_id['second'])

    def test_observation_judgment_needs_proof_despite_valid_quote(self):
        selected = [self.item(f'{actor}报告无人机飞行30分钟，试验团队记录全部航迹数据。', key=str(n))
                    for n,actor in enumerate(['NASA','ESA'])]
        observations = [{'text':f'{actor}报告无人机飞行300分钟，说明续航已经达到新的阶段。',
             'newsIds':[item['id']], 'supports':[{'newsId':item['id'], 'supportQuote':item['summary']}]}
             for actor,item in zip(['NASA','ESA'],selected)]
        self.assertIsNone(_validated_observations(observations, selected,set()))
        article = build_daily_deepread(selected,{},self.now)
        for entry,item in zip(observations,selected):
            entry['supports'][0]['evidenceId'] = item['evidenceRecords'][0]['evidenceId']
        article['observations'] = observations
        with self.assertRaises(ValueError): trace.validate_deepread_trace(article)

    def test_technical_campaign_and_regulation_survive_body_filter(self):
        for source in ['NASA completed the drone flight test campaign at the desert range.',
                       'NASA completed the launch campaign for the drone navigation experiment.',
                       'NASA tested a control policy for drone navigation in a simulation.',
                       'NASA tested voltage regulation in the drone navigation system.']:
            with self.subTest(source=source):
                item = self.item(source,'NASA completes drone flight tests')
                article = build_daily_deepread([item],{},self.now)
                self.assertEqual(article['eventCount'],1)
                trace.validate_deepread_trace(article)
        item = self.item('The president announced a campaign to win the next election.','NASA completes drone flight tests')
        self.assertEqual(build_daily_deepread([item],{},self.now)['eventCount'],0)

    def test_title_rewrite_cannot_change_phase_negation_or_actor(self):
        for original, rewritten, source in [
            ('NASA计划完成无人机导航试验','NASA完成无人机导航试验','NASA计划完成无人机导航试验。'),
            ('NASA无人机导航试验失败','NASA无人机导航试验成功','NASA无人机导航试验失败。'),
            ('NASA完成无人机导航试验','ESA完成无人机导航试验','NASA完成无人机导航试验。')]:
            with self.subTest(original=original):
                item = self.item(source+' '+original+'，报告记录了本次测试的具体条件与后续核对安排。',original,{'titleZh':rewritten})
                item['evidenceRecords'] = trace.make_evidence(item['summary'], item['url'], self.now.isoformat(), 'body')
                item['summaryEvidenceRefs'] = trace.trace_claim(item['summary'], item['evidenceRecords'])
                self.assertEqual(item['title'],original)
                bad = copy.deepcopy(item); bad['title'] = rewritten
                with self.assertRaises(ValueError): trace.validate_news_trace(bad)
                article = build_daily_deepread([item],{},self.now)
                article['events'][0]['title'] = rewritten
                with self.assertRaises(ValueError): trace.validate_deepread_trace(article)

    def test_publication_framing_cannot_hide_an_unsupported_number(self):
        item = self.item('NASA报告无人机飞行30分钟，试验团队记录全部航迹数据。')
        article = build_daily_deepread([item], {}, self.now)
        for field in ['headline', 'lead', 'chapter-title', 'chapter-angle']:
            bad = copy.deepcopy(article)
            if field.startswith('chapter-'):
                bad['chapters'][0][field.split('-')[1]] = 'NASA报告无人机飞行300分钟。'
            else:
                bad[field] = 'NASA报告无人机飞行300分钟。'
            with self.subTest(field=field), self.assertRaises(ValueError):
                trace.validate_deepread_trace(bad)

    def test_outline_title_and_angle_are_grounded_before_rendering(self):
        items = [self.item(f'{actor}报告无人机飞行30分钟，试验团队记录全部航迹数据。',
                           f'{actor}完成无人机导航试验', key=str(index))
                 for index, actor in enumerate(['NASA','ESA','JAXA','ISRO'])]
        def provider(_runtime, **request):
            if request['schema_name'] == 'deepread_outline_v2':
                return {'selectedNewsIds':[item['id'] for item in items], 'chapters':[
                    {'title':'NASA报告无人机飞行300分钟。' if index==0 else item['title'],
                     'angle':'NASA已经证实可以安全量产无人机。',
                     'newsIds':[item['id']], 'kind':'event', 'comparisonKey':''}
                    for index,item in enumerate(items)]}
            return {}
        article = build_daily_deepread(items, {}, self.now, {'provider':'fixture'}, provider)
        self.assertNotIn('300', article['chapters'][0]['title'])
        self.assertNotIn('量产', article['chapters'][0]['angle'])
        trace.validate_deepread_trace(article)

if __name__ == '__main__': unittest.main()
