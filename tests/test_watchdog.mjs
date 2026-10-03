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
function source({fresh=false, repoFresh=false, active=false, brokenDispatch=false, mismatched=false}={}) {
  const calls=[];
  const manifest={schemaVersion:1, releaseId:'r-test', basePath:'./releases/r-test/', editionDate:fresh?'2026-09-28':'2026-09-27'};
  const fetcher=async(url, options={})=>{
    url=String(url); calls.push({url, ...options});
    const response=(data, status=200)=>new Response(JSON.stringify(data),{status});
    if (url.includes('/dispatches')) {
      assert.equal(options.method,'POST'); assert.deepEqual(JSON.parse(options.body),{ref:'main',inputs:{force_refresh:'false'}});
      if (brokenDispatch) throw new Error('ambiguous connection loss');
      return new Response(null,{status:204});
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
test('0750 check observes missing edition without dispatch or alert',async()=>{
  assert.ok(monitor); const s=new MemoryStorage(),x=source();
  const result=await monitor(env,s,x.fetcher,new Date('2026-09-27T23:50:00Z'));
  assert.equal(result.status,'waiting'); assert.equal(dispatches(x),0);
  assert.equal(x.calls.filter(c=>c.url===env.ALERT_WEBHOOK_URL).length,0);
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
