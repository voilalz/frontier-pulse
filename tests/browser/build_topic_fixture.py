"""Authored source/model fixtures promoted through the real publication boundary."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from build_fixture import build, ROOT
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'tests'))
import publication as pub
from test_deepread_topics import story, BODY, FACTS, EditorialProvider
from deepread_editorial import build_daily_deepread
from deepread_quality import choose_readable_deepread, deepread_status
from update_news import archive_deepread


def build_topics(directory, state):
    public=build(directory)
    stage=Path(directory)/'topic-stage'
    pub.prepare_stage(public,stage)
    now=datetime(2026,9,30,0,10,tzinfo=timezone.utc)
    inputs=[story('navigation','Aster Labs navigation simulation results',body=BODY),
            story('sensor','Optical sensing benchmark protocol','前沿技术',body=BODY)]
    for item in inputs:
        item['publishedAt']='2026-09-29T23:00:00Z'
        item['image']='https://example.org/offline-illustration.svg'
        item['displayTranslation']={'version':1,'language':'zh-CN','provider':'deepseek',
            'title':'自主导航仿真评估结果','summary':FACTS[0],
            'sourceTitle':item['originalTitle'],'sourceSummary':item['summary'],
            'sourceEvidenceRefs':item['summaryEvidenceRefs']}
    registry=pub.read_json(stage/'data/events.json')
    registry['items'] += [{'eventId':i['eventId'],'newsIds':[i['id']]} for i in inputs]
    registry['eventCount']=len(registry['items'])
    pub.write_json_atomic(stage/'data/events.json',registry)
    provider=EditorialProvider(fail='sensor' if state=='partial' else None,checker_down=state=='brief')
    draft=build_daily_deepread(inputs,{},now,{'provider':'deepseek'},provider)
    reader=choose_readable_deepread(draft,[],'2026-09-30')
    pub.write_json_atomic(stage/'data/deepread.json',reader)
    archive_deepread(reader,stage/'data/deepread',{})
    status=pub.read_json(stage/'data/status.json')
    status['deepread']=deepread_status(reader,'2026-09-30')
    pub.write_json_atomic(stage/'data/status.json',status)
    pub.promote(stage,public,'daily','r-topic-'+state,'authored-topic-browser-fixture',
        revision_reason='离线浏览器验收主题深读',base_release_id='r-current',now=now)
    return public


if __name__=='__main__':
    print(build_topics(sys.argv[1],sys.argv[2]))
