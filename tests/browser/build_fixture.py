"""Build authored, isolated two-edition releases through the actual pipeline."""
import json
import shutil
import subprocess
import sys
from datetime import datetime,timedelta,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'tests'))
import publication as pub
from batch1_fixtures import localize_stage

def command(stage,fixture,now):
    data=stage/'data'
    args=[sys.executable,str(ROOT/'scripts/update_news.py'),'--fixture',str(fixture),
          '--research-fixture',str(ROOT/'tests/fixtures/papers.json'),'--skip-ai','--now',now.isoformat()]
    paths={'output':'news.json','status-output':'status.json','stream-output':'stream.json',
           'stream-status-output':'stream-status.json','research-output':'research.json','events-output':'events.json',
           'weekly-output':'weekly.json','weekly-dir':'weekly','signals-output':'signals.json','archive-dir':'archive',
           'archive-index':'archive/index.json','search-index':'archive/search-index.json','deepread-output':'deepread.json'}
    for key,value in paths.items():args += ['--'+key,str(data/value)]
    return args+['--feed-output',str(stage/'feed.xml')]

def build(directory):
    directory=Path(directory);public=directory/'public';stage=directory/'stage'
    public.mkdir(parents=True,exist_ok=True)
    for path in (ROOT/'public').iterdir():
        if path.name in {'data','releases','feed.xml'}:continue
        if path.is_dir():shutil.copytree(path,public/path.name,dirs_exist_ok=True)
        else:shutil.copy2(path,public/path.name)
    base=json.loads((ROOT/'tests/fixtures/articles.json').read_text())
    for day,release in [('2026-09-29','r-previous'),('2026-09-30','r-current')]:
        now=datetime.fromisoformat(day+'T00:10:00+00:00')
        rows=[]
        for index,original in enumerate(base):
            row={**original,'id':day+'-'+original['id'],'url':original['url']+'?edition='+day,
                 'publishedAt':(now-timedelta(hours=1+index/2)).isoformat(),
                 # Authored full-source lead, with the original test wording.
                 'description':original['title']+'. '+original['description']}
            rows.append(row)
        fixture=directory/('authored-'+day+'.json')
        fixture.write_text(json.dumps(rows))
        pub.prepare_stage(public,stage)
        result=subprocess.run(command(stage,fixture,now),cwd=ROOT,capture_output=True,text=True)
        if result.returncode:raise AssertionError(result.stderr[-2000:])
        article=localize_stage(stage)
        if article['eventCount']<4:raise AssertionError('authored fixture lacks four grounded deepread events')
        pub.promote(stage,public,'daily',release,'offline-browser-fixture')
    return public

if __name__=='__main__':print(build(sys.argv[1]))
