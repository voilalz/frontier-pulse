/* Independent publication watchdog. Delivered disabled; deployment is explicit. */
const ACTIVE = new Set(['queued', 'in_progress', 'waiting', 'requested', 'pending']);
export function chinaClock(now) {
  const shifted = new Date(now.valueOf() + 8 * 3600000);
  return {date:shifted.toISOString().slice(0,10), minutes:shifted.getUTCHours()*60+shifted.getUTCMinutes()};
}
function validManifest(value) {
  return value?.schemaVersion === 1 && /^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(value.releaseId)
    && /^\d{4}-\d{2}-\d{2}$/.test(value.editionDate) && value.basePath === `./releases/${value.releaseId}/`;
}
async function request(fetcher, url, options = {}) {
  return fetcher(url, {redirect:'error', signal:AbortSignal.timeout(8000), ...options});
}
async function json(fetcher, url, options) {
  const response = await request(fetcher, url, options);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}
function configuration(env) {
  const site = new URL(env.SITE_URL || 'https://newsfrontier.top/');
  if (site.protocol !== 'https:' || site.username || site.password || site.search || site.hash) throw new Error('Invalid production URL');
  if (!/^[\w.-]+\/[\w.-]+$/.test(env.GITHUB_REPO || '')) throw new Error('Invalid repository');
  return {site, api:`https://api.github.com/repos/${env.GITHUB_REPO}`,
    headers:{Authorization:`Bearer ${env.GITHUB_TOKEN}`, Accept:'application/vnd.github+json',
      'X-GitHub-Api-Version':'2026-03-10', 'User-Agent':'FrontierPublicationWatchdog'}};
}
export async function inspectProduction(env, fetcher, now) {
  const {site} = configuration(env);
  const manifest = await json(fetcher, new URL('data/release.json',site), {cache:'no-store'});
  if (!validManifest(manifest)) return {healthy:false, reason:'invalid-manifest'};
  if (manifest.editionDate !== chinaClock(now).date) return {healthy:false, reason:'old-edition', releaseId:manifest.releaseId};
  const base = new URL(manifest.basePath, site);
  const [news, deep] = await Promise.all(['news','deepread'].map(name=>
    json(fetcher,new URL(`data/${name}.json`,base),{cache:'no-store'})));
  const same = value=>value.releaseId===manifest.releaseId && value.editionDate===manifest.editionDate;
  const healthy = same(news) && same(deep) && news.items?.length===10
    && Array.isArray(deep.events) && deep.events.length>0 && deep.eventCount===deep.events.length;
  return {healthy, reason:healthy?'complete':'inconsistent-content', releaseId:manifest.releaseId};
}

