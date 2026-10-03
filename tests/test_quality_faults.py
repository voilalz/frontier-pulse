import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'tests/browser'))
import build_fixture
import publication as pub
import update_news as news
from deepread_editorial import build_daily_deepread
from evidence_trace import validate_deepread_trace

class QualityFaultTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.public=build_fixture.build(self.root)
        self.stage=self.root/'stage'
    def state(self):return {str(p.relative_to(self.public)):p.read_bytes() for p in self.public.rglob('*') if p.is_file() and 'releases' not in p.relative_to(self.public).parts}

    def test_collection_failure_cannot_promote_or_replace_last_readable_release(self):
        before=self.state();pub.prepare_stage(self.public,self.stage)
        now=datetime(2026,9,30,0,10,tzinfo=timezone.utc)
        args=build_fixture.command(self.stage,self.root/'authored-2026-09-30.json',now)
        with patch.object(sys,'argv',args[1:]),patch.object(news,'collect_fixture',side_effect=RuntimeError('injected collection failure')):
            self.assertEqual(news.main(),2)
        with self.assertRaises(ValueError):pub.promote(self.stage,self.public,'daily','r-collection-fault','fixture')
        self.assertEqual(self.state(),before)
        pub.record_failure(self.public,'daily','collection failed')
        after=self.state();self.assertEqual([key for key in before if before[key]!=after[key]],['data/status.json'])
        self.assertEqual(json.loads(after['data/status.json'])['state'],'failed')

    def test_model_outage_retains_grounded_readable_article_with_degraded_status(self):
        news_items=json.loads((self.public/'data/news.json').read_text())['items']
        def outage(*args,**kwargs):raise RuntimeError('injected model outage')
        article=build_daily_deepread(news_items,{},datetime(2026,9,30,0,10,tzinfo=timezone.utc),{'provider':'fixture'},outage)
        validate_deepread_trace(article)
        self.assertGreaterEqual(article['eventCount'],4)
        self.assertEqual(article['generationStatus'],'fallback')
        self.assertTrue(article['warnings'])
        pub.prepare_stage(self.public,self.stage)
        for name in ['deepread.json','deepread/2026-09-30.json']:
            pub.write_json_atomic(self.stage/'data'/name,article)
        pub.promote(self.stage,self.public,'daily','r-model-degraded','fixture')
        self.assertEqual(json.loads((self.public/'data/deepread.json').read_text())['generationStatus'],'fallback')
        pub.verify_snapshot(self.public/'releases/r-model-degraded')

    def test_install_failure_rolls_back_files_and_preserves_snapshot(self):
        before=self.state();pub.prepare_stage(self.public,self.stage)
        original=pub.install_file;count=0
        def failure(source,target):
            nonlocal count
            count+=1
            if count==3:raise OSError('injected disk failure')
            return original(source,target)
        with patch.object(pub,'install_file',side_effect=failure):
            with self.assertRaises(OSError):pub.promote(self.stage,self.public,'daily','r-install-fault','fixture')
        self.assertEqual(self.state(),before)
        pub.verify_snapshot(self.public/'releases/r-current')
        pub.record_failure(self.public,'daily','publication failed')
        self.assertEqual(json.loads((self.public/'data/status.json').read_text())['state'],'failed')

if __name__=='__main__':unittest.main()
