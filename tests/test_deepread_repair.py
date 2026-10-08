"""Production rollout regressions: difficulty idioms and useful writer repairs."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))

from deepread_editorial import build_daily_deepread
from deepread_quality import choose_readable_deepread, validate_readable
from deepread_topic_quality import rule_issue
from evidence_trace import make_evidence
from test_deepread_topics import EditorialProvider, ANALYSIS, BODY, NOW, story


class WriterRepairTests(unittest.TestCase):
    def check_fact(self, text, source):
        rows = make_evidence(source, 'https://example.org/research', NOW.isoformat())
        records = {row['evidenceId']: row for row in rows}
        return rule_issue(text, 'fact', list(records), records)

    def test_proved_no_easy_feat_is_difficulty_not_failed_validation(self):
        source = ('Getting such clocks to work, however, proved no easy feat, '
                  'because driving these narrow nuclear transitions requires '
                  'highly stable lasers with extremely small bandwidths.')
        for text in (
            '实现这样的核时钟并非易事，窄带核跃迁需要高度稳定且带宽极窄的激光。',
            '实现这样的核时钟很困难，窄带核跃迁需要高度稳定且带宽极窄的激光。',
        ):
            with self.subTest(text=text):
                self.assertEqual(self.check_fact(text, source), '')

    def test_genuine_negative_validation_and_deployment_stay_protected(self):
        source = 'The sensor was not proven to work and has never been deployed.'
        self.assertEqual(self.check_fact('该传感器已经被验证有效，并已完成部署。', source),
                         'negated-action')
        source = 'The experiment proved no easy feat, and the device has never been deployed.'
        self.assertEqual(self.check_fact('这项实验很困难，设备已完成部署。', source),
                         'negated-action')

    def test_local_failure_gets_specific_feedback_then_independent_review(self):
        base = EditorialProvider()
        writes, reviews, feedback = [], [], []

        def provider(runtime, **kwargs):
            data = json.loads(kwargs['input_text'])
            response = base(runtime, **kwargs)
            if kwargs['schema_name'] == 'deepread_topic_write_v13':
                writes.append(data)
                feedback.extend(data['validationFeedback'])
                repaired = any('引语' in entry.get('repairInstruction', '')
                               and 'text' in entry and entry.get('evidenceRecords')
                               for entry in data['validationFeedback'])
                if not repaired:
                    response = copy.deepcopy(response)
                    response['blocks'][2]['sentences'][0]['text'] = (
                        ANALYSIS + '公司负责人称“这是我们迄今最成熟的导航模型，可以直接投入使用”。')
            elif kwargs['schema_name'] == 'deepread_topic_check_v13':
                reviews.append(data)
            return response

        draft = build_daily_deepread(
            [story('navigation', 'Aster Labs navigation simulation results', body=BODY)],
            {}, NOW, {'provider': 'deepseek'}, provider)
        self.assertEqual(len(draft['chapters']), 1)
        self.assertEqual(len(writes), 2)
        self.assertEqual(len(reviews), 1)
        self.assertTrue(any(entry.get('rule') == 'analysis-new-quotation' for entry in feedback))
        self.assertNotIn('repairInstruction', json.dumps(draft))
        reader = choose_readable_deepread(draft, [], '2026-10-08')
        validate_readable(reader, '2026-10-08')


if __name__ == '__main__':
    unittest.main()
