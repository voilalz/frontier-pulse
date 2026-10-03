"use strict";
// Real product assets, accepted corpus, publication snapshots and service worker.
const assert=require('node:assert/strict');
const fs=require('node:fs'), path=require('node:path'), os=require('node:os'), http=require('node:http');
const {execFileSync}=require('node:child_process');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'../..');
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'frontier-classics-'));
const publicRoot=execFileSync('python',[path.join(__dirname,'build_classic_fixture.py'),temp,'--news'],{cwd:root,encoding:'utf8'}).trim();
const output=process.env.FRONTIER_BROWSER_OUTPUT||path.join(os.tmpdir(),'frontier-classic-evidence');
fs.mkdirSync(output,{recursive:true});
let fault='';
const media={'.html':'text/html','.js':'application/javascript','.css':'text/css','.json':'application/json','.svg':'image/svg+xml','.png':'image/png'};
const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://localhost');
  if((fault==='news' && /^\/(data|releases)\//.test(url.pathname)) || (fault==='classic' && url.pathname.startsWith('/classics/'))){res.writeHead(503);res.end('injected failure');return;}
  const file=path.resolve(publicRoot,'.'+(url.pathname==='/'?'/index.html':decodeURIComponent(url.pathname)));
  if(!file.startsWith(publicRoot+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);res.end('missing');return;}
  res.writeHead(200,{'Content-Type':media[path.extname(file)]||'application/octet-stream'});fs.createReadStream(file).pipe(res);
});
const legacy={id:'legacy:paper',contentType:'paper',title:'Preserved legacy paper',authors:['Legacy Author'],year:2020,
  summary:'Legacy saved research summary.',source:'arXiv',url:'https://arxiv.org/abs/2001.00001',publishedAt:'2020-01-01T00:00:00Z',editionDate:'2020-01-01'};
const scenarios=['daily-history','search-favorite-citation','old-favorites','cross-day-cache','news-failure',
  'classic-refresh-failure','unpublished-date','stale-start','stale-refresh','local-favorites-news-failure',
  'malformed-favorite','quota-refresh','search-isolation','initial-news-failure'];
