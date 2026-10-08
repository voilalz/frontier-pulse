"""Depth changes: reasoned analysis, anchored qualifiers, storylines and salvage."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))

from deepread_editorial import build_daily_deepread
from deepread_topic_quality import qualifier_flags, rule_issue
from deepread_topics import prepare_candidates, project_keys
from evidence_trace import make_evidence
from test_deepread_topics import BODY, NOW, EditorialProvider, story


def records_for(source):
    rows = make_evidence(source, 'https://example.org/f47', NOW.isoformat())
    return {row['evidenceId']: row for row in rows}


class AnalysisRules(unittest.TestCase):
    def setUp(self):
        self.records = records_for('Aster Labs tested its navigation model only in a closed simulation using recorded images.')
        self.refs = list(self.records)

    def test_reasoned_causal_analysis_is_left_to_the_checker(self):
        text = '评估只用了已记录的图像，因此它能说明模型处理既有数据的表现，还不能说明现场飞行的表现。'
        self.assertEqual(rule_issue(text, 'analysis', self.refs, self.records), '')

    def test_short_term_quotes_pass_but_invented_quotations_do_not(self):
        self.assertEqual(rule_issue('所谓“封闭仿真”，指输入事先录好的评估方式。', 'analysis', self.refs, self.records), '')
        self.assertEqual(rule_issue('负责人称“这套模型已经可以直接上机飞行了”。', 'analysis', self.refs, self.records),
                         'analysis-new-quotation')


class AnchoredQualifiers(unittest.TestCase):
    def test_qualifier_on_the_claimed_clause_is_still_a_hard_failure(self):
        records = records_for('The F-47 will begin flight tests in 2028.')
        self.assertEqual(rule_issue('F-47已于2028年开始飞行测试。', 'fact', list(records), records),
                         'qualifier:planned')

    def test_plan_in_an_unrelated_clause_is_flagged_for_the_checker_not_rejected(self):
        records = records_for('Engineers completed the ground vibration test of the F-47 airframe, '
                              'and Boeing will publish the data next year.')
        text = '工程师已完成F-47机体的地面振动试验。'
        self.assertEqual(rule_issue(text, 'fact', list(records), records), '')
        self.assertEqual(qualifier_flags(text, list(records), records), ['planned'])

    def test_negation_stays_a_hard_rule(self):
        records = records_for('The company has not published field results for the F-47 sensor.')
        self.assertTrue(rule_issue('该公司已经公布F-47传感器的外场结果。', 'fact', list(records), records))


CUAS = ('The counter-drone system was demonstrated against small quadcopters at a test range, and the release describes only this limited demonstration. '
        'The company has not published independent test results, and it describes the demonstration rather than a deployment.')


class Storylines(unittest.TestCase):
    def test_counter_drone_reports_share_a_storyline_key(self):
        for title in ('EOS unveils next-generation Slinger C-UAS system',
                      'AERO Vodochody and Thales Belgium advance Skyfox counter-drone development'):
            self.assertIn('story:counter-uas', project_keys({'title': title}))

    def test_earlier_reports_on_the_storyline_become_history(self):
        prior = story('ondas', 'Ondas launches long-range Dronebuster REACH C-UAS system', '无人系统', body=CUAS)
        prior['editionDate'] = '2026-10-02'
        current = story('eos', 'EOS unveils next-generation Slinger C-UAS system', '无人系统', body=CUAS)
        pool, _ = prepare_candidates([current], {}, NOW, [prior])
        history = pool[0]['_history']
        self.assertEqual([(h['newsId'], h['relation']) for h in history], [('ondas', 'same-storyline')])
        self.assertEqual(pool[0]['_deltaScore'], 0)

    def test_fallback_plan_groups_a_storyline_instead_of_one_report_per_topic(self):
        items = [story('eos', 'EOS unveils next-generation Slinger C-UAS system', '无人系统', body=CUAS),
                 story('skyfox', 'AERO Vodochody and Thales Belgium advance Skyfox C-UAS development', '无人系统',
                       source='Second Journal', body=CUAS.replace('quadcopters', 'fixed-wing drones')),
                 story('nav', 'Aster Labs navigation simulation results', body=BODY)]
        report = build_daily_deepread(items, {}, NOW)
        plan = {tuple(sorted(t['newsIds'])): t for t in report['topicPlan']}
        self.assertIn(('eos', 'skyfox'), plan)
        self.assertTrue(plan[('eos', 'skyfox')]['title'].startswith('反无人机'))
        self.assertIn(('nav',), plan)


class PlannerAndSalvage(unittest.TestCase):
    def test_one_malformed_planned_topic_does_not_discard_the_plan(self):
        base = EditorialProvider()

        def provider(runtime, **kwargs):
            if kwargs['schema_name'] == 'deepread_topics_v13':
                return {'topics': [
                    {'title': '一个引用了不存在新闻的主题', 'angle': '无效。', 'newsIds': ['missing']},
                    {'title': '自主导航仿真结果说明了什么', 'angle': '核对评估条件。', 'newsIds': ['navigation']}]}
            return base(runtime, **kwargs)

        draft = build_daily_deepread([story('navigation', 'Aster Labs navigation simulation results', body=BODY)],
                                     {}, NOW, {'provider': 'deepseek'}, provider)
        self.assertEqual(draft['topicPlan'][0]['title'], '自主导航仿真结果说明了什么')
        self.assertEqual(len(draft['chapters']), 1)

    def test_a_sentence_that_keeps_failing_is_dropped_not_the_chapter(self):
        base = EditorialProvider()
        bad = '据材料披露，该模型已经获得正式飞行认证。'

        def provider(runtime, **kwargs):
            response = base(runtime, **kwargs)
            if kwargs['schema_name'] == 'deepread_topic_write_v13':
                response = copy.deepcopy(response)
                refs = response['blocks'][0]['sentences'][0]['evidenceIds']
                response['blocks'].insert(2, {'type': 'paragraph', 'newsIds': response['blocks'][0]['newsIds'],
                                              'sentences': [{'text': bad, 'evidenceIds': refs}]})
            if kwargs['schema_name'] == 'deepread_topic_check_v13':
                data = json.loads(kwargs['input_text'])
                response = {'checks': [{'id': c['id'], 'verdict': 'unsupported' if c['text'] == bad else 'supported',
                                        'reason': ''} for c in data['claims']],
                            'editorialReview': {'verdict': 'ready', 'reason': ''}}
            return response

        draft = build_daily_deepread([story('navigation', 'Aster Labs navigation simulation results', body=BODY)],
                                     {}, NOW, {'provider': 'deepseek'}, provider)
        self.assertEqual(len(draft['chapters']), 1)
        self.assertNotIn(bad, json.dumps(draft['chapters'], ensure_ascii=False))
        detail = draft['recoveryDiagnostics']['chapters']['chapter-1']
        self.assertEqual((detail['state'], detail['droppedSentences']), ('salvaged', 1))


if __name__ == '__main__':
    unittest.main()
