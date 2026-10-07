(() => {
  'use strict';
  const api=window.FrontierClassicClient;
  const context=window.FrontierClassicContext;
  const section=document.getElementById('classicSection');
  const bookmarksSection=document.getElementById('classicBookmarks');
  const KEY='fp-classic-snapshot-v1', SAVED='fp-classic-bookmarks-v1';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const safe=v=>{try{const u=new URL(v);return ['http:','https:'].includes(u.protocol)?u.href:'';}catch(_){return '';}};
  const read=(key,fallback)=>{try{return JSON.parse(localStorage.getItem(key))??fallback;}catch(_){return fallback;}};
  const write=(key,value)=>{try{localStorage.setItem(key,JSON.stringify(value));}catch(_){/* privacy/quota */}};
  let state=null, active=false, request=0, mode='daily', date='', query='', domain='';
  let contextPromise=null, newsProvider=null, associatedNews=[];
  const entryParams=new URLSearchParams(location.search);
  const newsDate=entryParams.get('newsDate') || '';
  const newsRelease=entryParams.get('release') || '';
  const entryPaper=entryParams.get('paper') || '';
  let paperScrolled=false;
  let saved=read(SAVED,[]);
  if(!Array.isArray(saved))saved=[];
  saved=saved.filter(api.validFavorite);
  const labels={problem:'研究问题',method:'方法',contribution:'贡献',applicability:'适用条件',limitations:'局限',readingAdvice:'建议阅读'};
  const domains={AI:'AI · 人工智能',SLAM:'SLAM · 定位建图',GNC:'GNC · 制导导航控制',CV:'CV · 计算机视觉',UAV:'UAV · 无人飞行系统'};
  const link=(url,label)=>safe(url)?`<a href="${esc(safe(url))}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`:'';
  section.innerHTML=`<div class="classic-toolbar"><div class="classic-tabs" role="group" aria-label="论文阅读范围">
    <button type="button" data-classic-mode="daily">当日推荐</button><button type="button" data-classic-mode="history">论文历史库</button>
    </div><div class="date-control classic-date-control"><span>推荐日期 · 北京时间</span><div>
    <button type="button" id="classicPrevious" aria-label="上一日推荐">←</button><input type="date" id="classicDate" aria-label="选择论文推荐日期">
    <button type="button" id="classicNext" aria-label="下一日推荐">→</button></div><small id="classicDateHint"></small></div></div>
    <div id="classicHistoryControls" class="classic-history-controls" hidden><label>标题或作者<input type="search" id="classicSearch" placeholder="搜索已推荐论文标题、完整作者" autocomplete="off"></label>
    <label>主领域<select id="classicDomain"><option value="">全部主领域</option>${Object.entries(domains).map(([k,v])=>`<option value="${k}">${esc(v)}</option>`).join('')}</select></label></div>
    <p id="classicNotice" class="classic-notice" role="status"></p><p id="classicStock" class="classic-stock" hidden></p>
    <div id="classicCards" class="classic-grid" aria-live="polite" aria-busy="false"></div>`;
  const $=id=>document.getElementById(id);
  const savedKey=s=>s.paper.id; // One identity; reread does not duplicate a favorite.
  const isSaved=p=>saved.some(s=>savedKey(s)===p.id);
  const paperRows=()=>state?Object.entries(state.archive.editions)
    .flatMap(([date,edition])=>edition.items.map(paper=>({date,paper}))):[];
  const paperAnchor=(id,day)=>'classic-'+String(id).replace(/[^a-zA-Z0-9_-]+/g,'-').replace(/^-+|-+$/g,'')+'-'+day;
  function newsLinks(paper) {
    const linked=context?.relatedNews(paper,associatedNews,paperRows()) || [];
    return linked.length?`<aside class="classic-news-links" aria-label="采用相关方法的新闻"><span>相关动态</span><ul>${linked.map(news=>
      `<li><a href="${esc(context.newsHref(news))}">${esc(news.title)}</a><time datetime="${esc(news.editionDate)}">${esc(news.editionDate)}</time></li>`).join('')}</ul></aside>`:'';
  }

  function card({paper:p,date:d}) {
    const guides=Object.entries(labels).map(([key,label])=>`<section><h4>${label}</h4><p>${esc(p.guide[key])}</p>
      <small>${esc((p.sourceLocators||[]).filter(l=>l.section===key).map(l=>(l.classification==='readerInference'?'阅读推论 · ':'全文依据 · ')+l.locator).join('；'))}</small></section>`).join('');
    const title=api.displayTitle(p);
    return `<article class="classic-card" id="${esc(paperAnchor(p.id,d))}" data-classic-id="${esc(p.id)}" data-classic-date="${esc(d)}"><div class="meta"><span class="cat">${esc(domains[p.primaryDomain]||p.primaryDomain)}</span>
      ${p.classicReread?`<span>经典重读 · 上次 ${esc(p.previousRecommendationDate)}</span>`:''}</div>
      <h3>${esc(title)}</h3>${title!==p.title?`<p class="classic-original-title" lang="en">${esc(p.title)}</p>`:''}<p class="classic-authors">${esc(p.authors.join(', '))}</p>
      <p class="classic-bibliography">发表年份：<b>${esc(p.year)}</b> · ${esc(p.venue)}<br>推荐日期：<time datetime="${esc(d)}">${esc(d)}</time></p>
      <p class="classic-overview">${esc(p.overview)}</p><div class="classic-actions">${link(p.canonicalUrl,'书目原文')}${link(p.fullText?.url,'阅读全文')}
      <button type="button" data-classic-save aria-pressed="${isSaved(p)}">${isSaved(p)?'取消收藏':'收藏'}</button><button type="button" data-classic-cite>复制引用</button></div>
      <details><summary>阅读导读</summary><div class="classic-guide">${guides}</div></details>${newsLinks(p)}</article>`;
  }
  function rows(){
    if(!state)return [];
    if(mode==='history')return api.search(state.archive,query,domain);
    const e=api.select(state,date);return e?e.items.map(paper=>({paper,date:e.recommendationDate})):[];
  }
  function sync(){
    if(!active)return;
    const params=new URLSearchParams({view:'research'});
    if(mode==='history'){params.set('classic','history');if(query)params.set('q',query);if(domain)params.set('domain',domain);}
    else if(date)params.set('date',date);
    if(newsDate)params.set('newsDate',newsDate);
    if(newsRelease)params.set('release',newsRelease);
    if(entryPaper)params.set('paper',entryPaper);
    history.replaceState(null,'',location.pathname+'?'+params.toString()+(location.hash || ''));
  }
  function render(){
    if(!active)return;
    const today=api.beijingDate();
    const dates=state?Object.keys(state.archive.editions).filter(d=>d<=today).sort().reverse():[];
    const selected=date||state?.edition.recommendationDate||'';
    $('classicDate').value=selected;
    $('classicDate').max=today;
    const i=dates.indexOf(selected);
    $('classicPrevious').disabled=i<0||i>=dates.length-1;
    $('classicNext').disabled=i<=0;
    $('classicPrevious').dataset.date=i>=0?dates[i+1]||'':'';
    $('classicNext').dataset.date=i>0?dates[i-1]||'':'';
    $('classicDateHint').textContent=`${dates.length}期推荐`;
    section.querySelector('.classic-date-control').hidden=mode!=='daily';
    $('classicHistoryControls').hidden=mode!=='history';
    section.querySelectorAll('[data-classic-mode]').forEach(b=>{b.classList.toggle('active',b.dataset.classicMode===mode);b.setAttribute('aria-pressed',String(b.dataset.classicMode===mode));});
    const health=state?api.health(state,date,today,state.cached):'今日待更新';
    $('dataState').textContent=mode==='history'?'论文历史库':health;
    $('dataState').className='state-badge'+(health==='今日待更新'||state?.cached?' warning':'');
    const pending=health==='今日待更新';
    $('classicNotice').textContent=state
      ? `${pending?'今日待更新；当前保留上期推荐。':''}${state.cached?' 当前展示缓存，刷新可重试。':''}`
      : '尚无可用的经典推荐，稍后刷新可重试。';
    $('classicNotice').hidden=!$('classicNotice').textContent.trim();
    $('classicStock').hidden=true;
    const list=rows();
    $('classicCards').innerHTML=list.length?list.map(card).join(''):`<p class="classic-empty">${mode==='history'?'没有匹配的已推荐论文。':'所选日期尚无已发布推荐。'}</p>`;
    $('classicCards').setAttribute('aria-busy','false');
    $('dataNote').textContent='';
    sync();
    const entry=list.find(row=>row.paper.id===entryPaper);
    if(entry && !paperScrolled){
      paperScrolled=true;requestAnimationFrame(()=>$(paperAnchor(entryPaper,entry.date))?.scrollIntoView({block:'start'}));
    }
  }
  async function ensureContext(bypass=false){
    if(contextPromise){await contextPromise;if(!bypass)return state;}
    if(state && !bypass)return state;
    contextPromise=(async()=>{
      const loaded=await api.load(window.fetch.bind(window),state?.cache||read(KEY,null),bypass);
      state=loaded;if(!state.cached)write(KEY,state.cache);return state;
    })();
    try{return await contextPromise;}finally{contextPromise=null;}
  }
  async function loadAssociatedNews(){
    if(!context || !newsProvider){associatedNews=[];return;}
    try{associatedNews=await newsProvider({date:newsDate,release:newsRelease});}
    catch(_){associatedNews=[];}
  }
  async function show(options={}){
    active=true;section.hidden=false;const ticket=++request;
    if(options.date!==undefined)date=options.date;
    if(options.initial){const params=new URLSearchParams(location.search);mode=params.get('classic')==='history'?'history':'daily';date=params.get('date')||'';query=params.get('q')||'';domain=domains[params.get('domain')]?params.get('domain'):'';$('classicSearch').value=query;$('classicDomain').value=domain;}
    if(!state||options.bypassCache){
      $('classicCards').setAttribute('aria-busy','true');
      try{
        await ensureContext(Boolean(options.bypassCache));
        if(ticket!==request)return;
      }catch(error){
        if(ticket!==request)return;
        state=null;render();$('classicNotice').hidden=false;$('classicNotice').textContent='经典推荐读取失败：'+error.message+'；可点击刷新重试。';return;
      }
    }
    // Render the paper first; optional news failures cannot hide its guide.
    if(ticket===request)render();
    await loadAssociatedNews();
    if(ticket===request)render();
  }
  function hide(){active=false;++request;section.hidden=true;}
  function renderBookmarks(){
    bookmarksSection.innerHTML=saved.length?`<h2>收藏的经典论文</h2><div class="classic-grid">${saved.map(card).join('')}</div>`:'';
  }
  async function click(event){
    const target=event.target.closest('button');if(!target)return;
    if(target.dataset.classicMode){mode=target.dataset.classicMode;render();return;}
    if(target.id==='classicPrevious'||target.id==='classicNext'){date=target.dataset.date;render();return;}
    const element=target.closest('.classic-card');if(!element)return;
    const p=rows().find(r=>r.paper.id===element.dataset.classicId && r.date===element.dataset.classicDate)
      ||saved.find(s=>s.paper.id===element.dataset.classicId);
    if(!p)return;
    if(target.hasAttribute('data-classic-save')){
      if(isSaved(p.paper))saved=saved.filter(s=>s.paper.id!==p.paper.id);else saved.unshift(structuredClone(p));
      write(SAVED,saved);render();renderBookmarks();
    }else if(target.hasAttribute('data-classic-cite')){
      try{await navigator.clipboard.writeText(api.citation(p.paper));notify('已复制完整引用');}
      catch(_){notify('浏览器未允许复制，可从书目原文取得引用');}
    }
  }
  function notify(message){$('toast').textContent=message;$('toast').hidden=false;setTimeout(()=>$('toast').hidden=true,2600);}
  section.addEventListener('click',click);bookmarksSection.addEventListener('click',click);
  $('classicDate').addEventListener('change',e=>{date=e.target.value;render();});
  $('classicSearch').addEventListener('input',e=>{query=e.target.value;render();});
  $('classicDomain').addEventListener('change',e=>{domain=e.target.value;render();});
  window.FrontierClassics={show,hide,renderBookmarks,ensureContext,
    setNewsProvider:provider=>{newsProvider=provider;},
    relatedPapers:item=>context?.relatedPapers(item,paperRows()) || []};
})();
