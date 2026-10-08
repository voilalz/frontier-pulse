(() => {
  "use strict";

  const publication = window.FrontierPublication;
  const classicUI = window.FrontierClassics;
  let releaseManifest = null;
  let editionVersion = null;
  const RELEASE_CACHE_KEY = "fp-release-manifest-v1";
  const publicationCacheKey = (key) => releaseManifest ? `${key}:${releaseManifest.releaseId}` : key;

  const ENDPOINTS = {
    latest: "./data/news.json",
    deepread: "./data/deepread.json",
    deepreadIndex: "./data/deepread/index.json",
    stream: "./data/stream.json",
    streamStatus: "./data/stream-status.json",
    research: "./data/research.json",
    status: "./data/status.json",
    archive: "./data/archive/index.json",
    search: "./data/archive/search-index.json",
  };
  let newsPolicy = null;
  const CATEGORIES = ["AI", "航空航天", "军事动态", "局部冲突", "前沿技术", "无人系统"];
  const VIEWS = new Set(["latest", "deepread", "stream", "research", "history", "bookmarks", "watchlist"]);
  const PAGE_SIZE = 24;
  const CACHE_KEY = "fp-last-good-report-v2";
  const STREAM_CACHE_KEY = "fp-last-good-stream-v1";
  const RESEARCH_CACHE_KEY = "fp-last-good-research-v1";
  const DEEPREAD_CACHE_KEY = "fp-last-good-deepread-v1";
  const BOOKMARK_KEY = "fp-bookmarks-v2";
  const WATCH_KEY = "fp-watchwords-v1";
  const RESEARCH_KEYWORDS_KEY = "fp-research-keywords-v1";
  const RESEARCH_SCOPE_KEY = "fp-research-scope-v1";
  const THEME_KEY = "fp-theme-v1";

  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
  const clean = (value, fallback = "") => String(value ?? fallback).replace(/\s+/g, " ").trim();
  const safeUrl = (value) => {
    try {
      const url = new URL(String(value));
      return ["http:", "https:"].includes(url.protocol) ? url.href : "";
    } catch (_) {
      return "";
    }
  };
  const readStorage = (key, fallback) => {
    try {
      const value = JSON.parse(localStorage.getItem(key));
      return value ?? fallback;
    } catch (_) {
      return fallback;
    }
  };
  const writeStorage = (key, value) => {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) { /* quota/privacy mode */ }
  };

  const params = new URLSearchParams(location.search);
  const initialView = VIEWS.has(params.get("view")) ? params.get("view") : "latest";
  const initialDate = /^\d{4}-\d{2}-\d{2}$/.test(params.get("date") || "") ? params.get("date") : "";
  const initialRelease = /^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(params.get('release') || '') ? params.get('release') : '';
  const initialRange = [6, 12, 24].includes(Number(params.get("range"))) ? Number(params.get("range")) : 24;
  const storedResearchScope = readStorage(RESEARCH_SCOPE_KEY, "all") === "mine" ? "mine" : "all";
  const initialResearchScope = params.get("scope") === "mine" ? "mine" : storedResearchScope;
  const legacyBookmarks = readStorage("fp-bookmarks", []).filter((item) => typeof item === "string");
  const storedBookmarks = readStorage(BOOKMARK_KEY, []).filter((item) => item && typeof item === "object");

  const state = {
    view: initialView,
    viewRequest: 0,
    historicalSelection: false,
    deepreadRequest: 0,
    query: initialView === "research" ? "" : clean(params.get("q")),
    category: "全部",
    source: clean(params.get("source"), "全部"),
    rangeHours: initialRange,
    sort: "score",
    editionDate: initialDate,
    latestReport: null,
    streamReport: null,
    researchReport: null,
    deepreadReport: null,
    deepreadIndex: null,
    deepreadCache: new Map(),
    deepreadLoadError: "",
    streamStatus: null,
    currentReport: null,
    items: [],
    visible: [],
    visibleLimit: PAGE_SIZE,
    totalVisible: 0,
    archiveIndex: null,
    searchManifest: null,
    searchItems: null,
    editionCache: new Map(),
    expandedKeys: new Set(),
    pipelineStatus: null,
    bookmarks: storedBookmarks,
    watchwords: readStorage(WATCH_KEY, []).filter((word) => typeof word === "string").slice(0, 20),
    researchKeywords: [...new Set(readStorage(RESEARCH_KEYWORDS_KEY, [])
      .filter((word) => typeof word === "string")
      .map((word) => clean(word).slice(0, 60))
      .filter(Boolean))].slice(0, 20),
    researchScope: initialResearchScope,
    latestLoadError: "",
    streamLoadError: "",
    researchLoadError: "",
    usingCache: false,
    theme: readStorage(THEME_KEY, "") || (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light"),
    hashHandled: false,
  };
  if (!state.researchKeywords.length) state.researchScope = "all";

  function formatDate(value, includeTime = true) {
    return publication.formatDate(value, includeTime);
  }

  function editionTimezoneLabel(value) {
    const zone = clean(value, "Asia/Shanghai");
    if (zone === "Asia/Shanghai") return "版本日期 · 中国标准时间（UTC+8）";
    if (zone === "Asia/Tokyo") return "版本日期 · 东京时间（UTC+9）";
    return `版本日期 · ${zone}`;
  }

  function itemKey(item) {
    return clean(item._bookmarkKey) || `${clean(item.editionDate, "unknown")}::${clean(item.id)}`;
  }

  function normalizeSource(source, fallback = {}) {
    const url = safeUrl(source?.url || fallback.url);
    if (!url) return null;
    return {
      name: clean(source?.name || fallback.source || source?.domain || "原始来源"),
      domain: clean(source?.domain),
      evidenceGroup: clean(source?.evidenceGroup || source?.domain || source?.name),
      url,
      publishedAt: clean(source?.publishedAt || fallback.publishedAt),
    };
  }

  function normalizeHistoryContext(raw, editionDate = "", itemId = "") {
    if (!raw || typeof raw !== "object") return null;
    const candidates = (Array.isArray(raw.relatedStories) ? raw.relatedStories : []).map((story) => ({
      id: clean(story?.id),
      eventId: clean(story?.eventId),
      editionDate: /^\d{4}-\d{2}-\d{2}$/.test(clean(story?.editionDate)) ? clean(story.editionDate) : "",
      title: clean(story?.title || story?.originalTitle, "历史事件"),
      originalTitle: clean(story?.originalTitle),
      summary: clean(story?.summary),
      category: clean(story?.category, "前沿技术"),
      source: clean(story?.source, "历史归档"),
      publishedAt: clean(story?.publishedAt),
      associationScore: Math.max(0, Math.min(100, Number(story?.associationScore) || 0)),
      relationLabel: clean(story?.relationLabel, "相关主题演进"),
      associationReasons: (Array.isArray(story?.associationReasons) ? story.associationReasons : [])
        .map((reason) => clean(reason)).filter(Boolean).slice(0, 3),
    })).filter((story) => story.id && story.editionDate && story.title);
    const allowed = candidates.filter((story) => isAllowedNewsItem(story) && story.id !== itemId
      && (!editionDate || story.editionDate < editionDate));
    const analysisFiltered = Boolean(raw.analysisFiltered) || allowed.length !== candidates.length;
    const relatedStories = [...new Map(allowed.map((story) => [`${story.editionDate}::${story.id}`, story])).values()]
      .sort((a, b) => a.editionDate.localeCompare(b.editionDate)).slice(-5);
    const outlook = (Array.isArray(raw.outlook) ? raw.outlook : []).map((item) => ({
      horizon: clean(item?.horizon, "观察"),
      text: clean(item?.text),
      confidence: ["低", "中", "高"].includes(clean(item?.confidence)) ? clean(item.confidence) : "低",
    })).filter((item) => item.text).slice(0, 2);
    return {
      status: raw.status === "linked" && relatedStories.length ? "linked" : "no-match",
      lookbackDays: Math.max(7, Number(raw.lookbackDays) || 365),
      relatedCount: relatedStories.length,
      relatedStories,
      // Cached prose may describe a removed archive node; do not expose it.
      analysisFiltered,
      timelineSummary: analysisFiltered ? "" : clean(raw.timelineSummary),
      outlook: analysisFiltered ? [] : outlook,
      analysisProvider: clean(raw.analysisProvider, "rules"),
    };
  }

  function normalizeEvidenceMatrix(raw) {
    if (!raw || typeof raw !== "object") return null;
    const claims = (Array.isArray(raw.claims) ? raw.claims : []).map((claim) => ({
      text: clean(claim?.text),
      status: clean(claim?.status, "single-source"),
      statusLabel: clean(claim?.statusLabel, "仍需核验"),
      sourceGroups: (Array.isArray(claim?.sourceGroups) ? claim.sourceGroups : []).map((value) => clean(value)).filter(Boolean).slice(0, 8),
    })).filter((claim) => claim.text).slice(0, 4);
    const disputes = (Array.isArray(raw.disputes) ? raw.disputes : []).map((dispute) => ({
      label: clean(dispute?.label, "公开说法存在差异"),
      current: clean(dispute?.current),
      historical: clean(dispute?.historical),
      editionDate: clean(dispute?.editionDate),
      note: clean(dispute?.note),
    })).filter((dispute) => dispute.current || dispute.historical).slice(0, 3);
    return {
      overallStatus: clean(raw.overallStatus, "single-source"),
      independentSourceCount: Math.max(1, Number(raw.independentSourceCount) || 1),
      sourceGroups: (Array.isArray(raw.sourceGroups) ? raw.sourceGroups : []).map((value) => clean(value)).filter(Boolean).slice(0, 12),
      claims,
      disputes,
      explanation: clean(raw.explanation),
    };
  }

  function normalizeForecastLedger(raw) {
    return (Array.isArray(raw) ? raw : []).map((entry) => ({
      predictionId: clean(entry?.predictionId),
      eventId: clean(entry?.eventId),
      statement: clean(entry?.statement),
      horizon: clean(entry?.horizon, "观察"),
      confidence: clean(entry?.confidence, "低"),
      status: clean(entry?.status, "open"),
      statusLabel: clean(entry?.statusLabel, "待验证"),
      createdAt: clean(entry?.createdAt),
      dueAfter: clean(entry?.dueAfter),
      verificationSignals: (Array.isArray(entry?.verificationSignals) ? entry.verificationSignals : []).map((value) => clean(value)).filter(Boolean).slice(0, 4),
    })).filter((entry) => entry.predictionId && entry.statement).slice(0, 12);
  }

  function normalizeEventDossier(raw, eventId = "") {
    if (!raw || typeof raw !== "object") return null;
    const timeline = (Array.isArray(raw.timeline) ? raw.timeline : []).map((entry) => ({
      editionDate: clean(entry?.editionDate),
      newsId: clean(entry?.newsId),
      title: clean(entry?.title, "事件更新"),
      source: clean(entry?.source, "公开来源"),
      publishedAt: clean(entry?.publishedAt),
      score: Number(entry?.score) || null,
      relationLabel: clean(entry?.relationLabel),
      associationScore: Number(entry?.associationScore) || null,
    })).filter((entry) => entry.editionDate && entry.newsId).slice(-12);
    return {
      eventId: clean(raw.eventId || eventId),
      status: clean(raw.status, "new"),
      statusLabel: clean(raw.statusLabel, raw.status === "tracking" ? "持续跟踪" : "新事件"),
      firstSeen: clean(raw.firstSeen),
      lastSeen: clean(raw.lastSeen),
      updateCount: Math.max(timeline.length, Number(raw.updateCount) || 0),
      independentSourceCount: Math.max(1, Number(raw.independentSourceCount) || 1),
      paperCount: Math.max(0, Number(raw.paperCount) || 0),
      timeline,
    };
  }

  function normalizeRelatedRecords(raw, type) {
    return (Array.isArray(raw) ? raw : []).map((record) => ({
      id: clean(record?.id),
      eventId: clean(record?.eventId),
      title: clean(record?.title || record?.originalTitle, type === "paper" ? "相关论文" : "相关新闻"),
      originalTitle: clean(record?.originalTitle),
      category: clean(record?.category),
      researchArea: clean(record?.researchArea),
      editionDate: clean(record?.editionDate),
      publishedAt: clean(record?.publishedAt),
      url: safeUrl(record?.url),
      pdfUrl: safeUrl(record?.pdfUrl),
      associationScore: Math.max(0, Math.min(100, Number(record?.associationScore) || 0)),
      relationType: clean(record?.relationType, "同主题关联"),
      associationReasons: (Array.isArray(record?.associationReasons) ? record.associationReasons : []).map((value) => clean(value)).filter(Boolean).slice(0, 3),
    })).filter((record) => record.id && record.title).slice(0, 6);
  }

  const withoutCalendarMay = text => text.replace(/\bMay\.?\s+\d{1,4}\b|\b\d{1,2}(?:st|nd|rd|th)?\s+May\b(?=\s*(?:[,.;:!?]|$|\d{4}\b))|\b(?:in|on|by|for|until|during|from|since|through|before|after)\s+(?:\d{1,2}(?:st|nd|rd|th)?\s+)?May\b|\b(?:next|last|this|early|late)\s+May\b(?=\s*(?:[,.;:!?]|$|(?:the|a|an)\b))/gi, ' calendar month ');

  const quantityValues = text => {
    const normalized = text.normalize("NFKC");
    const scales = {hundred:100,thousand:1000,million:1e6,billion:1e9,trillion:1e12,decade:10,decades:10,century:100,centuries:100,
      百:100,千:1000,万:1e4,百万:1e6,千万:1e7,亿:1e8,十亿:1e9,万亿:1e12};
    const scalePattern = Object.keys(scales).sort((a,b)=>b.length-a.length).join("|");
    const values = new Set();
    // Decimal coefficients and integer scales avoid binary float mismatches.
    const canonical = (token, scale = 1) => {
      const digits = token.replaceAll(",", "");
      if (!/^\d+(?:\.\d+)?$/.test(digits)) return "id:" + digits;
      const [whole, fraction = ""] = digits.split(".");
      const coefficient = BigInt(whole + fraction) * BigInt(scale);
      const padded = coefficient.toString().padStart(fraction.length + 1, "0");
      const decimal = fraction.length ? padded.slice(0, -fraction.length) + "." + padded.slice(-fraction.length) : padded;
      return "number:" + (decimal.includes(".") ? decimal.replace(/0+$/, "").replace(/\.$/, "") : decimal);
    };
    const digitPattern = new RegExp("(\\p{Decimal_Number}+(?:[.,]\\p{Decimal_Number}+)*)(?:\\s*("+scalePattern+"))?", "giu");
    for (const m of normalized.matchAll(digitPattern)) {
      let scale = scales[(m[2]||"").toLowerCase()]||1;
      if (!m[2]) {
        const tail = normalized.slice(m.index + m[0].length);
        const abbreviation = /^\s*([kmbt])\b(?![.-][a-z0-9])/i.exec(tail);
        const currencyBefore = /(?:[$€£¥]|\b(?:USD|EUR|GBP|JPY|CNY))\s*$/i.test(normalized.slice(0, m.index));
        const currencyAfter = abbreviation && /^\s*(?:dollars?|euros?|pounds?|yen|yuan|USD|EUR|GBP|JPY|CNY)\b/i.test(tail.slice(abbreviation[0].length));
        if (abbreviation && (currencyBefore || currencyAfter)) scale = {k:1e3,m:1e6,b:1e9,t:1e12}[abbreviation[1].toLowerCase()];
      }
      values.add(canonical(m[1], scale));
    }
    const names = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety first second third fourth fifth sixth seventh eighth ninth tenth half".split(" ");
    const numbers = [...Array.from({length:21},(_,i)=>i),30,40,50,60,70,80,90,...Array.from({length:10},(_,i)=>i+1),0.5];
    const words = Object.fromEntries(names.map((n,i)=>[n,numbers[i]]));
    const tens = "twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety";
    const ones = "one|two|three|four|five|six|seven|eight|nine";
    const expression = "(?:"+tens+")(?:[-\\s]+(?:"+ones+"))?|"+names.sort((a,b)=>b.length-a.length).join("|");
    const wordPattern = new RegExp("\\b("+expression+")\\b(?:\\s*("+scalePattern+"))?", "gi");
    for (const m of normalized.matchAll(wordPattern)) values.add(canonical(String(m[1].toLowerCase().split(/[-\s]+/).reduce((total, word)=>total+words[word],0)), scales[(m[2]||"").toLowerCase()]||1));
    const months = "Jan(?:uary)? Feb(?:ruary)? Mar(?:ch)? Apr(?:il)? May Jun(?:e)? Jul(?:y)? Aug(?:ust)? Sep(?:tember)? Oct(?:ober)? Nov(?:ember)? Dec(?:ember)?".split(" ");
    const monthNames = "January February March April May June July August September October November December".split(" ");
    months.forEach((month,i)=>{
      const dated = i === 4 ? withoutCalendarMay(normalized) !== normalized
        : new RegExp("\\b"+month+"\\.?\\s+\\d{1,4}\\b", "i").test(normalized)
        || new RegExp("\\b\\d{1,2}(?:st|nd|rd|th)?\\s+"+month+"\\b", "i").test(normalized)
        || new RegExp("\\b(?:in|by|until|during|from|since|through|before|after|next|last|this|early|late)\\s+"+month+"\\b", "i").test(normalized);
      const named = ![2,4].includes(i) && new RegExp("\\b"+monthNames[i]+"\\b", "i").test(normalized);
      if (dated || named) values.add(canonical(String(i+1)));
    });
    for (const m of normalized.matchAll(/\b(\d{1,2})[.:](\d{2})\s*(am|pm)\b/gi)) {
      const hour=Number(m[1]), minute=Number(m[2]);
      if(hour>=1&&hour<=12&&minute<60) [hour,minute,hour%12+(m[3].toLowerCase()==="pm"?12:0)].forEach(n=>values.add(canonical(String(n))));
    }
    for (const m of normalized.matchAll(/\b(\d+(?:\.\d+)?)m\s+years?\b/gi)) values.add(canonical(m[1],1e6));
    const ignoredModels = new Set("jan feb mar apr may jun jul aug sep oct nov dec in on by for at of to a an usd eur gbp jpy cny us uk esa ai".split(" "));
    for (const m of normalized.matchAll(/(?<![a-z0-9])([a-z]{1,3})[.\s-]?(\d+(?:\.\d+)*)([a-z]{0,2})(?![a-z0-9])/gi)) {
      if (!ignoredModels.has(m[1].toLowerCase())) values.add("model:" + m[1].toLowerCase() + m[2] + m[3].toLowerCase());
    }
    return values;
  };
  const validZh = (text, source) => {
    if(typeof text!=="string"||typeof source!=="string"||!/[\u4e00-\u9fff]/.test(text))return false;
    const available=quantityValues(source);
    return [...quantityValues(text)].every(n=>available.has(n));
  };

  function proseDisplayText(value, sourceText, evidenceRefs) {
    const chineseNumber = token => {
      const digits = Object.fromEntries([..."零〇一二两三四五六七八九"].map((char, index) => [char, [0,0,1,2,2,3,4,5,6,7,8,9][index]]));
      if (token.includes("点")) {
        const [whole, fraction] = token.split("点");
        return chineseNumber(whole) + Number("0." + [...fraction].map(char => digits[char]).join(""));
      }
      for (const [unit, scale] of [["亿", 1e8], ["万", 1e4]]) {
        if (token.includes(unit)) {
          const position = token.indexOf(unit);
          return chineseNumber(token.slice(0, position) || "一") * scale + chineseNumber(token.slice(position + 1));
        }
      }
      if (!/[十百千]/.test(token)) return Number([...token].map(char => digits[char]).join("") || "0");
      let total = 0, current = 0;
      for (const char of token) {
        if (Object.hasOwn(digits, char)) current = digits[char];
        else { total += (current || 1) * {十:10, 百:100, 千:1000}[char]; current = 0; }
      }
      return total + current;
    };
    const proseQuantities = text => {
      text = text.normalize("NFKC");
      const values = quantityValues(text);
      const numeral = "[零〇一二两三四五六七八九十百千万亿]+(?:点[零〇一二三四五六七八九]+)?";
      const units = "个|项|名|人|家|台|艘|架|颗|枚|辆|套|组|种|年|月|日|天|次|倍|米|秒|小时|美元|元|%|％";
      const magnitudes = {十:10,百:100,千:1000,万:1e4,百万:1e6,千万:1e7,亿:1e8,十亿:1e9,万亿:1e12};
      const approximate = new RegExp("(?:数|几)(" + Object.keys(magnitudes).sort((a,b)=>b.length-a.length).join("|") + ")(?=" + units + ")", "g");
      const exactText = text.replace(approximate, (_, unit) => { values.add("approx:" + magnitudes[unit]); return " "; })
        // quantityValues already counted each Arabic coefficient with its scale.
        .replace(/\d+(?:[.,]\d+)*\s*(?:万亿|百万|千万|十亿|亿|万|千|百)/g, " ");
      for (const [word, magnitude] of Object.entries({tens:10,hundreds:100,thousands:1000,millions:1e6,billions:1e9,trillions:1e12})) {
        if (new RegExp("\\b" + word + "\\b", "i").test(text)) values.add("approx:" + magnitude);
      }
      const pattern = new RegExp("(?<![上下每这那另唯])(" + numeral + ")(?=" + units + ")|百分之(" + numeral + ")", "g");
      for (const match of exactText.matchAll(pattern)) values.add("number:" + chineseNumber(match[1] || match[2]));
      if (/\b(?:a|an)\b/i.test(text)) values.add("number:1");
      const numberWords = new Set("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety first second third fourth fifth sixth seventh eighth ninth tenth half".split(" "));
      for (const match of text.matchAll(/\bonly\s+((?:[a-z]+[- ]+){0,4})(?:weapon|model|system|ship|capsule|company)\b/gi)) {
        if (![...match[1].matchAll(/[a-z]+/gi)].some(word => numberWords.has(word[0].toLowerCase()))) values.add("number:1");
      }
      return values;
    };
    const scope = [
      /计划|规划|拟|预计|预期|将|即将|有望|预定|未来|可能|\b(?:plans?|planned|will|scheduled|expected|may|might|could)\b/i,
      /仅|只|唯一|有限|限定|受限|限制|\b(?:only|limited)\b/i,
      /模拟|仿真|\b(?:simulation|simulated)\b/i,
      /初步|初期|初始|\bpreliminary\b/i,
      /部分|一些|若干|少数|小规模|\b(?:some|partial|small.scale)\b/i,
      /并非|而非|不|未|没有|无|失败|\b(?:not|no|without|never|failed|unsuccessful)\b|\b\w+n['’]t\b/i,
    ];
    const negativeActions = [
      ["approv\\w*|permission|clearance|authori[sz]\\w*", "批准|获批|许可|授权"],
      ["production|commercial\\w*", "量产|生产|商用|商业化"],
      ["publish\\w*|reveal\\w*|disclos\\w*|announc\\w*", "公布|披露|发布|公开|宣布"],
      ["launch\\w*", "发射|推出|发布"], ["deploy\\w*", "部署"],
      ["test\\w*|validat\\w*|prov\\w*", "测试|验证|证明"], ["success\\w*|succeed\\w*", "成功"],
    ];
    const negationValid = (text, source) => source.split(/[.;,:]|\b(?:and|but)\b/i).every(clause => {
      if (!scope.at(-1).test(clause)) return true;
      const action = negativeActions.find(([original]) => new RegExp("\\b(?:" + original + ")\\b", "i").test(clause));
      return !action || new RegExp("(?:不|未|没有|无|失败)[^，。；！？,;.!?]{0,16}(?:" + action[1] + ")|(?:" + action[1] + ")(?:失败|未成功)").test(text);
    });
    const scopeSource = typeof sourceText === 'string' ? withoutCalendarMay(sourceText) : '';
    return value && value.version === 1 && value.language === "zh-CN"
      && ["deepseek", "openai"].includes(value.provider)
      && typeof sourceText === "string" && sourceText.length >= 10 && sourceText.length <= 900 && sourceText === sourceText.trim()
      && Array.isArray(evidenceRefs) && evidenceRefs.length
      && value.sourceText === sourceText && JSON.stringify(value.sourceEvidenceRefs) === JSON.stringify(evidenceRefs)
      && typeof value.text === "string" && value.text.length >= 10 && value.text.length <= 900
      && value.text === value.text.trim() && !/[<>\x00-\x1f]|(?:https?|javascript|data|file|vbscript)\s*:/i.test(value.text)
      && /[\u4e00-\u9fff]/.test(value.text) && [...proseQuantities(value.text)].every(n => proseQuantities(sourceText).has(n))
      && !/\b[a-z]{2,}(?:[\s\u0085]+[a-z]{2,}){2,}\b/.test(value.text)
      && (!/[\u4e00-\u9fff]/.test(sourceText) || value.text === sourceText)
      && negationValid(value.text, sourceText) && scope.every(pattern => !pattern.test(scopeSource) || pattern.test(value.text))
      ? value.text : "";
  }

  function readerTextValid(value) {
    return typeof value === 'string' && /[\u3400-\u9fff]/.test(value)
      && !/现有元数据|元数据未(?:提供|说明)|未提取到可引用的正文|未提供更多(?:摘要|信息|细节)|这条新闻来自|现有(?:信息|报道)(?:仅包含|未提供)|目前披露的信息仅涉及|文章.{0,180}(?:最初发表于|最先发表于)/.test(value)
      && !/\b[a-z]{2,}(?:\s+[a-z]{2,}){2,}\b/.test(value.replace(/\([^)]*\)|（[^）]*）/g,''));
  }

  function legacyReaderSummary(value) {
    if (typeof value !== 'string') return '';
    // Older editions appended collection notes to otherwise usable Chinese.
    // Remove only a separate note sentence; validate all remaining prose.
    const noteStart = /^(?:现有元数据|元数据未(?:提供|说明)|未提取到可引用的正文|未提供更多(?:摘要|信息|细节)|这条新闻来自|现有(?:信息|报道)(?:仅包含|未提供)|目前披露的信息仅涉及|文章.{0,180}(?:最初发表于|最先发表于))/;
    const sentences = value.split(/(?<=[。！？])\s*/);
    return sentences.some(sentence=>noteStart.test(sentence.trim()))
      ? sentences.filter(sentence=>!noteStart.test(sentence.trim())).join(' ').trim() : value;
  }

  function normalizeItem(raw, index, editionDate = "") {
    if (!raw || typeof raw !== "object" || !clean(raw.title)) throw new Error(`第 ${index + 1} 条新闻缺少标题`);
    const sources = (Array.isArray(raw.sources) ? raw.sources : [])
      .map((source) => normalizeSource(source, raw))
      .filter(Boolean);
    if (!sources.length) {
      const primary = normalizeSource({}, raw);
      if (primary) sources.push(primary);
    }
    const t = raw.displayTranslation;
    const sourceSummary = typeof raw._policySummary === 'string' ? raw._policySummary : raw.summary;
    const sourceRefs = raw.summaryEvidenceRefs;
    const records = (Array.isArray(raw.evidenceRecords) ? raw.evidenceRecords : [])
      .filter(record=>record && typeof record === "object").map(record=>({...record,url:safeUrl(record.url)}));
    const bound = t && t.version === 1 && t.language === "zh-CN"
      && ["deepseek", "openai"].includes(t.provider)
      && typeof t.sourceTitle === 'string' && typeof t.sourceSummary === 'string'
      && t.sourceTitle === raw.originalTitle && t.sourceSummary === sourceSummary
      && Array.isArray(t.sourceEvidenceRefs) && Array.isArray(sourceRefs)
      && JSON.stringify(t.sourceEvidenceRefs) === JSON.stringify(sourceRefs);
    const translatedTitle = bound && readerTextValid(t.title) && validZh(t.title, t.sourceTitle);
    const titleOnly = records.length === 0 && sourceRefs?.length === 0
      && legacyReaderSummary(sourceSummary) === '';
    const displaySummary = bound ? legacyReaderSummary(t.summary) : '';
    const translatedSummary = translatedTitle && (titleOnly ? displaySummary === ''
      : readerTextValid(displaySummary) && validZh(displaySummary, t.sourceTitle + " " + t.sourceSummary));
    const translated = translatedTitle && translatedSummary;
    const readerSummary = translated ? displaySummary : sourceSummary;
    const summary = raw.contentType === 'paper' ? clean(readerSummary) : readerTextValid(readerSummary) ? clean(readerSummary) : '';
    const item = {
      id: clean(raw.id, `item-${index}`),
      eventId: clean(raw.eventId),
      contentType: clean(raw.contentType, "news"),
      title: clean(translatedTitle ? t.title : raw.title),
      originalTitle: clean(raw.originalTitle || raw.title),
      summary,
      _policySummary: clean(sourceSummary),
      contentAvailability: titleOnly ? 'title-only' : clean(raw.contentAvailability, sourceSummary ? 'body' : 'title-only'),
      translationStatus: translated ? 'translated' : translatedTitle ? 'partial' : readerTextValid(sourceSummary) ? 'native' : 'pending',
      keyFacts: (Array.isArray(raw.keyFacts) ? raw.keyFacts : []).map((fact) => clean(fact)).filter(Boolean).slice(0, 4),
      why: clean(raw.why, "该事件的重要性需要结合后续公开信息继续判断。"),
      category: clean(raw.category, "前沿技术"),
      researchArea: clean(raw.researchArea),
      source: clean(raw.source || sources[0]?.name, "未知来源"),
      country: clean(raw.country, "国际"),
      publishedAt: clean(raw.publishedAt),
      updatedAt: clean(raw.updatedAt || raw.publishedAt),
      url: safeUrl(raw.url || sources[0]?.url),
      pdfUrl: safeUrl(raw.pdfUrl),
      image: safeUrl(raw.image),
      score: Number.isFinite(Number(raw.score)) ? Math.max(0, Math.min(100, Number(raw.score))) : null,
      scoreBasis: clean(raw.scoreBasis, raw._compact ? "按需加载" : "规则评分"),
      scoreComponents: raw.scoreComponents && typeof raw.scoreComponents === "object" ? raw.scoreComponents : {},
      scoreReasons: (Array.isArray(raw.scoreReasons) ? raw.scoreReasons : []).map((reason) => clean(reason)).filter(Boolean),
      confidence: clean(raw.confidence, Number(raw.corroboration) > 1 ? "中" : "待核验"),
      confidenceReason: clean(raw.confidenceReason, "旧版数据未提供完整置信度解释，请直接核验原始来源。"),
      tags: (Array.isArray(raw.tags) ? raw.tags : []).map((tag) => clean(tag)).filter(Boolean).slice(0, 5),
      corroboration: Math.max(1, Number(raw.corroboration) || sources.length || 1),
      sources,
      authors: (Array.isArray(raw.authors) ? raw.authors : []).map((author) => clean(author)).filter(Boolean).slice(0, 20),
      arxivCategories: (Array.isArray(raw.arxivCategories) ? raw.arxivCategories : []).map((category) => clean(category)).filter(Boolean),
      collectionKeywords: (Array.isArray(raw.collectionKeywords) ? raw.collectionKeywords : []).map((keyword) => clean(keyword)).filter(Boolean).slice(0, 20),
      primaryCategory: clean(raw.primaryCategory),
      peerReviewStatus: clean(raw.peerReviewStatus),
      abstract: clean(raw.abstract),
      question: clean(raw.question),
      method: clean(raw.method),
      findings: clean(raw.findings),
      limitations: clean(raw.limitations),
      isTopStory: Boolean(raw.isTopStory),
      streamRank: Number(raw.streamRank) || null,
      isSupplemental: Boolean(raw.isSupplemental),
      selectionWindowHours: Math.max(24, Number(raw.selectionWindowHours) || 24),
      selectionNote: clean(raw.selectionNote),
      diversityRelaxed: Boolean(raw.diversityRelaxed),
      translationProvider: clean(raw.translationProvider),
      historyContext: normalizeHistoryContext(raw.historyContext, clean(raw.editionDate || editionDate), clean(raw.id)),
      evidenceMatrix: normalizeEvidenceMatrix(raw.evidenceMatrix),
      forecastLedger: normalizeForecastLedger(raw.forecastLedger),
      eventDossier: normalizeEventDossier(raw.eventDossier, clean(raw.eventId)),
      relatedPapers: normalizeRelatedRecords(raw.relatedPapers, "paper"),
      relatedNews: normalizeRelatedRecords(raw.relatedNews, "news"),
      evidenceRecords: records,
      summaryEvidenceRefs: Array.isArray(sourceRefs) ? [...sourceRefs] : undefined,
      displayTranslation: bound ? {...t, sourceEvidenceRefs:[...t.sourceEvidenceRefs]} : undefined,
      releaseId: clean(raw.releaseId),
      editionDate: clean(raw.editionDate || editionDate),
      _compact: Boolean(raw._compact),
    };
    item._bookmarkKey = clean(raw._bookmarkKey) || itemKey(item);
    return item;
  }

  function isAllowedNewsItem(item) {
    if (item.contentType === "paper") return true;
    if (!newsPolicy) return false;
    if (!newsPolicy.enabled) return true;
    const lead = clean(item._policySummary || item.summary || item.description)
      .replace(/\b(?:U\.S\.|U\.K\.|U\.N\.|E\.U\.)/gi, (match) => match.replace(/\./g, ""))
      .split(/(?<=[!?。！？])\s*|(?<=\.)\s+/)[0].slice(0, 240);
    const subject = `${clean(item.title)} ${clean(item.originalTitle)} ${lead}`
      .replace(/’/g, "'").replace(/\bChinese[- ](?:American|British|Canadian|Australian)\b/gi, "").toLowerCase();
    return !newsPolicy.subject_terms.some((term) => {
      const needle = term.toLowerCase();
      if (/[\u3400-\u9fff]/.test(needle)) return subject.includes(needle);
      const escaped = needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      return new RegExp(`(^|[^a-z0-9])${escaped}([^a-z0-9]|$)`).test(subject);
    });
  }

  function normalizeReport(payload) {
    if (!payload || typeof payload !== "object" || !Array.isArray(payload.items)
        || (!payload.items.length && payload.coverageStatus !== 'insufficient')) {
      throw new Error("日报文件不存在或没有新闻条目");
    }
    const editionDate = clean(payload.editionDate);
    return withTranslationCoverage({
      ...payload,
      editionDate,
      generatedAt: clean(payload.generatedAt),
      timezone: clean(payload.timezone, "Asia/Shanghai"),
      method: clean(payload.method, "rules"),
      items: payload.items.slice(0, 100).map((item, index) => normalizeItem({...item,
        releaseId: payload.releaseId || item.releaseId}, index, editionDate)).filter(isAllowedNewsItem),
    });
  }

  function normalizeCollection(payload, type) {
    if (!payload || typeof payload !== "object" || !Array.isArray(payload.items)) {
      throw new Error(`${type === "paper" ? "论文" : "动态"}数据文件不可用`);
    }
    const limit = type === "paper" ? 200 : 500;
    const report = {
      ...payload,
      generatedAt: clean(payload.generatedAt),
      items: payload.items.slice(0, limit).map((item, index) => normalizeItem({ ...item, contentType: item.contentType || type }, index)).filter(isAllowedNewsItem),
    };
    return type === 'paper' ? report : withTranslationCoverage(report);
  }

  function withTranslationCoverage(report) {
    const count = report.items.filter(item=>item.translationStatus === 'translated').length;
    const partial = report.items.filter(item=>item.translationStatus === 'partial').length;
    const titleOnly = report.items.filter(item=>item.translationStatus === 'translated' && item.contentAvailability === 'title-only').length;
    const total = report.items.length;
    const configured = report.translationProvider || report.items.some(item=>item.displayTranslation);
    const status = total && count === total ? 'ok' : count || partial ? 'partial'
      : configured ? 'failed' : ['disabled', 'not-configured'].includes(report.translationStatus) ? report.translationStatus : 'not-configured';
    const warnings = (Array.isArray(report.translationWarnings) ? report.translationWarnings : [])
      .filter(value=>typeof value === 'string' && !/^(?:日报|全量动态)中文翻译(?:不完整|未完成)/.test(value));
    if (['partial', 'failed'].includes(status)) warnings.push(`中文翻译未完成：${count}/${total}${partial ? `，${partial} 条仅完成标题` : ''}`);
    let diagnostics = report.translationDiagnostics;
    if (diagnostics && typeof diagnostics === 'object' && Object.keys(diagnostics).length) {
      const missing = report.items.filter(item=>item.translationStatus !== 'translated').map(item=>item.id);
      const notAttempted = (Array.isArray(diagnostics.notAttemptedItemIds) ? diagnostics.notAttemptedItemIds : []).filter(id=>missing.includes(id));
      diagnostics = {...diagnostics, targetItemCount:total, totalTranslatedItemCount:count,
        totalMissingItemCount:missing.length, totalMissingItemIds:missing,
        notAttemptedItemIds:notAttempted, notAttemptedItemCount:notAttempted.length,
        coverageCompletionMessage:missing.length ? `还有 ${missing.length} 条中文译文待完成` : '中文译文已全部完成'};
    }
    return {...report, translatedItemCount:count, partialTranslatedItemCount:partial,
      titleOnlyTranslatedItemCount:titleOnly, translationStatus:status, translationWarnings:warnings,
      translationDiagnostics:diagnostics};
  }

  async function fetchJson(url, bypassCache = false) {
    const separator = url.includes("?") ? "&" : "?";
    const target = bypassCache ? `${url}${separator}t=${Date.now()}` : url;
    const response = await fetch(target, { cache: bypassCache ? "no-store" : "default" });
    if (!response.ok) { const error = new Error(`HTTP ${response.status}`); error.status = response.status; throw error; }
    return response.json();
  }

  function toast(message) {
    const element = $("toast");
    element.textContent = message;
    element.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { element.hidden = true; }, 2600);
  }

  async function loadPublication(bypassCache = false) {
    const cacheKey = initialRelease ? `${RELEASE_CACHE_KEY}:${initialRelease}` : RELEASE_CACHE_KEY;
    editionVersion = null;
    try {
      const manifest = publication.validateManifest(await fetchJson(initialRelease ? `./releases/${initialRelease}/manifest.json` : './data/release.json', bypassCache));
      if (initialRelease && manifest.releaseId !== initialRelease) throw new Error('指定版本与清单不一致');
      releaseManifest = manifest;
      writeStorage(cacheKey, manifest);
    } catch (error) {
      if (initialRelease) {
        const versionKey = `fp-edition-version-v1:${initialRelease}`;
        try {
          editionVersion = publication.validateEditionVersion(await fetchJson(`./data/edition-versions/${initialRelease}.json`, bypassCache), initialRelease);
          writeStorage(versionKey, editionVersion);
        } catch (versionError) {
          const cachedVersion = readStorage(versionKey, null);
          if (cachedVersion) editionVersion = publication.validateEditionVersion(cachedVersion, initialRelease);
          else throw new Error('指定历史版本暂时无法读取，请稍后重试。');
        }
        releaseManifest = editionVersion.manifest;
        writeStorage(cacheKey, releaseManifest);
        return;
      }
      const cached = readStorage(cacheKey, null);
      if (cached) releaseManifest = publication.validateManifest(cached);
      else if (error.status === 404) releaseManifest = null;
      else throw error;
    }
  }

  async function fetchPublicationJson(path, bypassCache = false) {
    const pinned = releaseManifest;
    if (editionVersion) {
      const bundle = editionVersion, date = bundle.news.editionDate, deepDate = bundle.deepread.editionDate;
      if (path === ENDPOINTS.latest || path === `./data/archive/${date}.json`) return bundle.news;
      if (path === ENDPOINTS.deepread || path === `./data/deepread/${deepDate}.json`) return bundle.deepread;
      if (path === ENDPOINTS.archive || path === ENDPOINTS.deepreadIndex) return {schemaVersion:1,releaseId:pinned.releaseId,
        editions:[{editionDate:path === ENDPOINTS.archive ? date : deepDate, itemCount:bundle.news.items.length}]};
      if (path === ENDPOINTS.search) return {schemaVersion:1,releaseId:pinned.releaseId,
        items:bundle.news.items.map(item=>({...item,editionDate:date}))};
      throw new Error('此链接仅包含所选历史版本，请返回首页查看其他日期。');
    }
    const payload = await fetchJson(publication.resolve(pinned, path), bypassCache);
    if (pinned !== releaseManifest) throw new Error("版本已切换，请重新读取");
    const current = path === ENDPOINTS.latest || path === ENDPOINTS.deepread
      || path === `./data/archive/${pinned?.editionDate}.json`
      || path === `./data/deepread/${pinned?.editionDate}.json`;
    if (pinned && ((current && !publication.accepts(pinned, payload))
      || ([ENDPOINTS.archive, ENDPOINTS.deepreadIndex, ENDPOINTS.search].includes(path) && payload.releaseId !== pinned.releaseId))) {
      throw new Error("内容版本与发布清单不一致");
    }
    return payload;
  }

  function showAlert(kind, title, detail) {
    const alert = $("systemAlert");
    const alertKind = ["failed", "warning", "notice"].includes(kind) ? kind : "warning";
    alert.className = `shell alert ${alertKind}`;
    alert.setAttribute("role", alertKind === "notice" ? "status" : "alert");
    const icon = alert.querySelector(".alert-icon");
    if (icon) icon.textContent = alertKind === "notice" ? "i" : "!";
    $("alertTitle").textContent = title;
    $("alertDetail").textContent = detail;
    alert.hidden = false;
  }

  function hideAlert() { $("systemAlert").hidden = true; }

  function reportAgeHours(report) {
    const generated = new Date(report?.generatedAt).valueOf();
    return Number.isFinite(generated) ? (Date.now() - generated) / 3_600_000 : Infinity;
  }

  function chinaEditionClock(value = new Date()) { return publication.clock(value); }

  function renderEditionHealth(report, label, historical = false, failed = false) {
    const date = report?.editionDate || (report?.generatedAt ? chinaEditionClock(new Date(report.generatedAt)).date : "");
    const health = publication.health({editionDate: date, historical, failed});
    const badge = $("dataState");
    badge.className = "state-badge";
    badge.textContent = health.label;
    if (health.kind === "current") return false;
    if (health.kind === "failed") {
      badge.classList.add("failed");
      showAlert("failed", `${label}更新失败`, `当前保留 ${date || "上一次"} 的内容，稍后刷新可重试。`);
    } else if (health.overdue) {
      badge.classList.add("warning");
      showAlert("warning", `今日${label}尚未更新`, `北京时间已过 08:00，当前版本为 ${date || "未知"}。正在等待当天内容。`);
    } else { hideAlert(); }
    return true;
  }

  function updateHealth(report) {
    const badge = $("dataState");
    badge.className = "state-badge";
    if (state.view === "history" && state.currentReport) {
      renderEditionHealth(state.currentReport, "日报", true);
      return;
    }
    if (state.pipelineStatus?.state === "failed") {
      renderEditionHealth(report, "日报", false, true);
      return;
    }
    if (state.latestLoadError) {
      badge.textContent = state.usingCache ? "本机缓存" : "读取失败";
      badge.classList.add("failed");
      showAlert("failed", "无法读取生产日报", state.usingCache
        ? `当前展示的是上次成功读取的真实日报。错误：${state.latestLoadError}`
        : `页面没有启用任何样例回退，且本机没有可用缓存。错误：${state.latestLoadError}`);
      return;
    }
    if (renderEditionHealth(report, "日报", false, state.pipelineStatus?.state === "failed")) return;
    if (report?.coverageStatus === 'insufficient') {
      badge.textContent = '合格候选不足';
      badge.classList.add('warning');
      showAlert('notice', '本期按实际合格数量刊发', `当前有 ${report.items.length} 条合格独立事件，未补入不合格稿件。`);
      return;
    }
    if (report?.items?.length !== 10) {
      badge.textContent = "数量异常";
      badge.classList.add("warning");
      showAlert("warning", "日报条目数量异常", `生产日报应包含 10 条新闻，当前读取到 ${report?.items?.length || 0} 条。`);
      return;
    }
    const warnings = Array.isArray(state.pipelineStatus?.warnings) ? state.pipelineStatus.warnings.filter(Boolean) : [];
    const translationWarnings = [
      ...(Array.isArray(report?.translationWarnings) ? report.translationWarnings : state.pipelineStatus?.translationWarnings || []),
      batchDiagnosticWarning(report?.translationDiagnostics || state.pipelineStatus?.translationDiagnostics, "日报"),
    ].filter(Boolean);
    const translationStatus = clean(report?.translationStatus || state.pipelineStatus?.translationStatus);
    const translatedItemCount = Number(report?.translatedItemCount ?? state.pipelineStatus?.translatedItemCount) || 0;
    if (["partial", "failed"].includes(translationStatus)) {
      badge.textContent = translationStatus === "partial" ? "部分中文" : "翻译失败";
      badge.classList.add("warning");
      showAlert(
        "warning",
        translationStatus === "partial" ? "日报已更新，但部分中文翻译失败" : "日报已更新，但中文翻译失败",
        [...new Set(translationWarnings)].join("；") || `已完成 ${translatedItemCount} 条中文翻译，其余条目保留原文链接与翻译状态。`,
      );
      return;
    }
    const deepreadState=state.pipelineStatus?.deepread;
    if (deepreadState && deepreadState.editionDate===report?.editionDate && deepreadState.state!=='ok') {
      badge.textContent='日报已更新';
      if (deepreadState.readerStatus==='partial') {
        showAlert('notice', '日报已更新，深读合格主题已发布', '可进入每日深读阅读已通过校对的解读，页面已标注本期内容的完整程度。');
      } else if (deepreadState.readerStatus==='brief') {
        showAlert('notice', '日报已更新，深读暂为简讯', '深读正文尚未就绪，已提供有来源的当日中文简讯。');
      } else {
        const retained=deepreadState.readerStatus==='retained'
          || (!deepreadState.readerStatus && deepreadState.state==='degraded');
        showAlert('warning', '日报已更新，深读生成失败', deepreadFailureDetail(deepreadState)
          +(retained ? `可阅读 ${deepreadState.contentEditionDate} 的历史完整版。` : '暂无合格深读正文，日报可独立阅读。'));
      }
      return;
    }
    // Ranking diagnostics remain in status.json for operators; readers only
    // see data freshness and language availability above.
    badge.textContent = "今日已更新";
    hideAlert();
  }

  const EVIDENCE_LABELS = {primary: "一手来源", multi: "多源报道", single: "单源报道", opinion: "观点材料"};

  function safeEditorialUrl(value) {
    const safe = safeUrl(value);
    if (!safe) return "";
    const url = new URL(safe);
    const host = url.hostname.toLowerCase();
    const octets = /^\d+\.\d+\.\d+\.\d+$/.test(host) ? host.split(".").map(Number) : null;
    const privateIp = host.startsWith("[") || (octets && (
      octets[0] === 0 || octets[0] === 10 || octets[0] === 127 || octets[0] >= 224
      || (octets[0] === 100 && octets[1] >= 64 && octets[1] <= 127)
      || (octets[0] === 169 && octets[1] === 254)
      || (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31)
      || (octets[0] === 192 && octets[1] === 168)
      || (octets[0] === 198 && [18, 19].includes(octets[1]))));
    return url.username || url.password || host === "localhost" || host.endsWith(".localhost")
      || host.endsWith(".local") || privateIp ? "" : safe;
  }

  const verifiedLegacyDeepreads = new WeakSet();
  const verifiedTopicDeepreads = new WeakSet();

  async function verifyTopicBindings(payload) {
    const records = new Map();
    for (const event of payload.events || []) {
      for (const record of [...(event.evidenceRecords || []), ...(event.history || []).flatMap(h=>h.evidenceRecords || [])]) {
        if (!['body','feed'].includes(record.kind) || !safeEditorialUrl(record.url)
            || typeof record.text !== 'string' || record.text.length < 10 || record.text.length > 600
            || record.text !== record.text.trim() || !Number.isFinite(Date.parse(record.fetchedAt))) return false;
        const bytes = new TextEncoder().encode(record.url+'\n'+record.kind+'\n'+record.text);
        const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
        if (record.evidenceId !== 'evd-'+hash.slice(0,20)) return false;
        records.set(record.evidenceId,record);
      }
    }
    const check = async (text, role, refs, proof) => {
      if (!proof || proof.version !== 1 || proof.verdict !== 'supported'
          || !['openai','deepseek'].includes(proof.provider) || !Array.isArray(refs)
          || !refs.length || refs.length > 3 || new Set(refs).size !== refs.length
          || refs.some(ref=>!records.has(ref))) return false;
      const source = refs.map(ref=>ref+'\t'+records.get(ref).text+'\t'+records.get(ref).url).join('\n');
      const bytes = new TextEncoder().encode(role+'\n'+text+'\n'+source);
      const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
      return proof.binding === hash;
    };
    for (const chapter of payload.chapters || []) {
      const editorial = chapter.editorialCheck;
      const material=[chapter.title,chapter.angle,chapter.newsIds,chapter.blocks.map(b=>
        [b.type,b.newsIds,b.sentences.map(s=>[s.text,s.evidenceIds])])];
      const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(material)));
      const binding=Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('');
      if (!editorial || editorial.version !== 1 || editorial.verdict !== 'ready'
          || !['openai','deepseek'].includes(editorial.provider) || editorial.binding !== binding) return false;
      for (const key of ['title','angle']) {
        if (!await check(chapter[key],'analysis',chapter.framingEvidenceIds,chapter[key+'Check'])) return false;
      }
      for (const block of chapter.blocks || []) {
        if (!Array.isArray(block.sentences) || block.text !== block.sentences.map(s=>s.text).join('')) return false;
        for (const sentence of block.sentences) {
          const role = ['paragraph','background','change'].includes(block.type) ? 'fact' : 'analysis';
          if (!await check(sentence.text,role,sentence.evidenceIds,sentence.semanticCheck)) return false;
        }
      }
    }
    if (payload.chapters?.length) {
      for (const key of ['headline','lead']) {
        if (!await check(payload[key],'analysis',payload.framingEvidenceIds,payload[key+'Check'])) return false;
      }
    }
    return true;
  }

  async function normalizeDeepreadForReader(payload) {
    if (payload?.generationRevision === 13) {
      try { if (await verifyTopicBindings(payload)) verifiedTopicDeepreads.add(payload); } catch (_) { /* fail closed */ }
    }
    if (payload?.schemaVersion === 2 && !payload.readerStatus) {
      try {
        const records = payload.events.flatMap(event=>event.evidenceRecords || []);
        const valid = await Promise.all(records.map(async record=>{
          if (!['body','feed'].includes(record.kind) || !safeEditorialUrl(record.url)
              || typeof record.text!=='string' || record.text.length < 10 || record.text.length > 600
              || record.text!==record.text.trim() || /[<>\x00-\x1f]/.test(record.text)
              || !Number.isFinite(Date.parse(record.fetchedAt)) || !/(?:Z|[+-]\d\d:\d\d)$/.test(record.fetchedAt)) return false;
          const bytes=new TextEncoder().encode(record.url+'\n'+record.kind+'\n'+record.text);
          const digest=await crypto.subtle.digest('SHA-256',bytes);
          const hash=Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('');
          return record.evidenceId==='evd-'+hash.slice(0,20);
        }));
        if (valid.length && valid.every(Boolean)) verifiedLegacyDeepreads.add(payload);
      } catch (_) { /* A malformed archive cannot gain reader completion. */ }
    }
    return normalizeDeepread(payload);
  }

  function normalizeEditorialDeepread(payload) {
    if (payload?.generationRevision === 13) return normalizeTopicDeepread(payload);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(payload.editionDate || "")
        || !Array.isArray(payload.events) || !Array.isArray(payload.chapters)) throw new Error("深读文件格式不完整");
    const archiveOriginal = !payload.readerStatus && (
      (Number(payload.generationRevision) < 12 && !payload.events.some(e=>e.evidenceRecords?.length))
      || (Number(payload.generationRevision) <= 12 && verifiedLegacyDeepreads.has(payload) && editorialLegacyBound(payload,false)));
    const seenEvents = new Set(), seenNews = new Set();
    let filtered = Boolean(payload.contentFiltered);
    const events = payload.events.slice(0, 12).filter((event) => {
      const id = clean(event?.newsId), eventId = clean(event?.eventId);
      if (!id || !eventId || seenEvents.has(eventId) || seenNews.has(id)
          || !isAllowedNewsItem({...event, summary: event?.excerpt})) { filtered = true; return false; }
      seenEvents.add(eventId); seenNews.add(id);
      return true;
    }).map((event) => {
      const historyInput = Array.isArray(event.history) ? event.history : [];
      const history = historyInput.filter((story) =>
        /^\d{4}-\d{2}-\d{2}$/.test(clean(story?.editionDate))
        && clean(story.editionDate) < payload.editionDate && clean(story.newsId) !== clean(event.newsId)
        && isAllowedNewsItem({title: story.title, summary: ""})).map((story) => ({
          editionDate: clean(story.editionDate), newsId: clean(story.newsId),
          title: clean(story.title), source: clean(story.source),
        })).slice(-3);
      if (historyInput.length !== history.length) filtered = true;
      const display = normalizeItem({...event, summary: event.excerpt}, 0);
      return {
        newsId: clean(event.newsId), eventId: clean(event.eventId), title: display.title,
        originalTitle: clean(event.originalTitle),
        excerpt: display.summary, sourceTitle: clean(event.title), sourceExcerpt: clean(event.excerpt),
        summaryEvidenceRefs: event.summaryEvidenceRefs,
        category: clean(event.category), publishedAt: clean(event.publishedAt),
        evidenceLevel: Object.hasOwn(EVIDENCE_LABELS, event.evidenceLevel) ? event.evidenceLevel : "single",
        sources: (Array.isArray(event.sources) ? event.sources : []).map((source) => ({
          name: clean(source?.name, "原报道"), url: safeEditorialUrl(source?.url),
        })).filter((source) => source.url).slice(0, 8),
        image: safeEditorialUrl(event.image), imageSource: clean(event.imageSource), history,
        evidenceRecords: (Array.isArray(event.evidenceRecords) ? event.evidenceRecords : []).slice(0,144)
          .filter((record) => /^evd-[a-f0-9]{20}$/.test(record?.evidenceId) && safeEditorialUrl(record?.url) && clean(record?.text))
          .map((record) => ({evidenceId:record.evidenceId, text:clean(record.text), url:safeEditorialUrl(record.url), fetchedAt:clean(record.fetchedAt)})),
      };
    }).filter((event) => event.sources.length);
    if (events.length !== payload.events.length) filtered = true;
    const byNews = new Map(events.map((event) => [event.newsId, event]));
    const chapters = payload.chapters.slice(0, 6).map((chapter, index) => {
      const declaredNewsIds = Array.isArray(chapter?.newsIds) ? chapter.newsIds : [];
      const newsIds = declaredNewsIds.map((value) => clean(value))
        .filter((id, offset, list) => byNews.has(id) && list.indexOf(id) === offset);
      if (newsIds.length !== declaredNewsIds.length) filtered = true;
      const kind = chapter?.kind === "comparison" && newsIds.length >= 2 && newsIds.length <= 3
        ? "comparison" : "event";
      const blocks = (Array.isArray(chapter?.blocks) ? chapter.blocks : []).filter((block) => {
        const refs = Array.isArray(block?.newsIds) ? block.newsIds.map((value) => clean(value)) : [];
        if (!refs.length || !refs.every((id) => newsIds.includes(id))) { filtered = true; return false; }
        if (block.type === "comparison") {
          if (kind === "comparison" && refs.length === newsIds.length
              && newsIds.every((id) => refs.includes(id)) && clean(block.text)) return true;
          filtered = true; return false;
        }
        return ["paragraph", "change"].includes(block.type) && clean(block.text);
      }).slice(0, 10).map((block) => {
        const refs = block.newsIds.map((value) => clean(value));
        const event = refs.length === 1 ? byNews.get(refs[0]) : null;
        const translatedExcerpt = block.type === "paragraph" && event
          && block.text === event.sourceExcerpt
          && JSON.stringify(block.evidenceIds) === JSON.stringify(event.summaryEvidenceRefs);
        const prose = proseDisplayText(block.displayTranslation, block.text, block.evidenceIds);
        const reader = prose || (translatedExcerpt ? (event.excerpt || (archiveOriginal ? clean(block.text) : '')) : clean(block.text));
        return {type: block.type, text: archiveOriginal || readerTextValid(reader) ? reader : '', newsIds: refs,
          evidenceIds: Array.isArray(block.evidenceIds) ? block.evidenceIds.filter((ref) => /^evd-[a-f0-9]{20}$/.test(ref)) : []};
      });
      const event = newsIds.map((id) => byNews.get(id)).find((member) => chapter?.title === member.sourceTitle);
      const title = event && chapter?.title === event.sourceTitle ? event.title : clean(chapter?.title, "本期进展");
      return {id: `deepread-chapter-${index + 1}`, title,
        angle: clean(chapter?.angle), kind, comparisonKey: kind === "comparison" ? clean(chapter.comparisonKey) : "",
        comparisonNote: kind === "comparison" ? "并列比较不代表事件之间存在因果关系。" : "",
        newsIds, blocks};
    }).filter((chapter) => chapter.newsIds.length);
    if (chapters.length !== payload.chapters.length) filtered = true;
    const retained = new Set(chapters.flatMap((chapter) => chapter.newsIds));
    const usedEvents = events.filter((event) => retained.has(event.newsId));
    const observations = (Array.isArray(payload.observations) ? payload.observations : []).slice(0, 3)
      .map((entry) => {
        const refs = Array.isArray(entry?.newsIds) ? entry.newsIds.map((id) => clean(id)) : [];
        const supports = Array.isArray(entry?.supports) ? entry.supports : [];
        if (!clean(entry?.text) || !refs.length || refs.length > 2
            || refs.some((id) => !retained.has(id)) || new Set(refs).size !== refs.length
            || supports.length !== refs.length || supports.some((support) =>
              !refs.includes(clean(support?.newsId)) || !clean(support?.supportQuote))) {
          filtered = true; return null;
        }
        const prose = proseDisplayText(entry.displayTranslation, entry.text, supports.map(support => support.evidenceId));
        const reader = prose || clean(entry.text);
        return {text: readerTextValid(reader) ? reader : '', newsIds: refs,
          supports: supports.map((support) => ({newsId: clean(support.newsId), supportQuote: clean(support.supportQuote)}))};
      }).filter(Boolean);
    if (filtered && !(archiveOriginal && verifiedLegacyDeepreads.has(payload))) chapters.forEach((chapter) => {
      chapter.title = "本期进展"; chapter.angle = ""; chapter.kind = "event";
      chapter.comparisonKey = ""; chapter.comparisonNote = "";
      chapter.blocks = chapter.newsIds.map((id) => ({type: "paragraph",
        text: byNews.get(id).excerpt || byNews.get(id).title, newsIds: [id]}));
    });
    const readable = !filtered && editorialReaderComplete({headline:payload.headline, lead:payload.lead,
      chapters, events:usedEvents, observations});
    const legacyComplete = !payload.readerStatus && verifiedLegacyDeepreads.has(payload) && readable && editorialLegacyBound(payload);
    const oldRevisionReadable = archiveOriginal && (!filtered || verifiedLegacyDeepreads.has(payload))
      && clean(payload.headline) && usedEvents.length && chapters.length
      && chapters.every(c=>clean(c.title) && c.blocks.length && c.blocks.every(b=>clean(b.text)));
    const legacyReadable = oldRevisionReadable || (!payload.readerStatus && verifiedLegacyDeepreads.has(payload) && !filtered && !legacyComplete
      && readerTextValid(payload.headline) && readerTextValid(payload.lead) && usedEvents.length >= 4
      && chapters.length >= 3 && chapters.every(c=>readerTextValid(c.title) && c.blocks.length
        && c.blocks.every(b=>readerTextValid(b.text) && /[。！？.!?][”"’）)]?$/.test(b.text) && !/(?:…|\.\.\.)$/.test(b.text)))
      && editorialLegacyBound(payload, false));
    return {
      releaseId: clean(payload.releaseId), schemaVersion: 2, editionDate: payload.editionDate, generatedAt: clean(payload.generatedAt),
      generationRevision:Number(payload.generationRevision) || 0,
      historicalOriginalFormat:archiveOriginal,
      readerStatus:clean(payload.readerStatus, legacyComplete ? 'complete' : legacyReadable ? 'legacy' : 'unavailable'),
      publicationEditionDate:clean(payload.publicationEditionDate, payload.editionDate),
      qualityFailures:Array.isArray(payload.qualityFailures) ? payload.qualityFailures : [],
      generationDiagnostics:payload.generationDiagnostics || {},
      headline: filtered ? "今日前沿深读" : clean(payload.headline, "今日前沿深读"),
      lead: filtered ? "" : clean(payload.lead),
      generationStatus: readable ? 'ok' : usedEvents.length < 4 ? "insufficient" : clean(payload.generationStatus, "fallback"),
      contentFiltered: filtered, chapters, events: usedEvents,
      observations: filtered ? [] : observations,
      eventCount: usedEvents.length,
      sourceCount: new Set(usedEvents.flatMap((event) => event.sources.map((source) => source.url))).size,
    };
  }

  function normalizeTopicDeepread(payload) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(payload.editionDate || '') || !Array.isArray(payload.events)
        || !Array.isArray(payload.chapters)) throw new Error('深读文件格式不完整');
    let filtered = !verifiedTopicDeepreads.has(payload);
    const seen = new Set();
    const events = payload.events.slice(0,6).filter(event=> {
      if (!event?.newsId || seen.has(event.newsId) || !isAllowedNewsItem({...event,summary:event.excerpt})) { filtered=true; return false; }
      seen.add(event.newsId); return true;
    }).map(event=> {
      const original = {...event,title:event.sourceTitle || event.title,summary:event.sourceExcerpt || event.excerpt};
      const display = normalizeItem(original,0);
      return {...event,title:display.title,excerpt:display.summary,sourceTitle:original.title,sourceExcerpt:original.summary,
        sources:(event.sources || []).map(s=>({name:clean(s.name),url:safeEditorialUrl(s.url)})).filter(s=>s.url),
        image:safeEditorialUrl(event.image), imageSource:clean(event.imageSource),
        history:(event.history || []).filter(h=>/^\d{4}-\d{2}-\d{2}$/.test(h.editionDate || '') && h.editionDate < payload.editionDate)};
    });
    const ids = new Set(events.map(e=>e.newsId));
    const chapters = payload.chapters.slice(0,3).filter(chapter=> {
      if (!Array.isArray(chapter.newsIds) || !chapter.newsIds.length || chapter.newsIds.some(id=>!ids.has(id))
          || !readerTextValid(chapter.title) || !readerTextValid(chapter.angle)
          || !Array.isArray(chapter.blocks) || chapter.blocks.length < 3
          || chapter.blocks.some(b=>!readerTextValid(b.text))) { filtered=true; return false; }
      return true;
    }).map((chapter,i)=>({...chapter,id:'deepread-chapter-'+(i+1)}));
    const briefs = (payload.briefs || []).filter(b=>readerTextValid(b.title) && b.newsIds?.every(id=>ids.has(id)))
      .map(b=>({...b,title:clean(b.title),sources:(b.sources || []).map(s=>({name:clean(s.name),url:safeEditorialUrl(s.url)})).filter(s=>s.url)}));
    let status = ['complete','partial','brief','retained','unavailable'].includes(payload.readerStatus) ? payload.readerStatus : 'unavailable';
    if (filtered || (['complete','partial','retained'].includes(status) && !chapters.length)) status='unavailable';
    if (status==='retained') {
      const age=(Date.parse(payload.publicationEditionDate)-Date.parse(payload.editionDate))/86400000;
      if (!(age>=0 && age<=1)) status='unavailable';
    }
    return {...payload,schemaVersion:2,generationRevision:13,readerStatus:status,contentFiltered:filtered,
      headline:clean(payload.headline),lead:clean(payload.lead),chapters:status==='unavailable' ? [] : chapters,
      briefs:status==='unavailable' ? [] : briefs,events,eventCount:events.length,observations:[]};
  }

  function editorialReaderComplete(report) {
    if (!report || report.events?.length < 4 || report.events?.length > 6 || report.chapters?.length < 3
        || !readerTextValid(report.headline) || !readerTextValid(report.lead)
        || ![2,3].includes(report.observations?.length)
        || report.observations.some(o=>!readerTextValid(o.text))) return false;
    const ids=report.chapters.flatMap(c=>c.newsIds), seen=new Set();
    if (ids.length !== report.events.length || new Set(ids).size !== ids.length) return false;
    return report.chapters.every(chapter=>readerTextValid(chapter.title) && readerTextValid(chapter.angle)
      && chapter.blocks.filter(b=>b.type==='paragraph').length >= 2
      && chapter.blocks.every(block=>{
        if (!readerTextValid(block.text) || !/[。！？.!?][”"’）)]?$/.test(block.text) || /(?:…|\.\.\.)$/.test(block.text)) return false;
        if (block.type !== 'paragraph') return true;
        const key=block.text.replace(/[^\p{L}\p{N}_]/gu,'');
        if ((block.text.match(/[\u3400-\u9fff]/g)||[]).length < 30 || seen.has(key)) return false;
        seen.add(key); return true;
      }));
  }

  function editorialLegacyBound(payload, complete = true) {
    const byId=new Map(payload.events.map(e=>[e.newsId,e]));
    if (byId.size !== payload.events.length || new Set(payload.events.map(e=>e.eventId)).size !== byId.size) return false;
    const literal=(text,refs,events)=>{
      if (typeof text!=='string' || !Array.isArray(refs) || !refs.length || new Set(refs).size!==refs.length) return false;
      const records=new Map(events.flatMap(e=>(e?.evidenceRecords||[])
        .filter(r=>e.sources?.some(s=>s.url===r.url)).map(r=>[r.evidenceId,r.text])));
      if (refs.some(ref=>!records.has(ref))) return false;
      const pending=[0], visited=new Set(), claim=text.trim();
      while (pending.length) {
        const start=pending.pop(); if (visited.has(start)) continue; visited.add(start);
        for (const ref of refs) {
          const quote=records.get(ref); if (!claim.startsWith(quote,start)) continue;
          const end=start+quote.length; if (end===claim.length) return true;
          if (claim[end]===' ') pending.push(end+1);
        }
      }
      const normalized=value=>value.replace(/\s+/g,' ').trim().toLowerCase();
      return text.split(/(?<=[。！？])\s*|(?<=[.!?])\s+(?=[A-Z])/).filter(s=>s.trim()).every(sentence=>
        refs.some(ref=>{
          const source=records.get(ref);
          const qualifiers=[/计划|拟|将|可能|\b(?:plans?|planned|will|scheduled|expected|may|might|could)\b/i,
            /仅|只|有限|限制|\b(?:only|limited)\b/i, /模拟|仿真|\b(?:simulation|simulated)\b/i,
            /初步|\bpreliminary\b/i, /部分|少数|\b(?:some|partial)\b/i,
            /并不|并非|尚未|并未|没有|未能|失败|不支持|\b(?:not|never|failed|unsuccessful)\b/i];
          return normalized(source).includes(normalized(sentence).replace(/[。！？.!?]+$/,''))
            && qualifiers.every(pattern=>!pattern.test(source) || pattern.test(sentence));
        }));
    };
    const frame=(text,events,allowed=[])=>allowed.includes(text)
      || literal(text,events.flatMap(e=>e.evidenceRecords.map(r=>r.evidenceId)),events);
    const count=payload.events.length, labels={'ai-agent':'AI 智能体','counter-uas':'反无人机技术',
      'quantum-computing':'量子计算','hypersonic-missile':'高超音速导弹','semiconductor-fabrication':'芯片制造',
      'robotaxi':'自动驾驶出租车','fusion':'核聚变','perovskite':'钙钛矿'};
    const note='并列比较不代表事件之间存在因果关系。';
    if (!frame(payload.headline,payload.events,[...payload.events.map(e=>e.title),`每日深读｜${payload.editionDate}：${count}项值得追踪的进展`])
        || !frame(payload.lead,payload.events,[`本期从过去24小时的${payload.candidateCount}项合格候选中，选取${count}项有来源的报道，按具体进展展开。`])) return false;
    if (payload.events.some(e=>typeof e.originalTitle!=='string'
      || (e.title!==e.originalTitle && !literal(e.title,['headline'],[{sources:e.sources,
        evidenceRecords:[{evidenceId:'headline',text:e.originalTitle,url:e.sources?.[0]?.url}]}]))
      || !literal(e.excerpt,e.summaryEvidenceRefs,[e]))) return false;
    const references=payload.chapters.flatMap(c=>c.newsIds || []);
    if (references.length!==count || new Set(references).size!==count || references.some(id=>!byId.has(id))) return false;
    if (payload.chapters.some(c=>{
      const events=c.newsIds.map(id=>byId.get(id)), label=labels[c.comparisonKey], amount={2:'两',3:'三'}[events.length];
      const comparison=c.kind==='comparison' && label && amount;
      if (!frame(c.title,events,[...events.map(e=>e.title),...(comparison ? [`${label}：${amount}项独立进展`] : [])])
          || !frame(c.angle,events,[comparison ? `分别核对${amount}项报道在${label}上披露的事实与未知事项` : '追踪本次报道中的具体变化'])) return true;
      return (complete && new Set(c.blocks.filter(b=>b.type==='paragraph').map(b=>clean(b.text))).size < 2)
        || c.blocks.some(b=>{
          if (!b.newsIds?.length || b.newsIds.some(id=>!c.newsIds.includes(id))) return true;
          const members=b.newsIds.map(id=>byId.get(id));
          const allRefs=members.flatMap(e=>e.evidenceRecords.map(r=>r.evidenceId));
          const method=`本章按${label || ''}并列呈现以上原文证据。${note}`;
          const fixed=b.type==='comparison' && comparison && b.text===method
            && b.newsIds.length===events.length && Array.isArray(b.evidenceIds)
            && new Set(b.evidenceIds).size===new Set(allRefs).size && allRefs.every(id=>b.evidenceIds.includes(id));
          return !(fixed || literal(b.text,b.evidenceIds,members));
        });
    })) return false;
    return (payload.observations||[]).every(o=>o.supports?.length && o.supports.every(s=>{
      const event=byId.get(s.newsId), record=event?.evidenceRecords?.find(r=>r.evidenceId===s.evidenceId);
      return record && clean(s.supportQuote) && record.text.includes(s.supportQuote)
        && literal(o.text,o.supports.map(s=>s.evidenceId),o.newsIds.map(id=>byId.get(id)));
    }));
  }

  function deepreadFailureDetail(report) {
    const labels={'source-trace-invalid':'来源或译文核验未通过', 'event-or-chapter-count':'事件或章节数量不足',
      'chapter-needs-two-paragraphs':'章节正文不完整', 'reader-observation-invalid':'观察内容未通过校验',
      'reader-prose-invalid-or-truncated':'正文含未完成的句子或无效译文',
      'reader-paragraph-short-or-repeated':'正文段落过短或重复', 'reader-heading-invalid':'章节标题未完成中文校验'};
    const reasons=(report?.qualityFailures||[]).map(code=>labels[code]).filter(Boolean);
    return reasons.length ? [...new Set(reasons)].join('；')+'。' : '本期深读未通过正文与来源校验，稍后可重试。';
  }

  function normalizeDeepread(payload) {
    if (payload?.schemaVersion === 2) return normalizeEditorialDeepread(payload);
    if (!payload || payload.schemaVersion !== 1 || !Array.isArray(payload.sections)
        || !/^\d{4}-\d{2}-\d{2}$/.test(payload.editionDate || "")) throw new Error("深读文件格式不完整");
    const seen = new Set();
    let filtered = Boolean(payload.contentFiltered);
    const sections = payload.sections.slice(0, 15).map((section, index) => {
      const events = (Array.isArray(section?.events) ? section.events : []).filter((event) => {
        if (!event || !clean(event.newsId) || !clean(event.eventId) || !isAllowedNewsItem(event)
            || seen.has(event.eventId) || seen.size >= 15) { filtered = true; return false; }
        seen.add(event.eventId);
        return true;
      }).map((event) => ({
        newsId: clean(event.newsId), eventId: clean(event.eventId), title: clean(event.title),
        summary: clean(event.summary), analysis: clean(event.analysis), watchFor: clean(event.watchFor),
        category: clean(event.category), publishedAt: clean(event.publishedAt),
        sources: (Array.isArray(event.sources) ? event.sources : []).map((source) => ({
          name: clean(source?.name, "原文"), url: safeUrl(source?.url),
        })).filter((source) => source.url).slice(0, 8),
        image: safeUrl(event.image), imageSource: clean(event.imageSource),
      }));
      return {id: `deepread-section-${index + 1}`, title: clean(section?.title, "今日进展"),
        overview: clean(section?.overview), events};
    }).filter((section) => section.events.length);
    if (filtered) sections.forEach((section) => { section.overview = ""; section.title = "本期进展"; });
    const allEvents = sections.flatMap((section) => section.events);
    return {
      schemaVersion: 1, editionDate: payload.editionDate, generatedAt: clean(payload.generatedAt),
      headline: filtered ? "今日前沿深读" : clean(payload.headline, "今日前沿深读"),
      introduction: filtered ? "" : clean(payload.introduction),
      conclusion: filtered ? "" : clean(payload.conclusion),
      generationStatus: allEvents.length < 10 ? "insufficient" : clean(payload.generationStatus, "fallback"),
      contentFiltered: filtered, sections, eventCount: allEvents.length,
      sourceCount: new Set(allEvents.flatMap((event) => event.sources.map((source) => source.name))).size,
    };
  }

  function renderRawEvidence(block, members) {
    const refs = new Set(block.evidenceIds || []);
    const records = new Map(members.flatMap((event) => event.evidenceRecords || [])
      .filter((record) => refs.has(record.evidenceId)).map((record) => [record.evidenceId, record]));
    if (!records.size) return "";
    return `<details class="deepread-evidence"><summary>原文依据 · ${records.size} 段</summary><ul>${[...records.values()].map((record) =>
      `<li data-evidence-id="${esc(record.evidenceId)}"><blockquote>${esc(record.text)}</blockquote>
       <a href="${esc(record.url)}" target="_blank" rel="noopener noreferrer">查看原文</a>
       <small>抓取 ${esc(formatDate(record.fetchedAt))}</small></li>`).join("")}</ul></details>`;
  }

  function renderEditorialDeepread(report) {
    if (report?.generationRevision === 13) return renderTopicContent(report);
    if (report?.readerStatus === 'legacy' && state.historicalSelection) return renderEditorialContent(report);
    if (!['complete','retained'].includes(report?.readerStatus) || report?.generationStatus !== 'ok'
        || report?.contentFiltered || !editorialReaderComplete(report)) {
      return `<div class="empty"><h2>本期深读生成失败</h2><p>${esc(deepreadFailureDetail(report))}日报可独立阅读。</p></div>`;
    }
    return renderEditorialContent(report);
  }

  function renderEditorialContent(report) {
    if (!report?.chapters?.length) return '<div class="empty"><h2>这期深读尚未发布</h2><p>请选择已有日期，或在日报更新后回来阅读。</p></div>';
    const byNews = new Map(report.events.map((event) => [event.newsId, event]));
    const length = [report.lead, ...report.chapters.flatMap((chapter) => chapter.blocks.map((block) => block.text))].join("").length;
    const minutes = Math.max(2, Math.round(length / 450));
    return `<div class="deepread-layout">
      <aside class="deepread-toc"><p class="eyebrow">IN THIS EDITION</p><b>本期阅读</b>
        <ol>${report.chapters.map((chapter) => `<li><a href="#${esc(chapter.id)}">${esc(chapter.title)}</a></li>`).join("")}</ol>
        <p>${report.eventCount} 项核心进展 · 约 ${minutes} 分钟</p>
        <p class="deepread-evidence-guide">证据标签说明材料来源类型，不代表所有细节已经独立核实。</p>
      </aside>
      <article class="deepread-article deepread-editorial">
        <header class="deepread-header"><p class="eyebrow">${esc(report.editionDate)} · FRONTIER PULSE</p>
          <h2>${esc(report.headline)}</h2>
          ${report.lead ? `<p class="deepread-lead">${esc(report.lead)}</p>` : ""}
          ${report.readerStatus === 'retained' ? `<p class="deepread-note deepread-retained-note">今日深读未更新，以下为 ${esc(report.editionDate)} 内容。</p>` : ""}
          ${report.readerStatus === 'legacy' ? '<p class="deepread-note">历史简版 · 按发布时的内容与语言保留，未按现行深读标准重新生成。</p>' : ''}
        </header>
        ${report.chapters.map((chapter) => {
          const members = chapter.newsIds.map((id) => byNews.get(id)).filter(Boolean);
          const illustrated = members.find((event) => event.image);
          return `<section class="deepread-chapter" id="${esc(chapter.id)}">
            <h2>${esc(chapter.title)}</h2>
            ${chapter.kind === "comparison" ? `<p class="deepread-comparison-note">${esc(chapter.comparisonNote)}</p>` : ""}
            ${illustrated ? `<figure class="deepread-figure"><img src="${esc(illustrated.image)}" alt="${esc(illustrated.title)}" loading="lazy" decoding="async" referrerpolicy="no-referrer"><figcaption>原文配图 · 图片来源：${esc(illustrated.imageSource || illustrated.sources[0]?.name || "原报道")}</figcaption></figure>` : ""}
            ${chapter.blocks.map((block) => `<p class="${block.type === "change" ? "deepread-change" : block.type === "comparison" ? "deepread-comparison" : "deepread-paragraph"}">${esc(block.text)}</p>${renderRawEvidence(block, members)}`).join("")}
            <div class="deepread-source-list"><b>本节资料</b>${members.map((event) => `<div class="deepread-source-row">
              <span class="deepread-evidence-tag">${EVIDENCE_LABELS[event.evidenceLevel]}</span>
              <span>${esc(event.title)}</span>
              ${event.sources.map((source) => `<a href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">${esc(source.name)} ↗</a>`).join("")}
              ${event.history.length ? `<small>前次记录：${event.history.map((story) => `<a href="?view=history&amp;date=${esc(story.editionDate)}">${esc(story.editionDate)}</a>`).join("、")}</small>` : ""}
            </div>`).join("")}</div>
          </section>`;
        }).join("")}
        ${report.observations?.length ? `<section class="deepread-observations" aria-label="今日观察">
          <h2>今日观察</h2><ol>${report.observations.map((entry) => `<li><p>${esc(entry.text)}</p>
            <small>依据：${entry.newsIds.map((id) => {
              const event = byNews.get(id), source = event?.sources[0];
              return source ? `<a href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">${esc(event.title)} ↗</a>` : "";
            }).join(" · ")}</small></li>`).join("")}</ol></section>` : ""}
      </article>
    </div>`;
  }

  function renderTopicContent(report) {
    if (report.contentFiltered || report.readerStatus==='unavailable') return `<div class="empty"><h2>本期深读暂未完成</h2><p>${esc(deepreadFailureDetail(report))}可先阅读今日简报。</p></div>`;
    const byNews = new Map(report.events.map(e=>[e.newsId,e]));
    const length = report.chapters.flatMap(c=>c.blocks.map(b=>b.text)).join('').length;
    const image = (report.chapters[0]?.newsIds || []).map(id=>byNews.get(id)).find(e=>e?.image);
    const partial = report.chapters.length < (report.topicPlan?.length || report.chapters.length);
    return `<div class="deepread-layout"><aside class="deepread-toc"><p class="eyebrow">IN THIS EDITION</p><b>本期阅读</b>
      <ol>${report.chapters.map(c=>`<li><a href="#${esc(c.id)}">${esc(c.title)}</a></li>`).join('')}</ol>
      <p>${report.chapters.length} 个主题${length ? ` · 约 ${Math.max(2,Math.round(length/450))} 分钟` : ''}</p>
      </aside><article class="deepread-article deepread-editorial deepread-topics">
      <header class="deepread-header"><p class="eyebrow">${esc(report.publicationEditionDate || report.editionDate)} · FRONTIER PULSE</p>
      ${report.readerStatus==='retained' ? `<p class="deepread-retained-note">今日深读未更新，以下为 ${esc(report.editionDate)} 内容。</p>` : ''}
      <h2>${esc(report.headline)}</h2>${report.lead ? `<p class="deepread-lead">${esc(report.lead)}</p>` : ''}
      ${report.readerStatus==='partial' ? `<p class="deepread-note">${partial ? '合格主题已先行发布，其余主题待恢复。' : '本期先发布有依据的解读，篇幅尚未达到完整版目标。'}</p>` : ''}
      ${report.readerStatus==='brief' ? '<p class="deepread-note">今日深读正文尚未完成，以下为当日中文简讯。</p>' : ''}</header>
      ${image && report.chapters.length ? `<figure class="deepread-figure deepread-hero"><img src="${esc(image.image)}" alt="${esc(image.title)}" loading="lazy" referrerpolicy="no-referrer"><figcaption>图片来源：${esc(image.imageSource || image.sources[0]?.name)}</figcaption></figure>` : ''}
      ${report.chapters.map((chapter,index)=> {
        const members = chapter.newsIds.map(id=>byNews.get(id)).filter(Boolean);
        const cited = [...new Set(chapter.blocks.flatMap(b=>b.sentences.flatMap(s=>s.evidenceIds)))];
        const records = new Map(members.flatMap(e=>[...(e.evidenceRecords || []),...(e.history || []).flatMap(h=>(h.evidenceRecords || []).map(r=>({...r,editionDate:h.editionDate})))])
          .map(r=>[r.evidenceId,r]));
        const target = ref=>`cite-${index+1}-${cited.indexOf(ref)+1}`;
        let analysisLabel = false;
        return `<section class="deepread-chapter" id="${esc(chapter.id)}"><h2>${esc(chapter.title)}</h2>
          ${chapter.comparisonNote ? `<p class="deepread-comparison-note">${esc(chapter.comparisonNote)}</p>` : ''}
          ${chapter.blocks.map(block=> {
            const analysis = ['analysis','comparison','watch'].includes(block.type);
            const label = analysis && !analysisLabel; if (analysis) analysisLabel=true;
            return `${label ? '<p class="deepread-analysis-label">编辑分析</p>' : ''}<p class="deepread-paragraph${analysis ? ' deepread-editor-analysis' : ''}${block.type==='change' ? ' deepread-change' : ''}">${block.sentences.map(s=>
              esc(s.text)+`<sup class="deepread-ref">${s.evidenceIds.map(ref=>`<a href="#${esc(target(ref))}" data-evidence-target="${esc(target(ref))}" aria-label="查看原文证据 ${cited.indexOf(ref)+1}">[${cited.indexOf(ref)+1}]</a>`).join('')}</sup>`).join('')}</p>`;
          }).join('')}
          <div class="deepread-source-list"><b>本节来源</b>${members.map(e=>`<div class="deepread-source-row"><span class="deepread-evidence-tag">${EVIDENCE_LABELS[e.evidenceLevel] || '单源报道'}</span>
          ${index>0 && e.image ? `<img class="deepread-source-thumb" src="${esc(e.image)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ''}
          ${e.sources.map(s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.name)} ↗</a>`).join('')}
          ${(e.history || []).length ? `<small>此前材料：${e.history.map(h=>`<a href="?view=deepread&amp;date=${esc(h.editionDate)}">${esc(h.editionDate)}</a>`).join('、')}</small>` : ''}</div>`).join('')}</div>
          <details class="deepread-footnotes"><summary>原文证据 · ${cited.length} 条</summary><ol>${cited.map(ref=> {
            const record=records.get(ref); return record ? `<li id="${esc(target(ref))}">${record.editionDate ? `<small>背景材料 · ${esc(record.editionDate)}</small>` : ''}
              <blockquote>${esc(record.text)}</blockquote><a href="${esc(record.url)}" target="_blank" rel="noopener noreferrer">查看原报道 ↗</a></li>` : '';
          }).join('')}</ol></details></section>`;
      }).join('')}
      ${report.briefs?.length ? `<section class="deepread-briefs"><h2>待恢复主题的简讯</h2><ul>${report.briefs.map(b=>`<li>${esc(b.title)} ${b.sources.map(s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.name)} ↗</a>`).join(' · ')}</li>`).join('')}</ul></section>` : ''}
      </article></div>`;
  }

  function renderDeepreadArticle(report) {
    if (report?.schemaVersion === 2) return renderEditorialDeepread(report);
    if (!report?.sections?.length) return '<div class="empty"><h2>这期深读尚未发布</h2><p>请选择已有日期，或在日报更新后回来阅读。</p></div>';
    const events = report.sections.flatMap((section) => section.events);
    const length = [report.introduction, report.conclusion, ...report.sections.map((section) => section.overview),
      ...events.flatMap((event) => [event.summary, event.analysis])].join("").length;
    const minutes = Math.max(2, Math.round(length / 450));
    let number = 0;
    return `<div class="deepread-layout">
      <aside class="deepread-toc"><p class="eyebrow">IN THIS EDITION</p><b>本期阅读</b>
        <ol>${report.sections.map((section) => `<li><a href="#${esc(section.id)}">${esc(section.title)}</a><span>${section.events.length} 项进展</span></li>`).join("")}</ol>
        <p>${report.eventCount} 项事件 · ${report.sourceCount} 个来源<br>约 ${minutes} 分钟</p>
      </aside>
      <article class="deepread-article">
        <header class="deepread-header"><p class="eyebrow">${esc(report.editionDate)} · FRONTIER PULSE</p>
          <h2>${esc(report.headline)}</h2>
          ${report.introduction ? `<p class="deepread-lead">${esc(report.introduction)}</p>` : ""}
          ${report.generationStatus === "insufficient" ? `<p class="deepread-note">本期收录 ${report.eventCount} 项可用事件，后续随日报更新。</p>` : ""}
        </header>
        ${report.sections.map((section) => `<section class="deepread-chapter" id="${esc(section.id)}">
          <h2>${esc(section.title)}</h2>${section.overview ? `<p class="deepread-overview">${esc(section.overview)}</p>` : ""}
          ${section.events.map((event) => `<section class="deepread-event" id="deepread-event-${++number}">
            <p class="deepread-kicker">${String(number).padStart(2, "0")} / ${esc(event.category)}</p>
            <h3>${esc(event.title)}</h3>
            ${event.image ? `<figure class="deepread-figure"><img src="${esc(event.image)}" alt="${esc(event.title)}" loading="lazy" decoding="async" referrerpolicy="no-referrer"><figcaption>原文配图 · 图片来源：${esc(event.imageSource || event.sources[0]?.name || "原报道")}</figcaption></figure>` : ""}
            <p>${esc(event.summary)}</p>
            ${event.analysis ? `<p class="deepread-analysis">${esc(event.analysis)}</p>` : ""}
            ${event.watchFor ? `<p class="deepread-watch"><b>后续关注</b> ${esc(event.watchFor)}</p>` : ""}
            <div class="deepread-citations"><span>报道来源</span>${event.sources.map((source) => `<a href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">${esc(source.name)} ↗</a>`).join("")}</div>
          </section>`).join("")}
        </section>`).join("")}
        ${report.conclusion ? `<footer class="deepread-conclusion"><p class="eyebrow">LOOKING AHEAD</p><h2>接下来，观察什么</h2><p>${esc(report.conclusion)}</p></footer>` : ""}
      </article>
    </div>`;
  }

  async function loadDeepread(date = "", bypassCache = false) {
    const request = ++state.deepreadRequest;
    state.deepreadLoadError = "";
    if (date && !/^\d{4}-\d{2}-\d{2}$/.test(date)) { state.deepreadReport = null; state.deepreadLoadError = "日期无效"; return; }
    const indexPromise = (state.deepreadIndex && !bypassCache) ? Promise.resolve() :
      fetchPublicationJson(ENDPOINTS.deepreadIndex, bypassCache).then((index) => {
        if (request === state.deepreadRequest) state.deepreadIndex = index;
      }).catch(() => {});
    try {
      const currentPublication = releaseManifest?.editionDate || state.latestReport?.editionDate
        || state.deepreadReport?.publicationEditionDate;
      const latest = !date || date === currentPublication;
      const report = !bypassCache && date && state.deepreadCache.has(date)
        ? state.deepreadCache.get(date)
        : await normalizeDeepreadForReader(await fetchPublicationJson(latest ? ENDPOINTS.deepread : `./data/deepread/${date}.json`, bypassCache));
      if (date && (latest ? (report.publicationEditionDate || report.editionDate) : report.editionDate) !== date) throw new Error("返回了不同日期的深读");
      if (request !== state.deepreadRequest) return;
      state.deepreadReport = report;
      state.deepreadCache.set(latest ? (report.publicationEditionDate || report.editionDate) : report.editionDate, report);
      if (latest) writeStorage(publicationCacheKey(DEEPREAD_CACHE_KEY), report);
    } catch (error) {
      if (request !== state.deepreadRequest) return;
      state.deepreadLoadError = clean(error?.message, "暂时无法读取");
      try {
        const cached = await normalizeDeepreadForReader(state.deepreadCache.get(date) || readStorage(publicationCacheKey(DEEPREAD_CACHE_KEY), null));
        state.deepreadReport = ((!date && publication.accepts(releaseManifest, cached))
          || (date && (cached.publicationEditionDate || cached.editionDate) === date)
          || (date && cached.editionDate === date && cached.readerStatus !== 'retained')) ? cached : null;
      } catch (_) { state.deepreadReport = null; }
    }
    await indexPromise;
  }

  function updateViewHealth() {
    if (state.view === "deepread") {
      const report = state.deepreadReport;
      const badge = $("dataState");
      badge.className = "state-badge";
      if (state.deepreadLoadError) {
        badge.textContent = report ? "深读缓存" : "尚无此期";
        badge.classList.add("warning");
        showAlert("warning", report ? "当前展示已保存的深读" : "这期深读暂时无法读取", report
          ? `版本日期为 ${report.editionDate}，刷新后可重试。`
          : "请选择已有日期，或稍后刷新。每日深读从栏目上线之日起独立归档。");
      } else if (report?.readerStatus === 'retained' && !state.historicalSelection) {
        badge.textContent = '沿用完整版';
        badge.classList.add('warning');
        showAlert('notice', '今日深读未通过内容校验', `最新完整版：${report.editionDate}，正文保留实际内容日期。`);
      } else if (['partial','brief'].includes(report?.readerStatus)) {
        badge.textContent = report.readerStatus==='partial' ? '主题已发布' : '今日简讯';
        badge.classList.add('warning');
        showAlert('notice', '今日深读部分发布', report.readerStatus==='partial' ? '可先阅读已通过校对的解读，页面已标注本期内容的完整程度。' : '深读正文尚未完成，先展示当日中文简讯。');
      } else if (report?.schemaVersion === 2 && report?.readerStatus === 'unavailable') {
        badge.textContent = '深读生成失败';
        badge.classList.add('failed');
        showAlert('failed', '本期深读生成失败', deepreadFailureDetail(report)+'日报可独立阅读。');
      } else if (report?.readerStatus === 'legacy' && state.historicalSelection) {
        badge.textContent = '历史归档';
        badge.classList.add('warning');
        showAlert('notice', '当前阅读旧版深读', `${report.editionDate} 按原发布格式保留，未按现行深读标准重新生成。`);
      } else if (renderEditionHealth(report, "深读", state.historicalSelection, state.pipelineStatus?.state === "failed")) {
        return;
      } else {
        badge.textContent = report?.generationStatus === "insufficient" ? "今日简版" : "今日已更新";
        hideAlert();
      }
      return;
    }
    if (state.view === "stream") {
      const badge = $("dataState");
      badge.className = "state-badge";
      if (state.streamLoadError) {
        badge.textContent = state.streamReport?.items?.length ? "动态缓存" : "动态失败";
        badge.classList.add(state.streamReport?.items?.length ? "warning" : "failed");
        showAlert(state.streamReport?.items?.length ? "warning" : "failed", "全量动态读取异常", state.streamReport?.items?.length
          ? `当前展示上次成功读取的真实动态流。错误：${state.streamLoadError}`
          : `没有可用的全量动态数据。错误：${state.streamLoadError}`);
        return;
      }
      if (state.streamStatus?.state === "failed") {
        badge.textContent = "动态更新失败";
        badge.classList.add("failed");
        showAlert("failed", "最近一次全量动态更新失败", `${state.streamStatus.message || "三小时采集未成功完成"}；当前保留上一版真实动态。`);
        return;
      }
      if (reportAgeHours(state.streamReport) > 7) {
        badge.textContent = "动态已过期";
        badge.classList.add("warning");
        showAlert("warning", "全量动态可能已经过期", `当前动态生成于 ${formatDate(state.streamReport?.generatedAt)}，已超过 7 小时。请检查三小时更新工作流。`);
        return;
      }
      const streamDiagnostics = state.streamReport?.translationDiagnostics || state.streamStatus?.translationDiagnostics;
      const translationWarnings = [
        ...(Array.isArray(state.streamReport?.translationWarnings) ? state.streamReport.translationWarnings : []),
        ...(Array.isArray(state.streamStatus?.translationWarnings) ? state.streamStatus.translationWarnings : []),
        batchDiagnosticWarning(streamDiagnostics, "新闻"),
      ].filter(Boolean);
      if (translationWarnings.length) {
        badge.textContent = "翻译不完整";
        badge.classList.add("warning");
        showAlert("warning", "全量动态已更新，但部分中文翻译失败", [...new Set(translationWarnings)].join("；"));
        return;
      }
      badge.textContent = "动态在线";
      hideAlert();
      return;
    }
    if (state.view === "research") {
      const badge = $("dataState");
      badge.className = "state-badge";
      const items = state.researchReport?.items || [];
      if (state.researchLoadError) {
        badge.textContent = items.length ? "论文缓存" : "论文失败";
        badge.classList.add(items.length ? "warning" : "failed");
        showAlert(items.length ? "warning" : "failed", "论文雷达读取异常", items.length
          ? `当前展示上次成功读取的真实论文数据。错误：${state.researchLoadError}`
          : `没有可用的论文数据。错误：${state.researchLoadError}`);
        return;
      }
      if (!items.length) {
        badge.textContent = "暂无论文";
        badge.classList.add("warning");
        showAlert("warning", "论文雷达暂无条目", "本期未抓取到符合研究方向与时间窗的论文，请检查 arXiv 可用性和研究分类配置。");
        return;
      }
      if (renderEditionHealth(state.researchReport, "论文", false,
        ["failed", "stale"].includes(state.researchReport?.editorialStatus))) return;
      const researchDiagnostics = state.researchReport?.editorialDiagnostics || state.pipelineStatus?.researchEditorialDiagnostics;
      const warnings = [
        ...(Array.isArray(state.researchReport?.warnings) ? state.researchReport.warnings : []),
        ...(Array.isArray(state.pipelineStatus?.researchWarnings) ? state.pipelineStatus.researchWarnings : []),
        batchDiagnosticWarning(researchDiagnostics, "论文"),
      ].filter(Boolean);
      const researchEditorialStatus = state.pipelineStatus?.researchEditorialStatus || state.researchReport?.editorialStatus;
      if (["partial", "fallback", "stale"].includes(researchEditorialStatus) || warnings.length) {
        badge.textContent = researchEditorialStatus === "stale" ? "论文未更新"
          : researchEditorialStatus === "partial" ? "论文部分翻译" : "论文规则版";
        badge.classList.add("warning");
        showAlert("warning", researchEditorialStatus === "partial" ? "论文雷达部分批次未完成翻译" : "论文雷达已降级", [...new Set(warnings)].join("；") || "本期保留论文元数据与原始摘要，未完成 AI 中文编辑。");
        return;
      }
      badge.textContent = "今日已更新";
      hideAlert();
      return;
    }
    updateHealth(state.latestReport);
  }

  function migrateLegacyBookmarks(items) {
    if (!legacyBookmarks.length) return;
    const known = new Set(state.bookmarks.map(itemKey));
    items.filter((item) => legacyBookmarks.includes(item.id)).forEach((item) => {
      if (!known.has(itemKey(item))) state.bookmarks.push({ ...item, _bookmarkKey: itemKey(item) });
    });
    writeStorage(BOOKMARK_KEY, state.bookmarks);
    try { localStorage.removeItem("fp-bookmarks"); } catch (_) { /* ignore */ }
  }

  async function loadPipelineStatus(bypassCache = false) {
    try {
      const status = await fetchJson(ENDPOINTS.status, bypassCache);
      state.pipelineStatus = status && typeof status === "object" ? status : null;
    } catch (_) {
      state.pipelineStatus = null;
    }
  }

  async function loadLatest(showToast = false, bypassCache = false) {
    const owner = state.viewRequest;
    if (state.view === "latest") $("dataState").textContent = "同步中";
    state.latestLoadError = "";
    state.usingCache = false;
    const statusPromise = loadPipelineStatus(bypassCache);
    try {
      const report = normalizeReport(await fetchPublicationJson(ENDPOINTS.latest, bypassCache));
      state.latestReport = report;
      state.editionCache.set(report.editionDate, report);
      writeStorage(publicationCacheKey(CACHE_KEY), report);
      migrateLegacyBookmarks(report.items);
      if (showToast && owner === state.viewRequest && state.view !== "research") toast("已读取最新日报");
    } catch (error) {
      state.latestLoadError = clean(error?.message, "未知错误");
      try {
        state.latestReport = normalizeReport(readStorage(publicationCacheKey(CACHE_KEY), null));
        if (!publication.accepts(releaseManifest, state.latestReport)) throw new Error("日报缓存版本不匹配");
        state.usingCache = true;
      } catch (_) {
        state.latestReport = null;
      }
    }
    await statusPromise;
    if (owner !== state.viewRequest || state.view === "research") return;
    updateHealth(state.latestReport);
    if (state.view === "latest") {
      state.currentReport = state.latestReport;
      state.items = state.latestReport?.items || [];
      state.editionDate = state.latestReport?.editionDate || state.editionDate;
    }
  }

  async function loadStream(showToast = false, bypassCache = false) {
    state.streamLoadError = "";
    try {
      const [payload, status] = await Promise.all([
        fetchJson(ENDPOINTS.stream, bypassCache),
        fetchJson(ENDPOINTS.streamStatus, bypassCache).catch(() => null),
      ]);
      state.streamReport = normalizeCollection(payload, "news");
      state.streamStatus = status && typeof status === "object" ? status : null;
      writeStorage(STREAM_CACHE_KEY, state.streamReport);
      if (showToast) toast(`已读取 ${state.streamReport.items.length} 条全量动态`);
    } catch (error) {
      state.streamLoadError = clean(error?.message, "未知错误");
      try {
        state.streamReport = normalizeCollection(readStorage(STREAM_CACHE_KEY, null), "news");
        showAlert("warning", "全量动态暂时无法更新", `当前展示上次成功读取的动态流。错误：${clean(error?.message, "未知错误")}`);
      } catch (_) {
        state.streamReport = { generatedAt: "", rangeHours: 24, items: [] };
        showAlert("failed", "无法读取全量动态", clean(error?.message, "未知错误"));
      }
    }
    return state.streamReport;
  }

  async function loadResearch(showToast = false, bypassCache = false) {
    state.researchLoadError = "";
    try {
      const payload = await fetchJson(ENDPOINTS.research, bypassCache);
      state.researchReport = normalizeCollection(payload, "paper");
      writeStorage(RESEARCH_CACHE_KEY, state.researchReport);
      if (showToast) toast(`已读取 ${state.researchReport.items.length} 篇论文`);
    } catch (error) {
      state.researchLoadError = clean(error?.message, "未知错误");
      try {
        state.researchReport = normalizeCollection(readStorage(RESEARCH_CACHE_KEY, null), "paper");
        showAlert("warning", "论文雷达暂时无法更新", `当前展示上次成功读取的论文数据。错误：${clean(error?.message, "未知错误")}`);
      } catch (_) {
        state.researchReport = { generatedAt: "", rangeDays: 7, items: [] };
        showAlert("failed", "无法读取论文雷达", clean(error?.message, "未知错误"));
      }
    }
    return state.researchReport;
  }

  async function ensureArchiveIndex(bypassCache = false) {
    if (state.archiveIndex && !bypassCache) return state.archiveIndex;
    try {
      const payload = await fetchPublicationJson(ENDPOINTS.archive, bypassCache);
      const editions = (Array.isArray(payload?.editions) ? payload.editions : [])
        .filter((item) => /^\d{4}-\d{2}-\d{2}$/.test(item?.editionDate || ""))
        .sort((a, b) => b.editionDate.localeCompare(a.editionDate));
      state.archiveIndex = { ...payload, editions };
    } catch (_) {
      state.archiveIndex = { editions: [] };
    }
    return state.archiveIndex;
  }

  async function ensureSearchIndex(bypassCache = false) {
    if (state.searchItems && !bypassCache) return state.searchItems;
    try {
      const payload = await fetchPublicationJson(ENDPOINTS.search, bypassCache);
      state.searchManifest = payload;
      let rawItems = Array.isArray(payload?.items) ? payload.items : [];
      if (Number(payload?.schemaVersion) >= 2 && Array.isArray(payload?.shards)) {
        rawItems = [];
        const shards = payload.shards.filter((shard) => /^\.\/data\/archive\/search-\d{4}-\d{2}\.json$/.test(clean(shard?.file)));
        for (let index = 0; index < shards.length; index += 4) {
          const batch = await Promise.all(shards.slice(index, index + 4).map(async (shard) => {
            const shardPayload = await fetchPublicationJson(shard.file, bypassCache);
            return Array.isArray(shardPayload?.items) ? shardPayload.items : [];
          }));
          rawItems.push(...batch.flat());
        }
      }
      const compactIndex = Number(payload?.schemaVersion) >= 2;
      state.searchItems = rawItems
        .map((item, index) => normalizeItem({ ...item, _compact: compactIndex || item._compact }, index, item.editionDate))
        .slice(0, 10000);
    } catch (_) {
      state.searchItems = state.latestReport?.items || [];
    }
    return state.searchItems;
  }

  function availableDates() {
    if (state.view === "deepread") {
      const dates = new Set((state.deepreadIndex?.editions || []).map((item) => item.editionDate));
      if (state.deepreadReport?.editionDate) dates.add(state.deepreadReport.editionDate);
      if (state.deepreadReport?.publicationEditionDate) dates.add(state.deepreadReport.publicationEditionDate);
      return [...dates].filter((date) => /^\d{4}-\d{2}-\d{2}$/.test(date)).sort().reverse();
    }
    const dates = new Set((state.archiveIndex?.editions || []).map((item) => item.editionDate));
    if (state.latestReport?.editionDate) dates.add(state.latestReport.editionDate);
    return [...dates].sort().reverse();
  }

  async function loadEdition(date, bypassCache = false) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return;
    state.editionDate = date;
    if (date === state.latestReport?.editionDate) {
      state.currentReport = state.latestReport;
      state.items = state.latestReport?.items || [];
      return;
    }
    if (!bypassCache && state.editionCache.has(date)) {
      state.currentReport = state.editionCache.get(date);
      state.items = state.currentReport.items;
      return;
    }
    $("stories").setAttribute("aria-busy", "true");
    $("stories").innerHTML = '<div class="loading"></div>';
    try {
      const report = normalizeReport(await fetchPublicationJson(`./data/archive/${date}.json`, bypassCache));
      state.editionCache.set(date, report);
      state.currentReport = report;
      state.items = report.items;
    } catch (error) {
      state.currentReport = null;
      state.items = [];
      showAlert("failed", "无法读取所选归档", `${date} 的归档文件不可用：${clean(error?.message, "未知错误")}`);
    }
  }

  function syncUrl() {
    const query = new URLSearchParams();
    if (state.view !== "latest") query.set("view", state.view);
    if (["history", "deepread"].includes(state.view) && state.editionDate) query.set("date", state.editionDate);
    if (state.view === "stream" && state.rangeHours !== 24) query.set("range", String(state.rangeHours));
    if (state.view === "stream" && state.source !== "全部") query.set("source", state.source);
    if (state.view === "research" && state.researchScope === "mine" && state.researchKeywords.length) query.set("scope", "mine");
    if (state.query && state.view !== "deepread") query.set("q", state.query);
    if (initialRelease) query.set('release', initialRelease);
    const suffix = query.toString();
    history.replaceState(null, "", `${location.pathname}${suffix ? `?${suffix}` : ""}${location.hash || ""}`);
  }

  function applyTheme(theme, persist = false) {
    state.theme = theme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = state.theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", state.theme === "dark" ? "#0b151b" : "#102a38");
    const button = $("themeBtn");
    if (button) {
      button.textContent = state.theme === "dark" ? "☀" : "◐";
      button.title = state.theme === "dark" ? "切换浅色模式" : "切换深色模式";
      button.setAttribute("aria-label", button.title);
    }
    if (persist) writeStorage(THEME_KEY, state.theme);
  }

  function renderViewCopy() {
    const copy = {
      latest: ["DAILY BRIEF", "今日前沿态势", "科技 · AI · 航空航天 · 安全 · 前沿研究", "TOP 10", "今日 Top 10"],
      deepread: ["THE DAILY READ", "每日深读", "读懂今日进展，连接事实与趋势", "DAILY READ", "每日深读"],
      stream: ["FULL STREAM", `过去 ${state.rangeHours} 小时`, "全量合格动态", "STREAM", "全量动态"],
      research: ["DAILY CLASSICS", "每日经典论文", "", "CLASSICS", "当日推荐"],
      history: ["ARCHIVE", "历史脉络", state.query ? "跨日期检索" : "按日期回看", "ARCHIVE", state.query ? "跨日期搜索" : "历史要闻"],
      bookmarks: ["COLLECTION", "我的收藏", "仅保存在当前浏览器", "SAVED", "收藏新闻"],
      watchlist: ["WATCHLIST", "关注词", "从历史索引中追踪持续信号", "SIGNALS", "关注词命中"],
    }[state.view];
    $("viewEyebrow").textContent = copy[0];
    $("viewTitle").textContent = copy[1];
    $("viewDescription").textContent = copy[2];
    $("viewDescription").hidden = !copy[2];
    $("feedEyebrow").textContent = copy[3];
    $("feedTitle").textContent = copy[4];
    $("watchPanel").hidden = state.view !== "watchlist";
    $("spotlightSection").hidden = state.view !== "latest";
    $("classicSection").hidden = state.view !== "research";
    $("classicBookmarks").hidden = state.view !== "bookmarks";
    $("rangeControls").hidden = state.view !== "stream";
    $("sourceFilterWrap").hidden = state.view !== "stream";
    $("deepreadSection").hidden = state.view !== "deepread";
    $("briefSection").hidden = ["deepread", "research"].includes(state.view);
    $("feedSection").hidden = ["deepread", "research"].includes(state.view);
    $("searchWrap").hidden = ["deepread", "research"].includes(state.view);
    $("search").placeholder = state.view === "research" ? "搜索论文、作者、摘要…" : "搜索标题、摘要、来源…";
    document.querySelectorAll("[data-range]").forEach((button) => {
      button.classList.toggle("active", Number(button.dataset.range) === state.rangeHours);
      button.setAttribute("aria-pressed", String(Number(button.dataset.range) === state.rangeHours));
    });
    document.querySelectorAll("[data-view]").forEach((button) => {
      button.classList.toggle("active", button.dataset.view === state.view && button.closest("nav"));
      if (button.closest("nav")) button.setAttribute("aria-current", button.dataset.view === state.view ? "page" : "false");
    });
  }

  function renderDateControl() {
    const control = $("dateControl");
    control.hidden = !["latest", "history", "deepread"].includes(state.view);
    if (control.hidden) return;
    const dates = availableDates();
    const current = state.editionDate || state.latestReport?.editionDate || dates[0] || "";
    const report = state.currentReport || state.latestReport;
    $("editionTimezone").textContent = editionTimezoneLabel(report?.timezone || state.archiveIndex?.timezone);
    const input = $("editionPicker");
    input.value = current;
    if (dates.length) {
      input.min = dates[dates.length - 1];
      input.max = dates[0];
    }
    const index = dates.indexOf(current);
    $("previousEdition").disabled = index < 0 || index >= dates.length - 1;
    $("nextEdition").disabled = index <= 0;
    $("previousEdition").dataset.date = index >= 0 ? dates[index + 1] || "" : "";
    $("nextEdition").dataset.date = index > 0 ? dates[index - 1] || "" : "";
    $("editionHint").textContent = dates.length ? `已有 ${dates.length} 期可浏览` : "归档将在下一次成功更新后建立";
  }

  function uniqueSourceCount(items) {
    return new Set(items.flatMap((item) => item.sources.map((source) => source.evidenceGroup || source.domain || source.name))).size;
  }

  function valueCounts(items, getter) {
    const counts = Object.create(null);
    items.forEach((item) => {
      const key = clean(getter(item), "其他");
      counts[key] = (counts[key] || 0) + 1;
    });
    return counts;
  }

  function providerLabel(report) {
    const provider = clean(report?.translationProvider || report?.editorialProvider).toLocaleLowerCase();
    if (provider === "deepseek") return "DeepSeek V4 Flash";
    if (provider === "openai") return "OpenAI";
    return "";
  }

  function selectionLabel(report) {
    const method = clean(report?.selectionMethod || report?.method).toLocaleLowerCase();
    const constrained = report?.selectionStrategy === "ai-ranked-rule-constrained";
    if (method === "deepseek") return constrained ? "DeepSeek 排序 · 规则约束" : "DeepSeek";
    if (method === "openai") return constrained ? "OpenAI 排序 · 规则约束" : "OpenAI";
    return method === "rules" ? "规则 Top 10" : "规则";
  }

  function batchDiagnosticWarning(diagnostics, contentLabel) {
    const missing = Number(diagnostics?.totalMissingItemCount ?? diagnostics?.missingItemCount) || 0;
    if (!missing) return "";
    const completed = Number(diagnostics?.totalTranslatedItemCount ?? diagnostics?.completedItemCount) || 0;
    const global = diagnostics?.totalTranslatedItemCount != null && diagnostics?.totalMissingItemCount != null;
    const requested = Number(diagnostics?.targetItemCount ?? (global ? completed + missing : diagnostics?.requestedItemCount)) || 0;
    const reason = clean(diagnostics?.coverageCompletionMessage || diagnostics?.completionMessage, "仍有条目待完成中文翻译");
    return `${contentLabel}翻译完成 ${completed}/${requested}，仍缺失 ${missing} 条：${reason}`;
  }

  function renderBrief() {
    const report = state.currentReport;
    const items = state.items.filter(isAllowedNewsItem);
    const metricItems = ["stream", "research"].includes(state.view) ? viewFilteredItems(true) : items;
    let headline = report?.brief?.headline;
    let summary = report?.brief?.summary;
    let signals = Array.isArray(report?.brief?.signals) ? report.brief.signals : [];
    const provider = providerLabel(report);
    const translatedCount = Number(report?.translatedItemCount) || 0;
    const reportItemCount = Array.isArray(report?.items) ? report.items.length : items.length;
    let method = report
      ? `${selectionLabel(report)}选稿 · ${provider ? `${provider} 中文编辑 ${translatedCount}/${reportItemCount}` : "规则摘要"}`
      : "本机视图";
    if (state.view === "stream") {
      const total = Number(report?.totalCandidateCount) || items.length;
      const hasFilters = state.rangeHours !== 24 || state.source !== "全部" || state.category !== "全部" || Boolean(state.query);
      headline = `${metricItems.length} 条合格动态进入当前 ${state.rangeHours} 小时视图`;
      summary = hasFilters
        ? `当前筛选从 ${items.length} 条已收录动态中命中 ${metricItems.length} 条；可继续调整时间、来源、主题或关键词。`
        : report?.truncated
          ? `共发现 ${total} 条合格候选；当前载荷展示评分最高的 ${items.length} 条。`
          : `共发现并保留 ${total} 条合格候选；Top 10 条目会在卡片中单独标记。`;
      const categoryCounts = valueCounts(metricItems, (item) => item.category);
      signals = Object.entries(categoryCounts).sort((a, b) => b[1] - a[1]).slice(0, 3)
        .map(([category, count]) => `${category}：${count} 条动态`);
      method = Number(report?.translatedItemCount) > 0
        ? `每 3 小时采集 · 中文翻译 ${translatedCount}/${reportItemCount}${report?.titleOnlyTranslatedItemCount ? ` · ${report.titleOnlyTranslatedItemCount} 条仅标题` : ''}`
        : "每 3 小时采集 · 规则去重";
    } else if (state.view === "research") {
      headline = `${metricItems.length} 篇前沿论文进入当前研究视图`;
      summary = `${metricItems.length === items.length ? "覆盖" : `从 ${items.length} 篇论文中筛选出 ${metricItems.length} 篇，覆盖`}最近 ${Number(report?.rangeDays) || 7} 天公开研究元数据；预印本不等同于已经同行评审。`;
      const areaCounts = valueCounts(metricItems, (item) => item.researchArea || "前沿研究");
      signals = Object.entries(areaCounts).sort((a, b) => b[1] - a[1]).slice(0, 3)
        .map(([area, count]) => `${area}：${count} 篇`);
      method = provider ? `${provider} 中文编辑 · 元数据校验` : "论文元数据 · 独立评分";
    } else if (!report) {
      if (state.view === "bookmarks") {
        headline = `已收藏 ${items.length} 条值得持续跟踪的事件`;
        summary = "收藏是本机快照，即使新闻离开最新一期，也可从这里继续打开摘要与原文来源。";
      } else if (state.view === "watchlist") {
        headline = state.watchwords.length ? `${state.watchwords.length} 个关注词正在扫描历史索引` : "添加关注词，建立你的持续跟踪视图";
        summary = "匹配覆盖中文标题、原始标题、摘要、关键事实、标签与来源。";
      } else {
        headline = state.query ? `“${state.query}”的跨日期检索结果` : "历史归档";
        summary = "从每日版归档中回看事件演变；同一事件仍应结合多个来源和后续报道判断。";
      }
      signals = items.slice(0, 3).map((item) => `${item.category}：${item.summary}`);
    }
    $("briefHeadline").textContent = clean(headline, items.length ? items[0].title : "暂无可用内容");
    if (state.view !== "research") {
      headline = ["latest", "history"].includes(state.view) ? "本期新闻概览" : headline;
      summary = `共 ${metricItems.length} 条新闻，摘要涵盖事件背景、关键细节与最新进展。`;
      signals = [];
      method = "国际新闻精选";
      $("briefHeadline").textContent = clean(headline);
    }
    $("briefSummary").textContent = clean(summary, "当前视图没有可展示的新闻。");
    $("briefPoints").innerHTML = signals.slice(0, 3).map((signal) => `<li>${esc(signal)}</li>`).join("");
    $("briefMethod").textContent = method;
    $("itemCount").textContent = metricItems.length;
    $("sourceCount").textContent = uniqueSourceCount(metricItems);
    $("categoryCount").textContent = new Set(metricItems.map((item) => state.view === "research" ? item.researchArea : item.category)).size;
    $("itemCountLabel").textContent = state.view === "research" ? "篇论文" : state.view === "stream" ? "条动态" : "重点事件";
    $("sourceCountLabel").textContent = state.view === "research" ? "资料库" : "公开信源";
    $("categoryCountLabel").textContent = state.view === "research" ? "研究方向" : "主题领域";
    $("briefUpdated").textContent = report?.generatedAt ? `生成于 ${formatDate(report.generatedAt)}` : "本机个性化视图";
    const revision = report?.publicationRevision;
    if (revision) {
      const changes = revision.changes || {};
      const count = (changes.added?.length || 0) + (changes.corrected?.length || 0) + (changes.removed?.length || 0);
      const link = new URLSearchParams({view:'history',date:report.editionDate,release:revision.initialReleaseId});
      $('briefUpdated').innerHTML = `${esc(formatDate(revision.updatedAt))} 更新，新增/更正/撤回 ${count} 条 · <a href="?${esc(link.toString())}">查看初版</a>`;
    }
  }

  function renderSpotlight() {
    if (state.view !== "latest") return;
    const reportItems = (state.latestReport?.items || []).filter(isAllowedNewsItem);
    const requested = Array.isArray(state.latestReport?.spotlightIds) ? state.latestReport.spotlightIds : [];
    const requestedItems = requested.map((id) => reportItems.find((item) => item.id === id)).filter(Boolean);
    const items = requestedItems.length === 3 ? requestedItems : diverseSpotlightItems(reportItems);
    $("spotlightStories").innerHTML = items.length ? items.map((item, index) => `
      <article class="spotlight-card tone-${esc(categoryTone(item.category))}${index === 0 && item.image ? " has-backdrop" : ""}${index > 0 && item.image ? " has-thumb" : ""}">
        ${index === 0 && item.image ? `<img class="spotlight-image spotlight-backdrop" src="${esc(item.image)}" alt="" loading="eager" decoding="async" referrerpolicy="no-referrer">` : ""}
        ${index > 0 && item.image ? `<img class="spotlight-image spotlight-thumb" src="${esc(item.image)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">` : ""}
        <div class="spotlight-content">
          <div class="spotlight-meta"><b>0${index + 1}</b><span>${esc(item.category)}</span><span>${esc(item.source)}</span></div>
          <h3>${highlightText(item.title)}</h3>
          <p>${highlightText(item.summary)}</p>
          <a href="#${esc(anchorId(item))}">阅读完整摘要 <span aria-hidden="true">↓</span></a>
        </div>
      </article>`).join("") : '<div class="empty"><b>今日必读暂不可用</b>请检查日报更新状态。</div>';
    document.querySelectorAll(".spotlight-image").forEach((image) => {
      image.addEventListener("error", () => {
        image.closest(".spotlight-card")?.classList.remove("has-backdrop");
        image.closest(".spotlight-card")?.classList.remove("has-thumb");
        image.remove();
      }, { once: true });
    });
  }

  function categoryTone(category) {
    return ({
      "AI": "ai", "航空航天": "space", "军事动态": "defense",
      "局部冲突": "conflict", "前沿技术": "frontier", "无人系统": "unmanned",
    })[category] || "frontier";
  }

  function diverseSpotlightItems(items) {
    if (!items.length) return [];
    const selected = [items[0]];
    const remaining = items.slice(1);
    while (remaining.length && selected.length < 3) {
      const events = new Set(selected.map((item) => item.eventId || item.id));
      const categories = new Set(selected.map((item) => item.category));
      const sources = new Set(selected.map((item) => item.source));
      remaining.sort((a, b) => {
        const diversity = (item) => (events.has(item.eventId || item.id) ? 0 : 40)
          + (categories.has(item.category) ? 0 : 24) + (sources.has(item.source) ? 0 : 14)
          + Number(item.score || 0) / 100;
        return diversity(b) - diversity(a);
      });
      selected.push(remaining.shift());
    }
    return selected;
  }

  function searchableText(item) {
    return [item.title, item.originalTitle, item.summary, item.abstract, item.source,
      item.researchArea, item.primaryCategory, item.question, item.method, item.findings, item.limitations,
      ...item.authors, ...item.arxivCategories, ...item.collectionKeywords, ...item.tags,
      ...item.sources.map((source) => source.name)].join(" ").toLocaleLowerCase();
  }

  function matchedResearchKeywords(item) {
    const haystack = searchableText(item);
    return state.researchKeywords.filter((keyword) => haystack.includes(keyword.toLocaleLowerCase()));
  }

  function activeHighlightTerms() {
    const terms = clean(state.query).split(/\s+/).filter(Boolean).slice(0, 8);
    if (state.view === "research") terms.push(...state.researchKeywords);
    const unique = [];
    const seen = new Set();
    terms.forEach((term) => {
      const value = clean(term);
      const key = value.toLocaleLowerCase();
      if (value && !seen.has(key)) { seen.add(key); unique.push(value); }
    });
    return unique.sort((a, b) => b.length - a.length).slice(0, 28);
  }

  function highlightText(value) {
    const text = String(value ?? "");
    const terms = activeHighlightTerms();
    if (!terms.length) return esc(text);
    const pattern = terms.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
    if (!pattern) return esc(text);
    const matcher = new RegExp(`(${pattern})`, "gi");
    return text.split(matcher).map((part, index) => index % 2 ? `<mark>${esc(part)}</mark>` : esc(part)).join("");
  }

  function anchorId(item) {
    const safe = clean(item.id).replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "") || "story";
    return `item-${safe}`;
  }

  function historyHref(story) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(clean(story?.editionDate)) || !clean(story?.id)) return "";
    const query = new URLSearchParams({ view: "history", date: story.editionDate });
    return `${location.pathname || "/"}?${query.toString()}#${anchorId(story)}`;
  }

  function renderHistoryContext(item) {
    const context = item.historyContext;
    const related = context?.relatedStories || [];
    const history = related.map((story) => `<li>
      <time datetime="${esc(story.editionDate)}">${esc(story.editionDate)}</time>
      <div class="history-event"><a href="${esc(historyHref(story))}">${highlightText(story.title)}</a>
        <small>${esc(story.source)} · ${esc(story.relationLabel)}</small>
        ${story.summary ? `<p>${highlightText(story.summary)}</p>` : ""}</div>
    </li>`).join("");
    const currentDate = item.editionDate || clean(item.publishedAt).slice(0, 10);
    const current = `<li class="history-current">
      <time${currentDate ? ` datetime="${esc(currentDate)}"` : ""}>${esc(currentDate || "当前")}</time>
      <div class="history-event"><small class="history-current-label">本次进展</small><strong>${highlightText(item.title)}</strong><small>${esc(item.source)}</small></div>
    </li>`;
    const summary = related.length ? (context.analysisProvider !== "rules" && context.timelineSummary
      || `以下 ${related.length} 条相关历史报道可用于了解本次进展的背景。`) : "";
    const outlook = related.length ? context.outlook.map((observation) => `<li><b>${esc(observation.horizon)}</b><span>${esc(observation.text)}</span></li>`).join("") : "";
    return `<section class="history-context">
      <p class="history-caption">按报道归档日期排列，点击历史标题可查看当期新闻。</p>
      ${related.length ? "" : '<p class="history-empty">暂无可展示的相关历史报道，当前仅展示本次进展。</p>'}
      <ol class="history-timeline">${history}${current}</ol>
      ${summary ? `<h4>脉络分析</h4><p class="timeline-summary">${esc(summary)}</p>` : ""}
      ${outlook ? `<h4>后续观察</h4><ul class="history-outlook">${outlook}</ul>` : ""}
      ${related.length ? '<p class="history-disclaimer">相关报道不一定属于同一事件；后续观察是待验证的方向。</p>' : ""}
    </section>`;
  }

  function renderRelatedNews(item) {
    const related = item.relatedNews.filter(isAllowedNewsItem);
    if (!related.length) return "";
    return `<section class="cross-links paper-news-links"><div class="history-heading"><h4>近期现实动态</h4><span>论文 ↔ 新闻</span></div><ul>${related.map((news) => `
      <li><div><b>${esc(news.relationType)}</b><em>${news.associationScore}/100</em></div>
        <a href="${esc(news.url)}" target="_blank" rel="noopener noreferrer">${highlightText(news.title)}</a>
        <small>${esc(news.category)} · ${esc(news.editionDate || formatDate(news.publishedAt, false))}${news.associationReasons.length ? ` · ${esc(news.associationReasons.join(" · "))}` : ""}</small></li>`).join("")}</ul></section>`;
  }

  function captureViewportAnchor() {
    const stories = [...document.querySelectorAll("#stories .story")];
    const top = document.querySelector(".topbar")?.getBoundingClientRect().bottom || 0;
    const anchor = stories.find((story) => story.getBoundingClientRect().bottom > top + 8);
    return anchor ? { key: anchor.dataset.key, offset: anchor.getBoundingClientRect().top } : null;
  }

  function restoreViewportAnchor(snapshot) {
    if (!snapshot) return;
    requestAnimationFrame(() => {
      const anchor = [...document.querySelectorAll("#stories .story")].find((story) => story.dataset.key === snapshot.key);
      if (anchor) window.scrollBy(0, anchor.getBoundingClientRect().top - snapshot.offset);
    });
  }

  async function hydrateCompactItem(item) {
    if (!item?._compact || !/^\d{4}-\d{2}-\d{2}$/.test(item.editionDate)) return item;
    let report = state.editionCache.get(item.editionDate);
    if (!report) {
      report = normalizeReport(await fetchPublicationJson(`./data/archive/${item.editionDate}.json`));
      state.editionCache.set(item.editionDate, report);
    }
    const full = report.items.find((candidate) => candidate.id === item.id);
    if (!full) throw new Error("当期归档中找不到这条新闻");
    const key = itemKey(item);
    full._bookmarkKey = key;
    const replace = (items) => items?.map((candidate) => itemKey(candidate) === key ? full : candidate);
    state.items = replace(state.items);
    state.searchItems = replace(state.searchItems);
    state.bookmarks = replace(state.bookmarks);
    writeStorage(BOOKMARK_KEY, state.bookmarks);
    return full;
  }

  function facetValue(item) {
    return state.view === "research" ? clean(item.researchArea, "前沿研究") : item.category;
  }

  function viewFilteredItems(includeCategory = true, includeSource = true) {
    const query = state.query.toLocaleLowerCase();
    const watchwords = state.watchwords.map((word) => word.toLocaleLowerCase());
    const streamAnchor = new Date(state.streamReport?.generatedAt).valueOf() || Date.now();
    const rangeThreshold = streamAnchor - state.rangeHours * 3_600_000;
    return state.items.filter((item) => {
      if (!isAllowedNewsItem(item)) return false;
      const haystack = searchableText(item);
      const watchMatch = state.view !== "watchlist" || (watchwords.length && watchwords.some((word) => haystack.includes(word)));
      const researchMatch = state.view !== "research" || state.researchScope !== "mine"
        || (state.researchKeywords.length && matchedResearchKeywords(item).length);
      const queryMatch = !query || haystack.includes(query);
      const categoryMatch = !includeCategory || state.category === "全部" || facetValue(item) === state.category;
      const sourceMatch = !includeSource || state.view !== "stream" || state.source === "全部" || item.source === state.source;
      const rangeMatch = state.view !== "stream" || new Date(item.publishedAt).valueOf() >= rangeThreshold;
      return watchMatch && researchMatch && queryMatch && categoryMatch && sourceMatch && rangeMatch;
    });
  }

  function renderFilters() {
    const base = viewFilteredItems(false);
    const available = [...new Set(base.map(facetValue).filter(Boolean))];
    const ordered = state.view === "research"
      ? available.sort((a, b) => base.filter((item) => facetValue(item) === b).length - base.filter((item) => facetValue(item) === a).length)
      : [...CATEGORIES.filter((category) => available.includes(category)), ...available.filter((category) => !CATEGORIES.includes(category))];
    const labels = ["全部", ...ordered];
    if (!labels.includes(state.category)) state.category = "全部";
    $("filters").innerHTML = labels.map((category) => {
      const count = category === "全部" ? base.length : base.filter((item) => facetValue(item) === category).length;
      return `<button type="button" data-category="${esc(category)}" class="${state.category === category ? "active" : ""}" aria-pressed="${state.category === category}">${esc(category)} <span>${count}</span></button>`;
    }).join("");
  }

  function renderSourceFilter() {
    if (state.view !== "stream") return;
    const base = viewFilteredItems(false, false);
    const counts = new Map();
    base.forEach((item) => counts.set(item.source, (counts.get(item.source) || 0) + 1));
    const sources = [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    if (state.source !== "全部" && !counts.has(state.source)) state.source = "全部";
    $("sourceFilter").innerHTML = [
      `<option value="全部">全部来源（${base.length}）</option>`,
      ...sources.map(([source, count]) => `<option value="${esc(source)}">${esc(source)}（${count}）</option>`),
    ].join("");
    $("sourceFilter").value = state.source;
  }

  function bookmarkSet() { return new Set(state.bookmarks.map(itemKey)); }

  function renderPaper(item, index, saved) {
    const key = itemKey(item);
    const opened = state.expandedKeys.has(key) ? " open" : "";
    const authors = item.authors.length ? item.authors.slice(0, 6).join("、") + (item.authors.length > 6 ? " 等" : "") : "作者信息未提供";
    const original = item.originalTitle && item.originalTitle !== item.title
      ? `<p class="original-title" lang="en">原题：${esc(item.originalTitle)}</p>` : "";
    const researchFields = [
      ["研究问题", item.question], ["方法", item.method], ["主要发现", item.findings], ["局限性", item.limitations],
    ].filter(([, value]) => value);
    const structured = researchFields.length
      ? researchFields.map(([label, value]) => `<section><h4>${esc(label)}</h4><p>${highlightText(value)}</p></section>`).join("")
      : `<section><h4>原始摘要</h4><p>${highlightText(item.abstract || item.summary)}</p></section>`;
    const personalHits = matchedResearchKeywords(item);
    const keywordBadges = [
      ...personalHits.slice(0, 4).map((keyword) => `<span class="keyword-hit">我的关键词 · ${esc(keyword)}</span>`),
      ...item.collectionKeywords.filter((keyword) => !personalHits.some((hit) => hit.toLocaleLowerCase() === keyword.toLocaleLowerCase()))
        .slice(0, 3).map((keyword) => `<span class="collection-hit">采集命中 · ${esc(keyword)}</span>`),
    ].join("");
    return `<article class="story paper-card" id="${esc(anchorId(item))}" data-key="${esc(key)}">
      <span class="rank">${String(index + 1).padStart(2, "0")}</span>
      <div class="story-main"><div class="story-copy">
        <div class="meta">
          <span class="cat paper-cat">${esc(item.researchArea || "前沿研究")}</span><span class="legacy-paper-label">旧版论文</span>
          <b>${esc(item.source)}</b><span>${esc(formatDate(item.publishedAt, false))}</span>
          <span class="review-status">${esc(item.peerReviewStatus || "评审状态未标注")}</span>
          ${item.translationProvider ? `<span class="translation-badge">${esc(item.translationProvider === "deepseek" ? "DeepSeek 中文" : "AI 中文")}</span>` : ""}
        </div>
        <h3>${highlightText(item.title)}</h3>${original}
        <p class="paper-authors">${esc(authors)}</p>
        <p class="summary">${highlightText(item.summary)}</p>
        ${keywordBadges ? `<div class="keyword-hits">${keywordBadges}</div>` : ""}
        <div class="tags">${item.tags.map((tag) => `<span>${esc(tag)}</span>`).join("")}</div>
      </div></div>
      <div class="story-side">
        <div class="score"><b>${item.score ?? "—"}</b><small>研究相关度</small></div>
        <div class="story-actions">
          <button type="button" data-bookmark title="${saved ? "取消收藏" : "收藏"}" aria-label="${saved ? "取消收藏" : "收藏"}">${saved ? "★" : "☆"}</button>
          <button type="button" data-share title="复制本条链接" aria-label="复制本条链接">⌁</button>
          ${item.pdfUrl ? `<a href="${esc(item.pdfUrl)}" target="_blank" rel="noopener noreferrer" title="打开 PDF" aria-label="打开论文 PDF">PDF</a>` : ""}
          ${item.url ? `<a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer" title="打开论文页面" aria-label="打开论文页面">↗</a>` : ""}
        </div>
      </div>
      <details class="details" data-details-key="${esc(key)}"${opened}>
        <summary>展开研究问题、方法、发现与局限</summary>
        <div class="detail-grid paper-detail">${structured}
          <section><h4>论文元数据</h4><p>${esc(authors)}</p><p>${esc(item.arxivCategories.join(" · ") || item.primaryCategory)}</p><p>${esc(item.confidenceReason)}</p></section>
          ${renderRelatedNews(item)}
        </div>
      </details>
    </article>`;
  }

  function renderStory(item, index, saved) {
    const key = itemKey(item);
    const visual = item.image ? `<figure class="story-visual"><img src="${esc(item.image)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer"></figure>` : "";
    const sources = item.sources.map((source) => `<li><a href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">${esc(source.name || source.domain)}</a></li>`).join("");
    const related = classicUI?.relatedPapers?.(item) || [];
    const paperLinks = related.length ? `<aside class="news-classic-links" aria-label="相关方法论文"><span>相关方法</span>${related.map(row=>
      `<a href="${esc(window.FrontierClassicContext.paperHref(row,item))}">${esc(window.FrontierClassicClient.displayTitle(row.paper))}</a>`).join('')}</aside>` : '';
    const sourceDetails = item._compact || item.sources.length > 1
      ? `<details class="details news-sources" data-details-key="${esc(key)}"${state.expandedKeys.has(key) ? " open" : ""}><summary>其他来源</summary>${item._compact ? '<p class="detail-loading">展开后读取原始来源链接。</p>' : `<ul class="source-list">${sources}</ul>`}</details>` : "";
    const timelineKey = `timeline::${key}`;
    const timelineDetails = `<details class="details news-timeline" data-details-key="${esc(timelineKey)}" data-item-key="${esc(key)}"${state.expandedKeys.has(timelineKey) ? " open" : ""}>
      <summary>事件时间线与分析</summary>
      ${item._compact ? '<p class="detail-loading">展开后读取事件时间线与分析。</p>' : renderHistoryContext(item)}
    </details>`;
    return `<article class="story news-story" id="${esc(anchorId(item))}" data-key="${esc(key)}">
      <span class="rank">${String(index + 1).padStart(2, "0")}</span>
      <div class="story-main${item.image ? " has-image" : ""}">${visual}<div class="story-copy">
        <div class="meta"><span class="cat" data-category="${esc(item.category)}">${esc(item.category)}</span><b>${esc(item.source)}</b><time datetime="${esc(item.publishedAt)}">${esc(formatDate(item.publishedAt))}</time></div>
        <h3>${highlightText(item.title)}</h3>
        ${item.summary ? `<p class="summary">${highlightText(item.summary)}</p>` : `<p class="summary translation-state">${item.contentAvailability === 'title-only' ? '仅标题' : '中文翻译待完成'} · 请阅读原文</p>`}
        <div class="news-footer">
          ${item.url ? `<a class="read-original" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">阅读原文 <span aria-hidden="true">↗</span></a>` : ""}
          <div class="story-actions"><button type="button" data-bookmark title="${saved ? "取消收藏" : "收藏"}" aria-label="${saved ? "取消收藏" : "收藏"}">${saved ? "★" : "☆"}</button><button type="button" data-share title="复制本条链接" aria-label="复制本条链接">⌁</button></div>
        </div>
        ${sourceDetails}
        ${paperLinks}
      </div></div>
      ${timelineDetails}
    </article>`;
  }

  function renderStories() {
    const viewport = captureViewportAnchor();
    const saved = bookmarkSet();
    const visible = viewFilteredItems(true).sort((a, b) => state.sort === "latest"
      ? new Date(b.publishedAt) - new Date(a.publishedAt)
      : Number(b.score ?? -1) - Number(a.score ?? -1) || new Date(b.publishedAt) - new Date(a.publishedAt));
    state.totalVisible = visible.length;
    const paginated = state.view === "stream" || state.view === "research";
    state.visible = visible.slice(0, paginated ? state.visibleLimit : 200);
    const unit = state.view === "research" ? "篇" : "条";
    const noteParts = [`显示 ${state.visible.length} / ${state.totalVisible} ${unit}`];
    if (state.view === "history" && state.query) noteParts.push("按月分片的跨日期索引");
    if (state.view === "watchlist") noteParts.push(`${state.watchwords.length} 个关注词`);
    if (state.view === "research" && state.researchScope === "mine") noteParts.push(`${state.researchKeywords.length} 个论文关键词 · 专属论文流`);
    $("resultNote").textContent = noteParts.join(" · ");
    if (!state.visible.length) {
      const message = state.view === "watchlist" && !state.watchwords.length
        ? "先添加一个关注词，匹配结果会显示在这里。"
        : state.view === "bookmarks" ? "尚未收藏新闻。点击新闻卡片上的 ☆ 即可收藏。"
          : state.view === "research" && !state.researchKeywords.length ? "先添加论文关键词，系统会自动生成你的专属论文流。"
            : state.view === "research" && state.researchScope === "mine" ? "当前论文中暂无关键词命中；可添加英文同义词，或由管理员把该方向加入系统采集词。"
          : "没有匹配的新闻，请更换分类、日期或搜索词。";
      $("stories").innerHTML = `<div class="empty"><b>暂无结果</b>${esc(message)}</div>`;
    } else {
      const grouped = state.view === "watchlist" || (state.view === "history" && state.query);
      let previousEdition = "";
      $("stories").innerHTML = state.visible.map((item, index) => {
        const heading = grouped && item.editionDate !== previousEdition
          ? `<h3 class="edition-group">${esc(item.editionDate || "日期未知")} 版</h3>` : "";
        previousEdition = item.editionDate;
        return heading + (item.contentType === "paper"
          ? renderPaper(item, index, saved.has(itemKey(item)))
          : renderStory(item, index, saved.has(itemKey(item))));
      }).join("");
    }
    $("loadMoreBtn").hidden = !paginated || state.visible.length >= state.totalVisible;
    if (!$("loadMoreBtn").hidden) $("loadMoreBtn").textContent = `再加载 ${Math.min(PAGE_SIZE, state.totalVisible - state.visible.length)} ${unit}`;
    $("stories").setAttribute("aria-busy", "false");
    restoreViewportAnchor(viewport);
  }

  function renderWatchwords() {
    $("watchChips").innerHTML = state.watchwords.length
      ? state.watchwords.map((word) => `<button class="watch-chip" type="button" data-remove-word="${esc(word)}" title="移除关注词">${esc(word)}<span>×</span></button>`).join("")
      : '<span class="method-kicker">尚未添加关注词</span>';
  }

  function renderAll() {
    renderViewCopy();
    renderDateControl();
    if (state.view === "research") return;
    if (state.view === "bookmarks") classicUI.renderBookmarks();
    if (state.view === "deepread") {
      $("deepreadContent").innerHTML = renderDeepreadArticle(state.deepreadReport);
      $("deepreadContent").setAttribute("aria-busy", "false");
      $("dataNote").textContent = state.deepreadReport?.generatedAt
        ? `本期生成于 ${formatDate(state.deepreadReport.generatedAt)}`
        : "每日深读将在下一次日报成功更新后发布。";
      syncUrl();
      return;
    }
    renderSpotlight();
    renderWatchwords();
    renderSourceFilter();
    renderFilters();
    renderBrief();
    renderStories();
    const report = state.currentReport || state.latestReport;
    $("dataNote").textContent = report?.generatedAt
      ? state.view === "research"
        ? `论文雷达生成于 ${formatDate(report.generatedAt)}；预印本与中文摘要不能替代完整论文和同行评审。`
        : state.view === "stream"
          ? `全量动态更新于 ${formatDate(report.generatedAt)}；动态流是合格候选集合，Top 10 仍以每日简报为准。`
          : `数据生成于 ${formatDate(report.generatedAt)}；军事、冲突与前沿技术信息请优先核验一手来源。`
      : "当前视图没有远程数据。";
    syncUrl();
  }

  function renderViewLoading(view) {
    state.view = view;
    document.querySelectorAll("[data-view]").forEach((link) => {
      const active = link.dataset.view === view && link.closest("nav");
      link.classList.toggle("active", Boolean(active));
      if (link.closest("nav")) link.setAttribute("aria-current", active ? "page" : "false");
    });
    $("dataState").className = "state-badge";
    $("dataState").textContent = view === "research" ? "读取论文" : "读取动态";
    $("stories").setAttribute("aria-busy", "true");
    $("stories").innerHTML = '<div class="loading"></div><div class="loading"></div>';
    $("resultNote").textContent = view === "research" ? "正在读取论文雷达…" : "正在读取全量动态…";
    syncUrl();
  }

  async function switchView(view, options = {}) {
    if (!VIEWS.has(view)) return;
    const request = ++state.viewRequest;
    if (view === "research") {
      state.view = view;
      hideAlert();
      renderViewCopy();
      $("dateControl").hidden = true;
      await classicUI.show({initial:Boolean(options.initial), ...(options.date !== undefined ? {date:options.date} : {}), bypassCache:Boolean(options.bypassCache)});
      return;
    }
    if (view === "bookmarks") {
      classicUI.hide();
      state.view = view;
      state.category = "全部";
      state.visibleLimit = PAGE_SIZE;
      state.currentReport = null;
      state.items = state.bookmarks.map((item, index) => normalizeItem(item, index, item.editionDate));
      hideAlert();
      $("dataState").textContent = "本机收藏";
      $("dataState").className = "state-badge";
      renderAll();
      return;
    }
    try { await ensureNewsContext(); }
    catch (error) {
      if (request !== state.viewRequest) return;
      if (options.initial) throw error;
      toast("新闻暂时无法读取：" + clean(error.message));
      return;
    }
    if (request !== state.viewRequest) return;
    classicUI.hide();
    state.historicalSelection = view === "history" || (view === "deepread" && Boolean(options.historical));
    if (["stream", "research"].includes(view)) renderViewLoading(view);
    else state.view = view;
    state.category = "全部";
    state.visibleLimit = PAGE_SIZE;
    if (view === "deepread") {
      state.currentReport = null;
      state.items = [];
      state.editionDate = options.date || "";
      renderViewCopy();
      $("deepreadContent").setAttribute("aria-busy", "true");
      $("deepreadContent").innerHTML = '<div class="loading"></div>';
      await loadDeepread(options.date || "", Boolean(options.bypassCache));
      if (request !== state.viewRequest) return;
      state.currentReport = state.deepreadReport;
      state.editionDate = options.date || state.deepreadReport?.publicationEditionDate || state.deepreadReport?.editionDate || "";
      updateViewHealth();
      renderAll();
      return;
    }
    if (view === "latest") {
      state.sort = "score";
      state.currentReport = state.latestReport;
      state.items = state.latestReport?.items || [];
      state.editionDate = state.latestReport?.editionDate || "";
    } else if (view === "stream") {
      state.sort = "latest";
      await loadStream(Boolean(options.showToast), Boolean(options.bypassCache));
      if (request !== state.viewRequest) return;
      state.currentReport = state.streamReport;
      state.items = state.streamReport?.items || [];
      state.editionDate = "";
    } else if (view === "history") {
      await ensureArchiveIndex(Boolean(options.bypassCache));
      if (request !== state.viewRequest) return;
      const dates = availableDates();
      state.editionDate = options.date || state.editionDate || dates[0] || state.latestReport?.editionDate || "";
      if (state.query) {
        state.items = await ensureSearchIndex(Boolean(options.bypassCache));
        state.currentReport = null;
      } else if (state.editionDate) {
        await loadEdition(state.editionDate, Boolean(options.bypassCache));
      }
    } else if (view === "bookmarks") {
      state.currentReport = null;
      state.items = state.bookmarks.map((item, index) => normalizeItem(item, index, item.editionDate));
    } else {
      state.currentReport = null;
      state.items = await ensureSearchIndex(Boolean(options.bypassCache));
    }
    if (["stream", "research"].includes(view) && location.hash.startsWith("#item-")) {
      state.visibleLimit = Math.max(PAGE_SIZE, state.items.length);
    }
    document.querySelectorAll("[data-sort]").forEach((button) => button.classList.toggle("active", button.dataset.sort === state.sort));
    updateViewHealth();
    renderAll();
  }

  function toggleBookmark(key) {
    const current = state.visible.find((item) => itemKey(item) === key);
    if (!current) return;
    const index = state.bookmarks.findIndex((item) => itemKey(item) === key);
    if (index >= 0) {
      state.bookmarks.splice(index, 1);
      toast("已取消收藏");
    } else {
      state.bookmarks.unshift({ ...current, _bookmarkKey: key });
      toast("已收藏到本机");
    }
    writeStorage(BOOKMARK_KEY, state.bookmarks);
    if (state.view === "bookmarks") state.items = state.bookmarks;
    renderBrief();
    renderFilters();
    renderStories();
  }

  async function copyText(value) {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return;
    }
    const input = document.createElement("textarea");
    input.value = value;
    input.setAttribute("readonly", "");
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.append(input);
    input.select();
    document.execCommand("copy");
    input.remove();
  }

  async function shareStory(key) {
    const item = state.visible.find((candidate) => itemKey(candidate) === key);
    if (!item) return;
    const url = new URL(location.pathname, location.origin);
    if (item.editionDate) {
      url.searchParams.set("view", "history");
      url.searchParams.set("date", item.editionDate);
      let report = state.editionCache.get(item.editionDate);
      if (!report && state.currentReport?.editionDate === item.editionDate) report = state.currentReport;
      if (!report && releaseManifest) {
        try { report = await fetchPublicationJson(`./data/archive/${item.editionDate}.json`); }
        catch (_) { toast('该历史版本暂时无法读取，请稍后重试'); return; }
      }
      if (/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(report?.releaseId || '')) url.searchParams.set('release', report.releaseId);
    } else if (["stream", "research"].includes(state.view)) {
      url.searchParams.set("view", state.view);
    }
    url.hash = anchorId(item);
    try {
      await copyText(url.href);
      toast("已复制本条新闻链接");
    } catch (_) {
      toast("浏览器未允许复制，请从地址栏复制");
    }
  }

  function scrollToInitialHash() {
    if (state.hashHandled || !location.hash) return;
    const target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (!target) return;
    state.hashHandled = true;
    requestAnimationFrame(() => target.scrollIntoView({ block: "start" }));
  }

  function openDialog(type) {
      $("dialogEyebrow").textContent = "阅读说明";
      if (state.view === "research") {
        $("dialogTitle").textContent = "如何阅读经典论文";
        $("dialogContent").innerHTML = `<ul><li><b>标题：</b>中文译名用于阅读和检索，英文原名保留在标题下方及引用中。</li><li><b>日期：</b>发表年份是论文原始发表时间；推荐日期是本站这次推荐的日期，历史推荐可单独回看。</li><li><b>导读：</b>保留研究问题、方法、贡献、适用条件、局限和阅读建议，并附全文页码或章节定位；阅读推论单独标识。</li><li><b>关联：</b>来源明确描述采用某种具体方法时，提供相应论文与新闻入口。这种关联用于理解方法背景，不代表新系统复现了论文或具备相同性能。</li><li><b>个人工具：</b>收藏只保存在当前浏览器；复制引用使用英文书目原名。</li></ul>`;
      } else {
        $("dialogTitle").textContent = "新闻如何整理与更新";
        $("dialogContent").innerHTML = `<ul><li><b>选稿：</b>精选新闻与深读采用具有有效正文、可核查事实的报道。合格候选不足时展示实际数量；仅标题信息可留在动态，明确标识状态并提供原文入口。</li><li><b>摘要：</b>只整理来源支持的事实，不用采集缺失说明填充摘要，也不把整段英文当作中文摘要。信息有限时允许摘要更短。</li><li><b>合并与来源：</b>同一期的重复事件合并展示，保留可用来源；同一机构的不同事件分别保留。</li><li><b>后续：</b>主题相同不等于事件相同。回看不同日期的报道时，请结合原文核对新增事实，重复出现本身不代表有新进展。</li><li><b>正式版本：</b>日期按北京时间计算。同日重试不自动改写正式日报；必要更正保留初版、差异及对应版本入口。</li><li><b>更新失败：</b>内容未通过校验时保留之前的合格版本。深读独立判断是否更新，沿用前期时显示真实内容日期；没有合格旧版时显示未更新状态。</li></ul>`;
      }
    $("infoDialog").showModal();
  }

  let searchTimer;
  async function handleSearch(value) {
    state.query = clean(value);
    state.visibleLimit = PAGE_SIZE;
    if (state.view === "history") {
      if (state.query) {
        state.currentReport = null;
        state.items = await ensureSearchIndex();
      } else if (state.editionDate) {
        await loadEdition(state.editionDate);
      }
    }
    renderAll();
  }

  document.addEventListener("click", async (event) => {
    const target = event.target instanceof Element ? event.target : event.target.parentElement;
    const evidenceLink = target?.closest('[data-evidence-target]');
    if (evidenceLink) {
      const evidence = document.getElementById(evidenceLink.dataset.evidenceTarget);
      if (evidence) {
        const details = evidence.closest('details');
        if (details) details.open = true;
        evidence.scrollIntoView({behavior:'smooth',block:'center'});
      }
    }
    const viewButton = target?.closest("[data-view]");
    if (viewButton && VIEWS.has(viewButton.dataset.view)) {
      event.preventDefault();
      await switchView(viewButton.dataset.view);
      return;
    }
    const categoryButton = target?.closest("[data-category]");
    if (categoryButton?.closest("#filters")) {
      state.category = categoryButton.dataset.category;
      state.visibleLimit = PAGE_SIZE;
      renderFilters(); renderBrief(); renderStories(); return;
    }
    const rangeButton = target?.closest("[data-range]");
    if (rangeButton?.closest("#rangeControls")) {
      state.rangeHours = Number(rangeButton.dataset.range) || 24;
      state.visibleLimit = PAGE_SIZE;
      renderAll();
      return;
    }
    const researchScopeButton = target?.closest("[data-research-scope]");
    if (researchScopeButton) {
      const scope = researchScopeButton.dataset.researchScope;
      if (scope === "mine" && !state.researchKeywords.length) { toast("请先添加论文关键词"); return; }
      state.researchScope = scope === "mine" ? "mine" : "all";
      state.visibleLimit = PAGE_SIZE;
      writeStorage(RESEARCH_SCOPE_KEY, state.researchScope);
      renderAll();
      return;
    }
    const bookmarkButton = target?.closest("[data-bookmark]");
    if (bookmarkButton) { toggleBookmark(bookmarkButton.closest(".story").dataset.key); return; }
    const shareButton = target?.closest("[data-share]");
    if (shareButton) { await shareStory(shareButton.closest(".story").dataset.key); return; }
    const removeWord = target?.closest("[data-remove-word]");
    if (removeWord) {
      state.watchwords = state.watchwords.filter((word) => word !== removeWord.dataset.removeWord);
      writeStorage(WATCH_KEY, state.watchwords);
      renderAll();
      return;
    }
    const removeResearchKeyword = target?.closest("[data-remove-research-keyword]");
    if (removeResearchKeyword) {
      const keyword = removeResearchKeyword.dataset.removeResearchKeyword;
      state.researchKeywords = state.researchKeywords.filter((word) => word !== keyword);
      if (!state.researchKeywords.length) state.researchScope = "all";
      writeStorage(RESEARCH_KEYWORDS_KEY, state.researchKeywords);
      writeStorage(RESEARCH_SCOPE_KEY, state.researchScope);
      state.visibleLimit = PAGE_SIZE;
      renderAll();
    }
  });

  $("stories").addEventListener("toggle", async (event) => {
    const details = event.target.closest("details[data-details-key]");
    if (!details) return;
    const key = details.dataset.detailsKey;
    if (!details.open) {
      state.expandedKeys.delete(key);
      return;
    }
    state.expandedKeys.add(key);
    const item = state.visible.find((candidate) => itemKey(candidate) === (details.dataset.itemKey || key));
    if (!item?._compact || details.dataset.loading) return;
    details.dataset.loading = "true";
    const loading = details.querySelector(".detail-loading");
    if (loading) loading.textContent = "正在读取当期归档详情…";
    try {
      await hydrateCompactItem(item);
      renderStories();
    } catch (error) {
      if (loading) loading.textContent = `详情加载失败：${clean(error?.message, "未知错误")}`;
      delete details.dataset.loading;
    }
  }, true);

  $("stories").addEventListener("error", (event) => {
    if (event.target.matches(".story-visual img")) event.target.closest(".story-visual")?.remove();
  }, true);
  $("deepreadContent").addEventListener("error", (event) => {
    if (event.target.matches(".deepread-figure img")) event.target.closest("figure")?.remove();
  }, true);

  $("search").value = state.query;
  $("search").addEventListener("input", (event) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { handleSearch(event.target.value); }, 180);
  });
  document.querySelectorAll("[data-sort]").forEach((button) => button.addEventListener("click", () => {
    state.sort = button.dataset.sort;
    state.visibleLimit = PAGE_SIZE;
    document.querySelectorAll("[data-sort]").forEach((item) => item.classList.toggle("active", item === button));
    renderStories();
  }));
  $("sourceFilter").addEventListener("change", (event) => {
    state.source = event.target.value || "全部";
    state.visibleLimit = PAGE_SIZE;
    renderAll();
  });
  $("loadMoreBtn").addEventListener("click", () => {
    state.visibleLimit += PAGE_SIZE;
    renderStories();
  });
  $("editionPicker").addEventListener("change", async (event) => {
    state.query = ""; $("search").value = "";
    await switchView(state.view === "deepread" ? "deepread" : "history", { date: event.target.value, historical: true });
  });
  [$("previousEdition"), $("nextEdition")].forEach((button) => button.addEventListener("click", async () => {
    if (!button.dataset.date) return;
    state.query = ""; $("search").value = "";
    await switchView(state.view === "deepread" ? "deepread" : "history", { date: button.dataset.date, historical: true });
  }));
  $("watchForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = $("watchInput");
    const word = clean(input.value).slice(0, 40);
    if (!word) return;
    if (state.watchwords.some((item) => item.toLocaleLowerCase() === word.toLocaleLowerCase())) { toast("该关注词已存在"); return; }
    if (state.watchwords.length >= 20) { toast("最多保存 20 个关注词"); return; }
    state.watchwords.push(word); input.value = "";
    writeStorage(WATCH_KEY, state.watchwords);
    renderAll(); toast("已添加关注词");
  });
  $("reloadBtn").addEventListener("click", async () => {
    if (state.view === "research") {
      $("reloadBtn").disabled = true;
      try { await classicUI.show({bypassCache:true}); }
      finally { $("reloadBtn").disabled = false; }
      return;
    }
    state.archiveIndex = null; state.searchManifest = null; state.searchItems = null; state.editionCache.clear();
    state.deepreadIndex = null; state.deepreadCache.clear();
    const date = state.editionDate, historical = state.historicalSelection, refreshView = state.view;
    $("reloadBtn").disabled = true;
    ++state.deepreadRequest; const owner = ++state.viewRequest;
    try {
      await loadPublication(true);
      if (owner !== state.viewRequest || state.view !== refreshView) return;
      await loadLatest(true, true);
      if (owner !== state.viewRequest || state.view !== refreshView) return;
      await switchView(refreshView, { date: historical ? date : "", historical, bypassCache: true });
    } catch (error) {
      if (owner !== state.viewRequest || state.view !== refreshView) return;
      await loadPipelineStatus(true);
      if (owner !== state.viewRequest || state.view !== refreshView) return;
      if (state.pipelineStatus?.state === "failed") updateViewHealth();
      else showAlert("failed", "刷新失败", clean(error.message));
    }
    finally { $("reloadBtn").disabled = false; }
  });
  $("exportBtn").addEventListener("click", () => {
    const payload = { exportedAt: new Date().toISOString(), view: state.view, query: state.query, items: state.visible };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `frontier-pulse-${state.view}-${state.editionDate || "selection"}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 500);
    toast("已导出当前结果");
  });
  $("themeBtn").addEventListener("click", () => applyTheme(state.theme === "dark" ? "light" : "dark", true));
  $("scoringHelp").addEventListener("click", () => openDialog("scoring"));
  document.querySelectorAll('[data-reading-help]').forEach(button=>button.addEventListener('click',()=>openDialog('reading')));
  document.querySelector("[data-close-dialog]").addEventListener("click", () => $("infoDialog").close());
  $("infoDialog").addEventListener("click", (event) => { if (event.target === $("infoDialog")) $("infoDialog").close(); });
  $("alertClose").addEventListener("click", hideAlert);
  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) {
      event.preventDefault(); $("search").focus();
    }
  });

  let newsContextPromise;
  async function ensureNewsContext() {
    if (!newsContextPromise) newsContextPromise = (async () => {
      newsPolicy = await fetchJson("./assets/news-policy.json");
      if (!Array.isArray(newsPolicy?.subject_terms) || !newsPolicy.subject_terms.length) throw new Error("新闻内容规则暂时不可用，请刷新重试。");
      await loadPublication();
      await loadLatest();
      await ensureArchiveIndex();
      // Paper availability must not delay an otherwise usable news edition.
      classicUI.ensureContext().then(()=>{
        if(state.view !== 'research' && state.items.length)renderStories();
      }).catch(()=>{});
    })().catch(error => { newsContextPromise = null; throw error; });
    return newsContextPromise;
  }
  classicUI.setNewsProvider(async({date}={})=>{
    await ensureNewsContext();
    if(!/^\d{4}-\d{2}-\d{2}$/.test(date || ''))return (state.latestReport?.items || []).filter(isAllowedNewsItem);
    const report=state.editionCache.get(date)
      || normalizeReport(await fetchPublicationJson(`./data/archive/${date}.json`));
    return report.items.map(item=>({...item,releaseId:report.releaseId || item.releaseId})).filter(isAllowedNewsItem);
  });
  async function init() {
    applyTheme(state.theme);
    if ("serviceWorker" in navigator && location.protocol.startsWith("http")) {
      navigator.serviceWorker.register("./sw.js").catch(() => { /* offline support is optional */ });
    }
    $("stories").innerHTML = '<div class="loading"></div><div class="loading"></div>';
    await switchView(initialView, { date: initialDate, historical: Boolean(initialDate), initial:true });
    scrollToInitialHash();
  }

  init().catch((error) => {
    if (state.view === "research") return;
    state.items = [];
    showAlert("failed", "页面初始化失败", clean(error?.message, "未知错误"));
    renderAll();
  });
})();