export async function monitor(env, storage, fetcher = fetch, now = new Date()) {
  if (env.ENABLED !== 'true') return {status:'disabled'};
  const {date, minutes} = chinaClock(now), key = `day:${date}`, stamp = now.valueOf();
  // No external requests inside a transaction. A short lease protects the entire check;
  // persistent reservations protect retry/alert side effects across process restarts.
  const claimed = await storage.transaction(async txn=>{
    const state = await txn.get(key) || {date,attempts:0,checks:[]};
    if ((state.checkingUntil || 0) > stamp) return false;
    state.checkingUntil = stamp + 120000;
    await txn.put(key,state); return true;
  });
  if (!claimed) return {status:'checking'};
  let status='error', reason='', healthy=false, releaseId='';
  try {
    let inspection;
    try {inspection = await inspectProduction(env,fetcher,now);}
    catch {inspection = {healthy:false,reason:'production-unreachable'};}
    ({healthy, reason, releaseId = ''} = inspection);
    if (healthy) status='healthy';
    else if (minutes < 485) status='waiting';
    else {
      const config = configuration(env);
      if (!env.GITHUB_TOKEN) throw new Error('Missing GitHub token');
      let committed = null;
      // A just-published repository edition needs deployment recovery, not repeated AI generation.
      const response = await request(fetcher, `${config.api}/contents/public/data/release.json?ref=main`, {
        headers:{...config.headers,Accept:'application/vnd.github.raw+json'},
      });
      if (response.ok) committed = await response.json();
      else if (response.status !== 404) throw new Error('Repository check unavailable');
      if (validManifest(committed) && committed.editionDate===date) status='deployment-lag';
      else {
        const runs = await json(fetcher,`${config.api}/actions/workflows/daily-news.yml/runs?branch=main&per_page=20`,{headers:config.headers});
        if (!Array.isArray(runs.workflow_runs)) throw new Error('Invalid workflow response');
        if (runs.workflow_runs.some(run=>ACTIVE.has(run.status))) status='running';
        else {
          const reserved = await storage.transaction(async txn=>{
            const state = await txn.get(key);
            if (state.attempts>=2 || stamp-(state.lastAttemptAt || 0)<1800000) return false;
            state.attempts++; state.lastAttemptAt=stamp;
            await txn.put(key,state); return true;
          });
          if (reserved) {
            status='dispatch-uncertain';
            const dispatch = await request(fetcher,`${config.api}/actions/workflows/daily-news.yml/dispatches`,{
              method:'POST',headers:{...config.headers,'Content-Type':'application/json'},
              body:JSON.stringify({ref:'main',inputs:{force_refresh:'false'}}),
            });
            if (dispatch.status !== 204) throw new Error('Recovery dispatch rejected');
            status='recovery-requested';
          } else status='recovery-limited';
        }
      }
    }
  } catch (error) {
    if (status!=='dispatch-uncertain') status='check-failed';
    reason = error?.message === 'Missing GitHub token' ? 'missing-token' : 'upstream-error';
  }
  try {
    if (!healthy && minutes >= 485 && env.ALERT_WEBHOOK_URL) {
      const alertURL = new URL(env.ALERT_WEBHOOK_URL);
      if (alertURL.protocol !== 'https:') throw new Error('Alert webhook must use HTTPS');
      const alert = await storage.transaction(async txn=>{
        const state=await txn.get(key);
        if (state.alertReserved) return false;
        state.alertReserved=true; await txn.put(key,state); return true;
      });
      if (alert) {
        try {
          const response=await request(fetcher,alertURL.href,{method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({text:`NewsFrontier ${date} 发布检查异常：${status}；${reason}。请检查任务与部署。`,date,status,reason})});
          await storage.transaction(async txn=>{const state=await txn.get(key);state.alertDelivered=response.ok;await txn.put(key,state);});
        } catch {
          await storage.transaction(async txn=>{const state=await txn.get(key);state.alertDelivered=false;await txn.put(key,state);});
        }
      }
    }
  } finally {
    await storage.transaction(async txn=>{
      const state=await txn.get(key);
      state.status=status; state.reason=reason; state.releaseId=releaseId; state.checkedAt=now.toISOString();
      state.checkingUntil=0;
      if (healthy && !state.firstHealthyAt) state.firstHealthyAt=now.toISOString();
      if (healthy && minutes<=480) state.onTime=true;
      else if (minutes>=480 && state.onTime !== true) state.onTime=false;
      state.checks=[...(state.checks || []),{at:now.toISOString(),status}].slice(-20);
      await txn.put(key,state);
    });
    const cutoff = chinaClock(new Date(stamp-13*86400000)).date;
    const entries=await storage.list({prefix:'day:'});
    const expired=[...entries.keys()].filter(key=>key.slice(4)<cutoff);
    if (expired.length) await storage.delete(expired);
  }
  return {date,status,reason,releaseId};
}

export class PublicationWatchdog {
  constructor(ctx,env) {this.ctx=ctx;this.env=env;}
  async fetch(request) {
    if (request.method==='POST' && new URL(request.url).pathname==='/check') {
      return Response.json(await monitor(this.env,this.ctx.storage));
    }
    return new Response('Not found',{status:404});
  }
}
export default {
  async scheduled(_event,env,ctx) {
    if (env.ENABLED !== 'true') return;
    const object=env.WATCHDOG.get(env.WATCHDOG.idFromName('frontier-publication'));
    ctx.waitUntil(object.fetch(new Request('https://internal/check',{method:'POST'})).then(async response=>{
      if (!response.ok) throw new Error('Watchdog check failed');
      console.log(JSON.stringify(await response.json()));
    }));
  },
  // Deliberately no public route for running checks or dispatching workflows.
  async fetch() {return new Response('Not found',{status:404});},
};
