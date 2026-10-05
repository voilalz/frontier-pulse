import copy
import json
import sys
import unittest
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import evidence_trace as trace
import update_news as news
from news_evidence import strip_caption_text
from deepread_editorial_signals import is_political_policy
from deepread_editorial import build_daily_deepread

class EvidenceRegressionTests(unittest.TestCase):
    def records(self): return trace.make_evidence('NASA完成无人机导航试验，飞行持续30分钟。研究团队未披露量产时间。','https://nasa.gov/a','2026-09-26T01:00:00Z')
    def test_caption_corpus_22_positive_and_negative_boundaries(self):
        rows=json.loads((ROOT/'tests/fixtures/caption_boundaries.json').read_text())['cases']
        self.assertGreaterEqual(len(rows),20)
        for row in rows:
            with self.subTest(case=row['caseId']): self.assertEqual(bool(strip_caption_text(row['text'])),row['keep'])
    def test_policy_corpus_40_subject_boundaries(self):
        rows=json.loads((ROOT/'tests/fixtures/policy_boundaries.json').read_text())['cases']
        self.assertGreaterEqual(len(rows),40)
        for row in rows:
            with self.subTest(case=row['caseId']): self.assertEqual(is_political_policy(row),row['excluded'])
    def test_source_record_is_immutable_and_has_url_time_id(self):
        records=self.records(); trace.validate_evidence(records)
        self.assertEqual(records,self.records())
        self.assertTrue(all(r['fetchedAt'] and r['url'] and r['evidenceId'] for r in records))
        bad=copy.deepcopy(records); bad[0]['text']='NASA证明无人机已经安全量产。'
        with self.assertRaises(ValueError): trace.validate_evidence(bad)
    def test_units_qualifiers_negation_and_actors_cannot_change(self):
        records=trace.make_evidence('NASA尚未完成无人机导航试验，飞行记录只有30秒。ESA协助NASA进行导航试验。','https://nasa.gov/a','2026-09-26T01:00:00Z')
        refs=[r['evidenceId'] for r in records]
        for text in ['NASA完成无人机导航试验。','飞行记录只有30分钟。','NASA协助ESA进行导航试验。']:
            self.assertFalse(trace.validate_claim_refs(text,refs,records))
    def test_missing_extraction_is_not_publisher_nondisclosure(self):
        records=self.records()
        self.assertEqual(trace.make_evidence('现有元数据未提供测试规模。','https://nasa.gov/a','2026-09-26T01:00:00Z'),[])
        self.assertFalse(trace.validate_claim_refs('NASA尚未公布测试规模。',[r['evidenceId'] for r in records],records))
    def test_summary_only_never_enters_deepread(self):
        now=datetime(2026,9,26,2,tzinfo=timezone.utc)
        item={'id':'a','eventId':'evt-a','title':'NASA公布导航试验结果','summary':'NASA完成300分钟飞行并证实已经安全量产。','publishedAt':now.isoformat(),'source':'NASA','url':'https://nasa.gov/a'}
        article=build_daily_deepread([item],{},now)
        self.assertEqual(article['eventCount'],0)
    def test_cache_retains_raw_capture_time_and_rejects_model_summary(self):
        records=self.records(); now=datetime(2026,9,26,2,tzinfo=timezone.utc)
        item={'id':'a','originalTitle':'NASA完成无人机导航试验','url':'https://nasa.gov/a','publishedAt':now.isoformat(),'source':'NASA','summary':'错误300分钟摘要','evidenceRecords':records}
        cached=news.article_from_public_item(item,now)
        self.assertEqual(cached.source_evidence,records)
        rebuilt=news.item_from_article(cached,{})
        self.assertNotIn('300',rebuilt['summary'])
        self.assertEqual([r['fetchedAt'] for r in rebuilt['evidenceRecords']],[r['fetchedAt'] for r in records])

    def test_archived_generated_summary_and_key_facts_cannot_become_raw_proof(self):
        archived=json.loads((ROOT/'tests/fixtures/real_regression_cases.json').read_text())['legacySummaryOnly']
        now=datetime(2026,9,27,12,tzinfo=timezone.utc)
        recovered=news.article_from_public_item(archived,now)
        self.assertEqual(recovered.source_evidence,[])
        item=news.item_from_article(recovered,{})
        self.assertEqual(item['summary'],'')
        self.assertEqual(item['keyFacts'],[])
        self.assertEqual(build_daily_deepread([item],{},now)['eventCount'],0)

    def test_actual_archived_referendum_is_excluded_but_government_site_ai_incident_is_retained(self):
        archive=json.loads((ROOT/'tests/fixtures/real_regression_cases.json').read_text())
        self.assertTrue(is_political_policy(archive['politicalReport']))
        self.assertFalse(is_political_policy(archive['pauseReports'][0]))

if __name__=='__main__': unittest.main()
