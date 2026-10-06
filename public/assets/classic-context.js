/* Specific method associations, grounded only in captured source evidence. */
(function(root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./classic-titles.js'));
  else root.FrontierClassicContext = factory(root.FrontierClassicTitles || {});
})(typeof globalThis !== 'undefined' ? globalThis : this, function(titles) {
  'use strict';
  const rules = [
    ['classic:ai:transformer', ['Transformer'], '序列建模'],
    ['classic:ai:ppo', ['PPO','proximal policy optimization'], '策略优化'],
    ['classic:cv:resnet', ['ResNet','residual network'], '残差特征提取'],
    ['classic:cv:sift', ['SIFT','scale-invariant feature transform'], '局部特征匹配'],
    ['classic:slam:orbslam2', ['ORB-SLAM2','ORB-SLAM 2'], '视觉定位建图'],
    ['classic:slam:vinsmono', ['VINS-Mono','VINS Mono'], '视觉惯性状态估计'],
    ['classic:gnc:kalman1960', ['Kalman filter','卡尔曼滤波'], '线性状态估计'],
    ['classic:gnc:mayne2000', ['constrained model predictive control','约束模型预测控制'], '约束预测控制'],
    ['classic:uav:mellinger-minimum-snap-2011', ['minimum-snap trajectory','minimum snap trajectory','最小 snap 轨迹'], '平滑飞行轨迹'],
    ['classic:uav:loquercio-dronet-2018', ['DroNet'], '视觉飞行策略'],
  ];
  const clean = value => String(value ?? '').replace(/\s+/g,' ').trim();
  const validDate = value => /^\d{4}-\d{2}-\d{2}$/.test(value || '')
    && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0,10) === value;
  const safe = value => {try {const u=new URL(value);return ['http:','https:'].includes(u.protocol)?u.href:'';} catch (_) {return '';}};
  const slug = value => clean(value).replace(/[^a-zA-Z0-9_-]+/g,'-').replace(/^-+|-+$/g,'') || 'story';
  const beijingDate = () => new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  function displayTitle(paper) {
    const entry=titles[paper?.id];
    return entry && entry.originalTitle === paper.title ? entry.titleZh : clean(paper?.title);
  }
  const stop = new Set(('the a an its new now for from with and of our this that these their company system platform robot robots rover vehicle drone navigation model network method product team research researchers software hardware launch launches unveils released announces uses'.split(' ')));
  function sameSubject(item, subject) {
    const title=clean(item.originalTitle || item.title).toLowerCase();
    const words=subject.toLowerCase().match(/[a-z][a-z0-9-]{2,}/g) || [];
    if (words.some(word=>!stop.has(word) && new RegExp('(^|[^a-z0-9-])'+word+'([^a-z0-9-]|$)','i').test(title))) return true;
    const names=subject.split(/[的\s]+|系统|模型|无人机|机器人/).filter(name=>/^[\u4e00-\u9fff]{2,12}$/.test(name));
    return names.some(name=>!['研究人员','研究团队','该公司','新平台','该平台'].includes(name) && title.includes(name));
  }
  const uncertain = /\b(?:not|never|without|may|might|could|will|plans?|considering|expected|previously|formerly|said|says|reports?|reported|compares?|compared|unlike|whereas|while|which|according)\b|不采用|不使用|未采用|未使用|没有|计划|可能|将采用|拟采用|此前|曾经|表示|声称|相比|而另一/i;
  function adoption(item, clause) {
    if (uncertain.test(clause)) return '';
    const english=clause.match(/^(.{2,180}?)\s+(?:now\s+)?(?:uses?|adopts?|employs?|implements?|integrates?|is based on|is built on|is powered by)\s+(.+)$/i);
    const chinese=clause.match(/^(.{2,80}?)(?:采用|使用|集成|基于)(.+)$/);
    const match=english || chinese;
    return match && sameSubject(item,match[1]) ? match[2] : '';
  }
  const contains = (text, alias) => {
    const escaped=alias.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    return new RegExp((/^[a-z]/i.test(alias)?'(^|[^a-z0-9])':'')+escaped+(/[a-z0-9]$/i.test(alias)?'([^a-z0-9]|$)':''),'i').test(text);
  };
  function relatedPapers(item, rows, today=beijingDate()) {
    if (!item || !Array.isArray(rows)) return [];
    const urls=new Set([item.url,...(item.sources || []).map(s=>s.url)].map(safe).filter(Boolean));
    const records=(item.evidenceRecords || []).filter(e=>e && ['body','feed'].includes(e.kind)
      && clean(e.evidenceId) && clean(e.fetchedAt) && urls.has(safe(e.url)));
    const published=new Map();
    [...rows].filter(r=>validDate(r?.date) && r.date<=today && r.paper)
      .sort((a,b)=>b.date.localeCompare(a.date)).forEach(r=>{if(!published.has(r.paper.id))published.set(r.paper.id,r);});
    const links=[];
    for (const [id,aliases,problem] of rules) {
      const row=published.get(id);
      if (!row || (titles[id] && titles[id].originalTitle !== row.paper.title)) continue;
      let evidence=null;
      for (const record of records) {
        if (clean(record.text).split(/[.!?。！？;；,，]+/).some(clause=>{
          const method=adoption(item,clean(clause));
          return method && aliases.some(alias=>contains(method,alias));
        })) {evidence=record;break;}
      }
      if (evidence) links.push({...row,problem,evidence});
    }
    return links.slice(0,3);
  }
  function relatedNews(paper, items, rows, today=beijingDate()) {
    const seen=new Set();
    return (items || []).filter(item=>{
      const key=[item.editionDate,item.releaseId,item.id].join(':');
      if (!validDate(item.editionDate) || item.editionDate>today || seen.has(key)) return false;
      const linked=relatedPapers(item,rows,today).some(r=>r.paper.id===paper.id);
      if(linked)seen.add(key);return linked;
    }).sort((a,b)=>b.editionDate.localeCompare(a.editionDate)).slice(0,3);
  }
  function newsHref(item) {
    if (!clean(item?.id) || !validDate(item?.editionDate)) return '';
    const query=new URLSearchParams({view:'history',date:item.editionDate});
    if (/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(item.releaseId || '')) query.set('release',item.releaseId);
    return '?'+query.toString()+'#item-'+slug(item.id);
  }
  function paperHref(row, news) {
    if (!row?.paper?.id || !validDate(row.date)) return '';
    const query=new URLSearchParams({view:'research',date:row.date,paper:row.paper.id});
    if (validDate(news?.editionDate)) query.set('newsDate',news.editionDate);
    if (/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(news?.releaseId || '')) query.set('release',news.releaseId);
    return '?'+query.toString()+'#classic-'+slug(row.paper.id)+'-'+row.date;
  }
  return {displayTitle,relatedPapers,relatedNews,newsHref,paperHref};
});
