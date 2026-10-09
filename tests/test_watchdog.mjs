import assert from 'node:assert/strict';
import test from 'node:test';
let monitor, handler;
try { const m = await import('../ops/watchdog/worker.mjs'); monitor = m.monitor; handler = m.default; } catch {}
class MemoryStorage {
  data = new Map(); queue = Promise.resolve();
  async get(key) {return structuredClone(this.data.get(key));}
  async put(key, value) {this.data.set(key, structuredClone(value));}
  async delete(keys) {for (const key of Array.isArray(keys) ? keys : [keys]) this.data.delete(key);}
  async list({prefix=''}) {return new Map([...this.data].filter(([k])=>k.startsWith(prefix)).sort());}
  transaction(fn) {const job = this.queue.then(()=>fn(this)); this.queue = job.catch(()=>{}); return job;}
}
const env = {ENABLED:'true', SITE_URL:'https://newsfrontier.top/', GITHUB_REPO:'voilalz/frontier-pulse', GITHUB_TOKEN:'test', ALERT_WEBHOOK_URL:'https://alerts.example.test/hook'};
function source({fresh=false, repoFresh=false, active=false, brokenDispatch=false, mismatched=false, dispatchStatus=204, dispatchBody=null}={}) {
  const calls=[];
  const manifest={schemaVersion:1, releaseId:'r-test', basePath:'./releases/r-test/', editionDate:fresh?'2026-09-28':'2026-09-27'};
  const fetcher=async(url, options={})=>{
    url=String(url); calls.push({url, ...options});
    const response=(data, status=200)=>new Response(JSON.stringify(data),{status});
    if (url.includes('/dispatches')) {
      assert.equal(options.method,'POST');
      assert.deepEqual(JSON.parse(options.body),{ref:'main',inputs:{force_refresh:'false'},return_run_details:true});
      if (brokenDispatch) throw new Error('ambiguous connection loss');
      if (dispatchStatus === 204) return new Response(null,{status:204});
      return new Response(typeof dispatchBody === 'string' ? dispatchBody : JSON.stringify(dispatchBody),{status:dispatchStatus});
    }
    if (url === env.ALERT_WEBHOOK_URL) return new Response(null,{status:204});
    if (url.includes('/runs?')) return response({workflow_runs: active ? [{status:'in_progress'}] : []});
    if (url.includes('/contents/')) return response(repoFresh ? {...manifest, editionDate:'2026-09-28'} : manifest);
    if (url.endsWith('/data/release.json')) return response(manifest);
    if (url.endsWith('/data/news.json')) return response({releaseId:mismatched?'wrong':'r-test', editionDate:manifest.editionDate, items:Array.from({length:10},(_,i)=>({id:String(i)}))});
    if (url.endsWith('/data/deepread.json')) return response({releaseId:'r-test', editionDate:manifest.editionDate, generationStatus:'ok', eventCount:5, events:Array.from({length:5},(_,i)=>({newsId:String(i)}))});
    throw new Error('Unexpected request '+url);
  };
  return {fetcher, calls};
}
const at=(time)=>new Date('2026-09-28T'+time+'Z');
const dispatches=x=>x.calls.filter(c=>c.url.includes('/dispatches')).length;
test('healthy edition does not dispatch and records deadline observation',async()=>{
  assert.ok(monitor); const s=new MemoryStorage(),x=source({fresh:true});
  const result=await monitor(env,s,x.fetcher,at('00:00:00'));
  assert.equal(result.status,'healthy'); assert.equal(dispatches(x),0);
  assert.equal((await s.get('day:2026-09-28')).onTime,true);
});
test('before 0740 the monitor only waits',async()=>{
  assert.ok(monitor); const s=new MemoryStorage(),x=source();
  const result=await monitor(env,s,x.fetcher,new Date('2026-09-27T23:35:00Z'));
  assert.equal(result.status,'waiting'); assert.equal(dispatches(x),0);
  assert.equal(x.calls.filter(c=>c.url===env.ALERT_WEBHOOK_URL).length,0);
});
test('0741 dispatches the daily edition without alerting, then sees it running',async()=>{
  assert.ok(monitor); const s=new MemoryStorage(),x=source();
  const result=await monitor(env,s,x.fetcher,new Date('2026-09-27T23:41:00Z'));
  assert.equal(result.status,'recovery-requested'); assert.equal(dispatches(x),1);
  assert.equal(x.calls.filter(c=>c.url===env.ALERT_WEBHOOK_URL).length,0);
  const later=source({active:true});
  assert.equal((await monitor(env,s,later.fetcher,new Date('2026-09-27T23:50:00Z'))).status,'running');
  assert.equal(dispatches(later),0);
});
test('a failed 0741 run is retried once at 0815 and alerted at 0805',async()=>{
  assert.ok(monitor); const s=new MemoryStorage(),x=source();
  for(const time of ['2026-09-27T23:41:00Z','2026-09-27T23:50:00Z','2026-09-28T00:05:00Z','2026-09-28T00:15:00Z','2026-09-28T00:35:00Z'])
    await monitor(env,s,x.fetcher,new Date(time));
  assert.equal(dispatches(x),2);
  assert.equal(x.calls.filter(c=>c.url===env.ALERT_WEBHOOK_URL).length,1);
});
test('0805 old edition alerts and dispatches once, cooldown and daily cap are durable',async()=>{
  assert.ok(monitor); const s=new MemoryStorage(),x=source();
  for(const time of ['00:05:00','00:06:00','00:35:00','01:05:00']) await monitor(env,s,x.fetcher,at(time));
  assert.equal(dispatches(x),2); assert.equal((await s.get('day:2026-09-28')).attempts,2);
  assert.equal(x.calls.filter(c=>c.url===env.ALERT_WEBHOOK_URL).length,1);
});
test('concurrent checks reserve only one recovery',async()=>{
  assert.ok(monitor); const s=new MemoryStorage(),x=source();
  await Promise.all(Array.from({length:4},()=>monitor(env,s,x.fetcher,at('00:05:00'))));
  assert.equal(dispatches(x),1);
});
test('active workflow and deployment lag never cause another generation',async()=>{
  assert.ok(monitor);
  for(const options of [{active:true},{repoFresh:true}]) {
    const s=new MemoryStorage(),x=source(options); const r=await monitor(env,s,x.fetcher,at('00:05:00'));
    assert.equal(dispatches(x),0); assert.equal(r.status, options.active?'running':'deployment-lag');
  }
});
test('ambiguous dispatch failure consumes reserved attempt rather than duplicating request',async()=>{
  assert.ok(monitor); const s=new MemoryStorage(),x=source({brokenDispatch:true});
  for(const time of ['00:05:00','00:06:00','00:35:00','01:05:00']) await monitor(env,s,x.fetcher,at(time));
  assert.equal(dispatches(x),2); assert.equal((await s.get('day:2026-09-28')).attempts,2);
});
test('new date gets its own quota and retained daily reports cover fourteen days',async()=>{
  assert.ok(monitor); const s=new MemoryStorage(),x=source();
  for(let d=1;d<=27;d++) await s.put(`day:2026-09-${String(d).padStart(2,'0')}`,{attempts:2});
  await monitor(env,s,x.fetcher,at('00:05:00'));
  assert.equal(dispatches(x),1); assert.equal((await s.list({prefix:'day:'})).size,14);
  assert.equal(await s.get('day:2026-09-14'),undefined);
});
test('a mismatched payload is not a healthy release',async()=>{
  assert.ok(monitor);const s=new MemoryStorage(),x=source({fresh:true,mismatched:true,repoFresh:true});
  const result=await monitor(env,s,x.fetcher,at('00:05:00'));
  assert.equal(result.status,'deployment-lag');
});
test('disabled monitor has no requests and public requests cannot trigger checks',async()=>{
  assert.ok(monitor); let requests=0;
  const result=await monitor({...env,ENABLED:'false'},new MemoryStorage(),async()=>{requests++;},at('00:05:00'));
  assert.equal(result.status,'disabled'); assert.equal(requests,0);
  assert.equal((await handler.fetch(new Request('https://watchdog.example/check'),env)).status,404);
});
test('production checks go through the SITE service binding when present',async()=>{
  assert.ok(monitor); const x=source({fresh:true}), site=[];
  const bound={...env, SITE:{fetch:async(url,options)=>{site.push(String(url)); return x.fetcher(url,options);}}};
  const guarded=async(url,options)=>{
    if (String(url).startsWith(env.SITE_URL)) throw new Error('public production fetch');
    return x.fetcher(url,options);
  };
  const result=await monitor(bound,new MemoryStorage(),guarded,at('00:00:00'));
  assert.equal(result.status,'healthy'); assert.equal(site.length,3);
});
test('a 200 dispatch with run details succeeds and records the run ID',async()=>{
  assert.ok(monitor); const s=new MemoryStorage();
  const x=source({dispatchStatus:200, dispatchBody:{workflow_run_id:37868180309, run_url:'https://api.github.com/x', html_url:'https://github.com/x'}});
  const result=await monitor(env,s,x.fetcher,at('00:05:00'));
  assert.equal(result.status,'recovery-requested'); assert.equal(result.runId,37868180309);
  const state=await s.get('day:2026-09-28');
  assert.deepEqual(state.runIds,[37868180309]); assert.equal(state.checks.at(-1).runId,37868180309);
  assert.equal(state.attempts,1);
});
test('a 204 dispatch still succeeds without a run ID',async()=>{
  assert.ok(monitor); const s=new MemoryStorage(),x=source();
  const result=await monitor(env,s,x.fetcher,at('00:05:00'));
  assert.equal(result.status,'recovery-requested'); assert.equal(result.runId,undefined);
  assert.equal((await s.get('day:2026-09-28')).runIds,undefined);
});
test('a 200 dispatch with unreadable details is still accepted once',async()=>{
  assert.ok(monitor);
  for (const dispatchBody of ['not json', {workflow_run_id:'37868180309'}, {}]) {
    const s=new MemoryStorage(),x=source({dispatchStatus:200, dispatchBody});
    const result=await monitor(env,s,x.fetcher,at('00:05:00'));
    assert.equal(result.status,'recovery-requested'); assert.equal(result.runId,undefined);
    assert.equal(dispatches(x),1); assert.equal((await s.get('day:2026-09-28')).attempts,1);
  }
});
test('other dispatch responses are failures that keep the attempt and cooldown',async()=>{
  assert.ok(monitor);
  for (const dispatchStatus of [201, 403, 422]) {
    const s=new MemoryStorage(),x=source({dispatchStatus, dispatchBody:{message:'no'}});
    const first=await monitor(env,s,x.fetcher,at('00:05:00'));
    assert.equal(first.status,'dispatch-uncertain'); assert.equal(first.reason,'upstream-error');
    assert.equal((await monitor(env,s,x.fetcher,at('00:15:00'))).status,'recovery-limited');
    assert.equal(dispatches(x),1); assert.equal((await s.get('day:2026-09-28')).attempts,1);
  }
});