const results=[];let browser;
const waitCards=p=>p.waitForFunction(()=>document.querySelectorAll('#classicCards .classic-card').length===2);
const waitSeen=promise=>{let timer;return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('delayed news request was not observed')),10000);})]).finally(()=>clearTimeout(timer));};
const nav=(p,v)=>p.locator(`.view-tabs [data-view="${v}"]`).click();
async function previous(p){await p.locator('#classicPrevious').click();assert.equal(await p.locator('#classicDate').inputValue(),'2026-10-03');}
async function main(){
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base=`http://127.0.0.1:${server.address().port}`;
  browser=await chromium.launch({headless:true,...(process.env.FRONTIER_CHROME?{executablePath:process.env.FRONTIER_CHROME}:{})});
  const selected=process.env.FRONTIER_CLASSIC_SCENARIOS?.split(',')||scenarios;
  for(const device of [{name:'desktop',viewport:{width:1440,height:1000},timezoneId:'America/Los_Angeles'},
    {name:'mobile',viewport:{width:390,height:844},timezoneId:'Asia/Tokyo',isMobile:true,hasTouch:true}]){
    for(const scenario of selected){
      fault='';const context=await browser.newContext({...device,serviceWorkers:scenario==='cross-day-cache'?'allow':'block'});await context.grantPermissions(['clipboard-read','clipboard-write'],{origin:base});
      await context.route(/^https:\/\//,r=>r.abort());
      const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
      await page.clock.install({time:new Date('2026-10-04T00:10:00Z')});
      if(['old-favorites','local-favorites-news-failure','malformed-favorite'].includes(scenario)){
        await context.addInitScript(({legacy,malformed})=>{
          localStorage.setItem('fp-bookmarks-v2',JSON.stringify([legacy]));
          if(malformed)localStorage.setItem('fp-classic-bookmarks-v1',JSON.stringify([{date:'2026-10-04',paper:{id:'bad',authors:null,sourceLocators:[null]}}]));
        },{legacy,malformed:scenario==='malformed-favorite'});
      }
      if(scenario==='quota-refresh')await context.addInitScript(()=>{
        const original=Storage.prototype.setItem;
        Storage.prototype.setItem=function(k,v){if(k==='fp-classic-snapshot-v1')throw new DOMException('quota','QuotaExceededError');return original.call(this,k,v);};
      });
      try{
        if(['news-failure','local-favorites-news-failure','initial-news-failure'].includes(scenario))fault='news';
        if(scenario==='stale-start'){
          let release,started;const gate=new Promise(r=>release=r),seen=new Promise(r=>started=r);
          await page.route('**/data/status.json*',async route=>{started();await gate;await route.continue();});
          await page.goto(base,{waitUntil:'domcontentloaded'});await waitSeen(seen);
          await nav(page,'research');await waitCards(page);await previous(page);release();
          await page.waitForLoadState('networkidle');
          assert.equal(await page.locator('#dataState').textContent(),'历史推荐');
          assert.equal(await page.locator('#classicDate').inputValue(),'2026-10-03');
        }else if(scenario==='stale-refresh'){
          await page.goto(base,{waitUntil:'networkidle'});
          await page.waitForFunction(()=>document.querySelectorAll('#stories .story').length===10);
          let release,started;const gate=new Promise(r=>release=r),seen=new Promise(r=>started=r);
          await page.route('**/data/release.json*',async route=>{started();await gate;await route.continue();});
          await page.locator('#reloadBtn').click();await waitSeen(seen);
          await nav(page,'research');await waitCards(page);await previous(page);release();
          await page.waitForFunction(()=>!document.querySelector('#reloadBtn').disabled);
          assert.equal(await page.locator('#dataState').textContent(),'历史推荐');
          assert.equal(await page.locator('#classicDate').inputValue(),'2026-10-03');
          assert.match(page.url(),/view=research/);
        }else if(scenario==='initial-news-failure'){
          await page.goto(base,{waitUntil:'networkidle'});
          assert.equal(await page.locator('#systemAlert').isVisible(),true);
          assert.match(await page.locator('#alertTitle').textContent(),/初始化失败/);
          await nav(page,'research');await waitCards(page);
          assert.equal(await page.locator('#systemAlert').isVisible(),false);
        }else{
          const query=scenario==='search-isolation'?'?view=research&classic=history&q=Lowe&domain=CV':
            scenario==='local-favorites-news-failure'?'?view=bookmarks':'?view=research';
          await page.goto(base+query,{waitUntil:'networkidle'});
          if(scenario==='local-favorites-news-failure'){
            await page.locator('#stories .paper-card').waitFor();
            assert.match(await page.locator('#stories').textContent(),/Preserved legacy paper/);
            assert.equal(await page.locator('#dataState').textContent(),'本机收藏');
          }else if(scenario==='search-isolation'){
            assert.equal(await page.locator('#classicCards .classic-card').count(),1);
            await nav(page,'latest');await page.waitForFunction(()=>document.querySelectorAll('#stories .story').length===10);
            assert.equal(await page.locator('#search').inputValue(),'');
          }else{
            await waitCards(page);
            if(scenario==='daily-history'){
              assert.equal(await page.locator('#classicDate').inputValue(),'2026-10-04');
              assert.equal(await page.locator('#searchWrap').isVisible(),false);
              assert.equal(await page.locator('#dateControl').isVisible(),false);
              assert.equal(await page.locator('#classicCards .classic-card a').first().getAttribute('href').then(x=>x.startsWith('https://')),true);
              await page.locator('#classicCards details summary').first().click();
              assert.equal(await page.locator('#classicCards .classic-card').first().locator('.classic-guide section').count(),6);
              await previous(page);await page.locator('#classicNext').click();
              await page.locator('[data-classic-mode="history"]').click();
              assert.equal(await page.locator('#classicCards .classic-card').count(),4);
              assert.equal(await page.locator('#classicHistoryControls').isVisible(),true);
              await page.screenshot({path:path.join(output,device.name+'-classics.png'),fullPage:true});
            }else if(scenario==='search-favorite-citation'){
              const paper=await page.evaluate(()=>JSON.parse(localStorage.getItem('fp-classic-snapshot-v1')).payloads['edition.json']);
              const item=JSON.parse(paper).items[0];
              await page.locator('#classicCards [data-classic-cite]').first().click();
              const citation=await page.evaluate(()=>navigator.clipboard.readText());
              for(const text of [...item.authors,item.title,item.venue,String(item.year),item.canonicalUrl])assert.ok(citation.includes(text));
              await page.locator('#classicCards [data-classic-save]').first().click();
              await page.locator('[data-classic-mode="history"]').click();await page.locator('#classicSearch').fill('Lowe');
              assert.equal(await page.locator('#classicCards .classic-card').count(),1);
              await nav(page,'bookmarks');assert.equal(await page.locator('#classicBookmarks .classic-card').count(),1);
            }else if(['old-favorites','malformed-favorite'].includes(scenario)){
              await page.locator('#classicCards [data-classic-save]').first().click();await nav(page,'bookmarks');
              await page.locator('#stories .paper-card').waitFor();
              assert.match(await page.locator('#stories').textContent(),/旧版论文/);
              assert.equal(await page.locator('#classicBookmarks .classic-card').count(),1);
              assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('fp-bookmarks-v2'))[0].id),'legacy:paper');
            }else if(scenario==='cross-day-cache'){
              await page.evaluate(()=>navigator.serviceWorker.ready);
              await page.waitForFunction(()=>Boolean(navigator.serviceWorker.controller));
              await page.reload({waitUntil:'networkidle'});await waitCards(page);
              await page.clock.setFixedTime(new Date('2026-10-05T00:10:00Z'));await context.setOffline(true);
              await page.reload({waitUntil:'networkidle'});await waitCards(page);
              assert.equal(await page.locator('#dataState').textContent(),'今日待更新');
              assert.equal(await page.locator('#classicDate').inputValue(),'2026-10-04');
            }else if(scenario==='news-failure'){
              await nav(page,'latest');assert.equal(await page.locator('#classicCards .classic-card').count(),2);
              assert.match(page.url(),/view=research/);
            }else if(['classic-refresh-failure','quota-refresh'].includes(scenario)){
              const before=await page.locator('#classicCards h3').allTextContents();
              if(scenario==='quota-refresh')assert.equal(await page.evaluate(()=>localStorage.getItem('fp-classic-snapshot-v1')),null);
              fault='classic';await page.locator('#reloadBtn').click();await page.waitForFunction(()=>!document.querySelector('#reloadBtn').disabled);
              assert.deepEqual(await page.locator('#classicCards h3').allTextContents(),before);
              assert.match(await page.locator('#classicNotice').textContent(),/缓存/);
            }else if(scenario==='unpublished-date'){
              await page.locator('#classicDate').fill('2026-10-02');await page.locator('#classicDate').dispatchEvent('change');
              assert.equal(await page.locator('#classicCards .classic-card').count(),0);
              assert.match(await page.locator('#classicCards').textContent(),/尚无已发布/);
              assert.equal(await page.locator('#classicDate').getAttribute('max'),'2026-10-04');
            }
          }
        }
        assert.deepEqual(errors,[]);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'document overflows viewport');
        results.push({device:device.name,scenario,status:'passed'});console.log(`PASS ${device.name}: ${scenario}`);
      }catch(error){
        results.push({device:device.name,scenario,status:'failed',error:error.message});
        console.error(`FAIL ${device.name}: ${scenario}: ${error.message}`);
        await page.screenshot({path:path.join(output,device.name+'-'+scenario+'-failed.png'),fullPage:true});
      }finally{await context.close();}
    }
  }
  fs.writeFileSync(path.join(output,'classic-results.json'),JSON.stringify({cases:results,passed:results.filter(r=>r.status==='passed').length,total:results.length},null,2));
  if(results.some(r=>r.status!=='passed'))process.exitCode=1;
}
main().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{
  if(browser)await browser.close();await new Promise(r=>server.close(r));fs.rmSync(temp,{recursive:true,force:true});
});
