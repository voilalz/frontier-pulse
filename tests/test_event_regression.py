import copy
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import event_identity as identity
import update_news as news

class EventRegressionTests(unittest.TestCase):
    def test_frozen_100_pair_acceptance(self):
        pairs=json.loads((ROOT/'tests/fixtures/event_pairs.json').read_text())['pairs']
        self.assertEqual(sum(p['sameEvent'] for p in pairs),50)
        self.assertEqual(sum(not p['sameEvent'] for p in pairs),50)
        missed=[]; merged=[]
        for p in pairs:
            actual=identity.same_event(p['first'],p['second'])
            if p['sameEvent'] and not actual: missed.append(p['caseId'])
            if not p['sameEvent'] and actual: merged.append(p['caseId'])
        self.assertEqual(merged,[])
        self.assertGreaterEqual(50-len(missed),45,missed)

    def test_real_pause_reports_merge_before_selection(self):
        rows=json.loads((ROOT/'tests/fixtures/real_regression_cases.json').read_text())['pauseReports']
        self.assertGreaterEqual(len(rows),2)
        articles=[news.Article(r['id'],r['originalTitle'],'',r['url'],r['source'],'fixture.source','国际',datetime(2026,9,27,1,tzinfo=timezone.utc)) for r in rows]
        merged=news.deduplicate(articles)
        self.assertEqual(len(merged),1)
        self.assertGreaterEqual(len(merged[0].evidence_sources),2)

    def test_stage_timeline_reuses_identity_without_duplicate_collapse(self):
        plan={'id':'plan','originalTitle':'NASA plans to launch Artemis 3 on September 26','url':'https://nasa.gov/plan','publishedAt':'2026-09-25T01:00:00Z'}
        done={**plan,'id':'done','originalTitle':'NASA launched Artemis 3 on September 26','url':'https://nasa.gov/done','publishedAt':'2026-09-26T01:00:00Z'}
        self.assertFalse(identity.same_event(plan,done))
        identity.assign_event_ids([plan],{}, {})
        registry={'items':[{'eventId':plan['eventId'],'newsIds':['plan'],'identityRepresentatives':[identity.event_identity_record(plan)]}]}
        identity.assign_event_ids([done],registry,{})
        self.assertEqual(done['eventId'],plan['eventId'])

    def test_live_link_cannot_reuse_changed_registry_payload(self):
        a={'id':'a','originalTitle':'SpaceX launches Starlink 9-28','url':'https://fixture.invalid/live','publishedAt':'2026-09-26T01:00:00Z'}
        identity.assign_event_ids([a],{}, {})
        b={**a,'id':'b','originalTitle':'SpaceX cancels Starlink 9-29'}
        registry={'items':[{'eventId':a['eventId'],'newsIds':['a'],'identityRepresentatives':[identity.event_identity_record(a)]}]}
        identity.assign_event_ids([b],registry,{})
        self.assertNotEqual(a['eventId'],b['eventId'])

if __name__=='__main__': unittest.main()
