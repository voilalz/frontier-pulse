(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.FrontierClassicClient = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const FILES = ['edition.json', 'archive.json', 'queue.json', 'status.json'];
  const SECTIONS = ['problem', 'method', 'contribution', 'applicability', 'limitations', 'readingAdvice'];
  const PAIRS = [['AI','SLAM'],['GNC','CV'],['UAV','AI'],['SLAM','GNC'],['CV','UAV']];
  const check = (ok, message) => { if (!ok) throw new Error(message); };
  const text = value => typeof value === 'string' && value.trim().length > 0;
  const day = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0,10) === value;
  const url = value => { try { return ['http:','https:'].includes(new URL(value).protocol); } catch (_) { return false; } };
  const header = (value, kind) => check(value?.schemaVersion === 1 && value.kind === kind
    && value.timezone === 'Asia/Shanghai' && value.anchorDate === '2026-09-30'
    && value.selectionRuleVersion === 'classic-calendar-v1', '经典数据版本校验失败');
  const sha = async value => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value))))
    .map(n=>n.toString(16).padStart(2,'0')).join('');
  const canonical = value => JSON.stringify(Object.fromEntries(Object.entries(value).sort(([a],[b])=>a.localeCompare(b))))+'\n';

  async function manifestCheck(m) {
    header(m,'classicRelease');
    check(/^c-[a-f0-9]{64}$/.test(m.releaseId || '') && m.basePath === `./releases/${m.releaseId}/`, '经典指针路径校验失败');
    check(m.files && Object.keys(m.files).sort().join() === [...FILES].sort().join()
      && FILES.every(f=>/^[a-f0-9]{64}$/.test(m.files[f])), '经典快照文件校验失败');
    check(m.releaseId === 'c-'+await sha(canonical(m.files)), '经典指针身份校验失败');
    check((m.recommendationDate === null || day(m.recommendationDate))
      && (m.latestPublishedDate === null || day(m.latestPublishedDate)), '经典指针日期校验失败');
  }

  function paperCheck(p) {
    check(p && text(p.id) && text(p.title) && Array.isArray(p.authors) && p.authors.length
      && p.authors.every(text) && Number.isInteger(p.year) && text(p.venue)
      && PAIRS.flat().includes(p.primaryDomain) && url(p.canonicalUrl) && url(p.fullText?.url)
      && text(p.overview) && text(p.classicRationale)
      && SECTIONS.every(s=>text(p.guide?.[s]))
      && Array.isArray(p.classicEvidence) && p.classicEvidence.length >= 2
      && p.classicEvidence.every(e=>url(e.url) && text(e.locator))
      && Array.isArray(p.sourceLocators) && p.sourceLocators.length
      && p.sourceLocators.every(l=>l && ['overview',...SECTIONS].includes(l.section)
        && ['paperFact','readerInference'].includes(l.classification) && text(l.locator)), '经典论文内容校验失败');
    check(typeof p.classicReread === 'boolean' && p.classicReread === (p.previousRecommendationDate !== null)
      && (p.previousRecommendationDate === null || day(p.previousRecommendationDate)), '经典重读日期校验失败');
  }

  function editionCheck(e, date) {
    header(e,'classicEdition');
    check(day(date) && e.recommendationDate === date && e.itemCount === 2 && Array.isArray(e.items)
      && e.items.length === 2 && e.items[0].id !== e.items[1].id && text(e.publishedAt), '经典版次日期/两篇校验失败');
    e.items.forEach(paperCheck);
    const offset = (Date.parse(date)-Date.parse('2026-09-30'))/86400000;
    check(e.items.map(p=>p.primaryDomain).join() === PAIRS[((offset%5)+5)%5].join(), '经典领域轮换校验失败');
  }

  async function verify(cache) {
    check(cache && cache.payloads, '没有完整经典缓存');
    const m=cache.manifest;
    await manifestCheck(m);
    const state={manifest:m};
    for (const file of FILES) {
      const raw=cache.payloads[file];
      check(typeof raw === 'string' && await sha(raw) === m.files[file], '经典快照哈希校验失败');
      state[file.slice(0,-5)]=JSON.parse(raw);
    }
    header(state.archive,'classicArchive'); header(state.queue,'classicQueue'); header(state.status,'classicStatus');
    check(state.archive.editions && typeof state.archive.editions === 'object'
      && !Array.isArray(state.archive.editions), '经典历史库校验失败');
    for (const [date,e] of Object.entries(state.archive.editions)) editionCheck(e,date);
    const dates=Object.keys(state.archive.editions).sort();
    check((dates.at(-1)||null) === m.latestPublishedDate, '经典最新日期校验失败');
    if (m.recommendationDate !== null) {
      editionCheck(state.edition,m.recommendationDate);
      check(JSON.stringify(state.edition) === JSON.stringify(state.archive.editions[m.recommendationDate]), '经典历史/版次校验失败');
    } else {
      header(state.edition,'classicEdition');
      check(state.edition.recommendationDate === null && state.edition.itemCount === 0
        && Array.isArray(state.edition.items) && !state.edition.items.length && !dates.length, '经典空版次校验失败');
    }
    check(['ok','pending','restored'].includes(state.status.state)
      && state.status.editionDate === m.recommendationDate
      && state.status.latestPublishedDate === m.latestPublishedDate, '经典状态校验失败');
    state.cache=cache;
    return state;
  }

  async function load(fetcher, cached=null, bypass=false) {
    try {
      const options={cache:bypass?'no-store':'no-cache'};
      const get=async path=>{
        const response=await fetcher(path,options);
        check(response.ok,'经典数据读取失败'); return response.text();
      };
      const suffix=bypass?`?t=${Date.now()}`:'';
      const manifest=JSON.parse(await get('./classics/release.json'+suffix));
      await manifestCheck(manifest);
      const payloads=Object.fromEntries(await Promise.all(FILES.map(async f=>[f,await get('./classics/'+manifest.basePath.slice(2)+f+suffix)])));
      const state=await verify({manifest,payloads});
      return {...state,cached:false,error:''};
    } catch (error) {
      if (!cached) throw error;
      return {...await verify(cached),cached:true,error:error.message};
    }
  }

  function beijingDate(now=new Date()) {
    return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(now);
  }
  function select(state,date='',today=beijingDate()) {
    const selected=date||state.edition.recommendationDate;
    return selected && selected <= today ? state.archive.editions[selected] || null : null;
  }
  function health(state,date='',today=beijingDate(),cached=false) {
    if (date && date !== today) return '历史推荐';
    if (state.edition.recommendationDate !== today || state.status.state === 'pending') return '今日待更新';
    if (state.status.state === 'restored') return '已恢复历史版本';
    return cached?'经典缓存':'今日已更新';
  }
  function search(archive,query='',domain='',today=beijingDate()) {
    const q=String(query).trim().toLocaleLowerCase();
    return Object.entries(archive.editions).filter(([date])=>date<=today).sort(([a],[b])=>b.localeCompare(a))
      .flatMap(([date,e])=>e.items.map(paper=>({date,paper})))
      .filter(({paper})=>(!domain||paper.primaryDomain===domain)
        && (!q||[paper.title,...paper.authors].join(' ').toLocaleLowerCase().includes(q)));
  }
  function validFavorite(value) {
    try { check(day(value?.date),'收藏日期错误'); paperCheck(value.paper); return true; } catch (_) { return false; }
  }
  const citation = p => `${p.authors.join(', ')}. ${p.title}. ${p.venue}, ${p.year}. ${p.canonicalUrl}`;
  return {load,verify,select,health,search,citation,beijingDate,validFavorite};
});
