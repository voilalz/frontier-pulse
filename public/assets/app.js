(() => {
  "use strict";

  const ENDPOINTS = {
    latest: "./data/news.json",
    status: "./data/status.json",
    archive: "./data/archive/index.json",
    search: "./data/archive/search-index.json",
  };
  const CATEGORIES = ["AI", "航空航天", "军事动态", "局部冲突", "前沿技术", "无人系统"];
  const VIEWS = new Set(["latest", "history", "bookmarks", "watchlist"]);
  const CACHE_KEY = "fp-last-good-report-v2";
  const BOOKMARK_KEY = "fp-bookmarks-v2";
  const WATCH_KEY = "fp-watchwords-v1";
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
  const legacyBookmarks = readStorage("fp-bookmarks", []).filter((item) => typeof item === "string");
  const storedBookmarks = readStorage(BOOKMARK_KEY, []).filter((item) => item && typeof item === "object");

  const state = {
    view: initialView,
    query: clean(params.get("q")),
    category: "全部",
    sort: "score",
    editionDate: initialDate,
    latestReport: null,
    currentReport: null,
    items: [],
    visible: [],
    archiveIndex: null,
    searchManifest: null,
    searchItems: null,
    editionCache: new Map(),
    expandedKeys: new Set(),
    pipelineStatus: null,
    bookmarks: storedBookmarks,
    watchwords: readStorage(WATCH_KEY, []).filter((word) => typeof word === "string").slice(0, 20),
    latestLoadError: "",
    usingCache: false,
    theme: readStorage(THEME_KEY, "") || (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light"),
    hashHandled: false,
  };

  function formatDate(value, includeTime = true) {
    const date = new Date(value);
    if (Number.isNaN(date.valueOf())) return "时间未知";
    const options = includeTime
      ? { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false, timeZoneName: "short" }
      : { year: "numeric", month: "2-digit", day: "2-digit" };
    return new Intl.DateTimeFormat("zh-CN", options).format(date);
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

  function normalizeItem(raw, index, editionDate = "") {
    if (!raw || typeof raw !== "object" || !clean(raw.title)) throw new Error(`第 ${index + 1} 条新闻缺少标题`);
    const sources = (Array.isArray(raw.sources) ? raw.sources : [])
      .map((source) => normalizeSource(source, raw))
      .filter(Boolean);
    if (!sources.length) {
      const primary = normalizeSource({}, raw);
      if (primary) sources.push(primary);
    }
    const summary = clean(raw.summary, "暂无摘要，请阅读原文核验。");
    const item = {
      id: clean(raw.id, `item-${index}`),
      title: clean(raw.title),
      originalTitle: clean(raw.originalTitle || raw.title),
      summary,
      keyFacts: (Array.isArray(raw.keyFacts) ? raw.keyFacts : [summary]).map((fact) => clean(fact)).filter(Boolean).slice(0, 4),
      why: clean(raw.why, "该事件的重要性需要结合后续公开信息继续判断。"),
      category: clean(raw.category, "前沿技术"),
      source: clean(raw.source || sources[0]?.name, "未知来源"),
      country: clean(raw.country, "国际"),
      publishedAt: clean(raw.publishedAt),
      url: safeUrl(raw.url || sources[0]?.url),
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
      editionDate: clean(raw.editionDate || editionDate),
      _compact: Boolean(raw._compact),
    };
    item._bookmarkKey = clean(raw._bookmarkKey) || itemKey(item);
    return item;
  }

  function normalizeReport(payload) {
    if (!payload || typeof payload !== "object" || !Array.isArray(payload.items) || !payload.items.length) {
      throw new Error("日报文件不存在或没有新闻条目");
    }
    const editionDate = clean(payload.editionDate);
    return {
      ...payload,
      editionDate,
      generatedAt: clean(payload.generatedAt),
      method: clean(payload.method, "rules"),
      items: payload.items.slice(0, 100).map((item, index) => normalizeItem(item, index, editionDate)),
    };
  }

  async function fetchJson(url, bypassCache = false) {
    const separator = url.includes("?") ? "&" : "?";
    const target = bypassCache ? `${url}${separator}t=${Date.now()}` : url;
    const response = await fetch(target, { cache: bypassCache ? "no-store" : "default" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  function toast(message) {
    const element = $("toast");
    element.textContent = message;
    element.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { element.hidden = true; }, 2600);
  }

  function showAlert(kind, title, detail) {
    const alert = $("systemAlert");
    alert.className = `shell alert ${kind === "failed" ? "failed" : ""}`;
    $("alertTitle").textContent = title;
    $("alertDetail").textContent = detail;
    alert.hidden = false;
  }

  function hideAlert() { $("systemAlert").hidden = true; }

  function reportAgeHours(report) {
    const generated = new Date(report?.generatedAt).valueOf();
    return Number.isFinite(generated) ? (Date.now() - generated) / 3_600_000 : Infinity;
  }

  function updateHealth(report) {
    const badge = $("dataState");
    badge.className = "state-badge";
    if (state.latestLoadError) {
      badge.textContent = state.usingCache ? "本机缓存" : "读取失败";
      badge.classList.add("failed");
      showAlert("failed", "无法读取生产日报", state.usingCache
        ? `当前展示的是上次成功读取的真实日报。错误：${state.latestLoadError}`
        : `页面没有启用任何样例回退，且本机没有可用缓存。错误：${state.latestLoadError}`);
      return;
    }
    if (state.pipelineStatus?.state === "failed") {
      badge.textContent = "更新失败";
      badge.classList.add("failed");
      const lastSuccess = state.pipelineStatus.lastSuccessAt ? formatDate(state.pipelineStatus.lastSuccessAt) : "未知";
      showAlert("failed", "最近一次自动更新失败", `${state.pipelineStatus.message || "采集流程未成功完成"}；最后成功时间：${lastSuccess}。页面继续保留上一期真实数据。`);
      return;
    }
    const age = reportAgeHours(report);
    if (age > 36) {
      badge.textContent = "数据过期";
      badge.classList.add("warning");
      showAlert("warning", "日报可能已经过期", `当前数据生成于 ${formatDate(report?.generatedAt)}，已超过 36 小时。请检查 GitHub Actions、信源可用性和部署状态。`);
      return;
    }
    if (report?.items?.length !== 10) {
      badge.textContent = "数量异常";
      badge.classList.add("warning");
      showAlert("warning", "日报条目数量异常", `生产日报应包含 10 条新闻，当前读取到 ${report?.items?.length || 0} 条。`);
      return;
    }
    const warnings = Array.isArray(state.pipelineStatus?.warnings) ? state.pipelineStatus.warnings.filter(Boolean) : [];
    if (state.pipelineStatus?.editorialStatus === "fallback" || warnings.length) {
      badge.textContent = "规则回退";
      badge.classList.add("warning");
      showAlert("warning", "日报已更新，但 AI 编辑发生降级", warnings.join("；") || state.pipelineStatus.message || "已使用规则模式生成本期内容。");
      return;
    }
    badge.textContent = "在线";
    hideAlert();
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
    $("dataState").textContent = "同步中";
    state.latestLoadError = "";
    state.usingCache = false;
    const statusPromise = loadPipelineStatus(bypassCache);
    try {
      const report = normalizeReport(await fetchJson(ENDPOINTS.latest, bypassCache));
      state.latestReport = report;
      state.editionCache.set(report.editionDate, report);
      writeStorage(CACHE_KEY, report);
      migrateLegacyBookmarks(report.items);
      if (showToast) toast("已读取最新日报");
    } catch (error) {
      state.latestLoadError = clean(error?.message, "未知错误");
      try {
        state.latestReport = normalizeReport(readStorage(CACHE_KEY, null));
        state.usingCache = true;
      } catch (_) {
        state.latestReport = null;
      }
    }
    await statusPromise;
    updateHealth(state.latestReport);
    if (state.view === "latest") {
      state.currentReport = state.latestReport;
      state.items = state.latestReport?.items || [];
      state.editionDate = state.latestReport?.editionDate || state.editionDate;
    }
  }

  async function ensureArchiveIndex(bypassCache = false) {
    if (state.archiveIndex && !bypassCache) return state.archiveIndex;
    try {
      const payload = await fetchJson(ENDPOINTS.archive, bypassCache);
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
      const payload = await fetchJson(ENDPOINTS.search, bypassCache);
      state.searchManifest = payload;
      let rawItems = Array.isArray(payload?.items) ? payload.items : [];
      if (Number(payload?.schemaVersion) >= 2 && Array.isArray(payload?.shards)) {
        rawItems = [];
        const shards = payload.shards.filter((shard) => /^\.\/data\/archive\/search-\d{4}-\d{2}\.json$/.test(clean(shard?.file)));
        for (let index = 0; index < shards.length; index += 4) {
          const batch = await Promise.all(shards.slice(index, index + 4).map(async (shard) => {
            const shardPayload = await fetchJson(shard.file, bypassCache);
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
      const report = normalizeReport(await fetchJson(`./data/archive/${date}.json`, bypassCache));
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
    if (state.view === "history" && state.editionDate) query.set("date", state.editionDate);
    if (state.query) query.set("q", state.query);
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
      latest: ["DAILY INTELLIGENCE BRIEF", "全球科技与安全态势日报", "从全球公开信源中去重、交叉比对并筛选每日十条重点事件。摘要用于快速判断，关键结论请回到原文核验。", "TOP STORIES", "今日要闻"],
      history: ["ARCHIVE & DISCOVERY", "历史归档与跨日检索", "按日期回看每日版；输入搜索词后，将自动切换为跨日期检索。", "ARCHIVE", state.query ? "跨日期搜索" : "历史要闻"],
      bookmarks: ["PERSONAL COLLECTION", "我的收藏", "收藏内容完整保存在当前浏览器，不会上传服务器。", "SAVED STORIES", "收藏新闻"],
      watchlist: ["PERSONAL WATCHLIST", "关注词情报流", "用本机关注词扫描已有归档，快速追踪技术、机构、地区与装备型号。", "WATCHED SIGNALS", "关注词命中"],
    }[state.view];
    $("viewEyebrow").textContent = copy[0];
    $("viewTitle").textContent = copy[1];
    $("viewDescription").textContent = copy[2];
    $("feedEyebrow").textContent = copy[3];
    $("feedTitle").textContent = copy[4];
    $("watchPanel").hidden = state.view !== "watchlist";
    document.querySelectorAll("[data-view]").forEach((button) => {
      button.classList.toggle("active", button.dataset.view === state.view && button.closest("nav"));
      if (button.closest("nav")) button.setAttribute("aria-current", button.dataset.view === state.view ? "page" : "false");
    });
  }

  function renderDateControl() {
    const control = $("dateControl");
    control.hidden = !["latest", "history"].includes(state.view);
    if (control.hidden) return;
    const dates = availableDates();
    const current = state.editionDate || state.latestReport?.editionDate || dates[0] || "";
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

  function renderBrief() {
    const report = state.currentReport;
    const items = state.items;
    let headline = report?.brief?.headline;
    let summary = report?.brief?.summary;
    let signals = Array.isArray(report?.brief?.signals) ? report.brief.signals : [];
    let method = report?.method === "openai" ? "AI 编辑 + 规则校验" : report ? "规则评分" : "本机视图";
    if (!report) {
      if (state.view === "bookmarks") {
        headline = `已收藏 ${items.length} 条值得持续跟踪的事件`;
        summary = "收藏是本机快照，即使新闻离开最新一期，也可从这里继续打开来源与评分说明。";
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
    $("briefSummary").textContent = clean(summary, "当前视图没有可展示的新闻。");
    $("briefPoints").innerHTML = signals.slice(0, 3).map((signal) => `<li>${esc(signal)}</li>`).join("");
    $("briefMethod").textContent = method;
    $("itemCount").textContent = items.length;
    $("sourceCount").textContent = uniqueSourceCount(items);
    $("categoryCount").textContent = new Set(items.map((item) => item.category)).size;
    $("briefUpdated").textContent = report?.generatedAt ? `生成于 ${formatDate(report.generatedAt)}` : "本机个性化视图";
  }

  function searchableText(item) {
    return [item.title, item.originalTitle, item.summary, item.why, item.source, item.country, ...item.keyFacts, ...item.tags, ...item.sources.map((source) => source.name)].join(" ").toLocaleLowerCase();
  }

  function highlightText(value) {
    const text = String(value ?? "");
    const terms = clean(state.query).split(/\s+/).filter(Boolean).slice(0, 8);
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
      report = normalizeReport(await fetchJson(`./data/archive/${item.editionDate}.json`));
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

  function viewFilteredItems(includeCategory = true) {
    const query = state.query.toLocaleLowerCase();
    const watchwords = state.watchwords.map((word) => word.toLocaleLowerCase());
    return state.items.filter((item) => {
      const haystack = searchableText(item);
      const watchMatch = state.view !== "watchlist" || (watchwords.length && watchwords.some((word) => haystack.includes(word)));
      const queryMatch = !query || haystack.includes(query);
      const categoryMatch = !includeCategory || state.category === "全部" || item.category === state.category;
      return watchMatch && queryMatch && categoryMatch;
    });
  }

  function renderFilters() {
    const base = viewFilteredItems(false);
    const labels = ["全部", ...CATEGORIES.filter((category) => base.some((item) => item.category === category))];
    if (!labels.includes(state.category)) state.category = "全部";
    $("filters").innerHTML = labels.map((category) => {
      const count = category === "全部" ? base.length : base.filter((item) => item.category === category).length;
      return `<button type="button" data-category="${esc(category)}" class="${state.category === category ? "active" : ""}" aria-pressed="${state.category === category}">${esc(category)} <span>${count}</span></button>`;
    }).join("");
  }

  function bookmarkSet() { return new Set(state.bookmarks.map(itemKey)); }

  function renderStory(item, index, saved) {
    const original = item.originalTitle && item.originalTitle !== item.title
      ? `<p class="original-title" lang="en">原题：${esc(item.originalTitle)}</p>` : "";
    const sources = item.sources.map((source, sourceIndex) => `<li><a href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">${esc(source.name || source.domain || `来源 ${sourceIndex + 1}`)}</a>${source.publishedAt ? ` · ${esc(formatDate(source.publishedAt))}` : ""}</li>`).join("");
    const components = Object.entries(item.scoreComponents).map(([name, value]) => {
      const sign = name.endsWith("降权") ? "−" : "+";
      return `<li>${esc(name)} ${sign}${esc(value)}</li>`;
    }).join("");
    const scoreReasons = item.scoreReasons.length
      ? item.scoreReasons.map((reason) => `<li>${esc(reason)}</li>`).join("")
      : "<li>旧版归档未保存评分分项。</li>";
    const detailsId = `details-${esc(item.id)}-${index}`;
    const key = itemKey(item);
    const opened = state.expandedKeys.has(key) ? " open" : "";
    const visual = item.image ? `<figure class="story-visual"><img src="${esc(item.image)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer"></figure>` : "";
    const detailContent = item._compact
      ? '<div class="detail-loading">展开后将按需读取当期归档中的完整来源、关键事实与评分解释。</div>'
      : `<div class="detail-grid">
          <section><h4>关键事实</h4><ul>${item.keyFacts.map((fact) => `<li>${highlightText(fact)}</li>`).join("")}</ul><h4>为什么重要</h4><p>${esc(item.why)}</p></section>
          <section><h4>来源与置信度</h4><p>${esc(item.confidenceReason)}</p><ul class="source-list">${sources || "<li>没有可用来源链接</li>"}</ul></section>
          <section><h4>重要度为什么是 ${item.score}</h4><ul>${scoreReasons}</ul>${components ? `<ul class="score-components">${components}</ul>` : ""}<p>重要度用于排序，不是对报道真伪的概率判断。</p></section>
        </div>`;
    return `<article class="story" id="${esc(anchorId(item))}" data-key="${esc(key)}">
      <span class="rank">${String(index + 1).padStart(2, "0")}</span>
      <div class="story-main${item.image ? " has-image" : ""}">${visual}<div class="story-copy">
        <div class="meta">
          <span class="cat" data-category="${esc(item.category)}">${esc(item.category)}</span>
          <b>${esc(item.source)}</b><span>${esc(item.country)}</span><span>${esc(formatDate(item.publishedAt))}</span>
          ${item.editionDate ? `<span>${esc(item.editionDate)} 版</span>` : ""}
          <span class="confidence" data-confidence="${esc(item.confidence)}">置信度 ${esc(item.confidence)}</span>
        </div>
        <h3>${highlightText(item.title)}</h3>${original}<p class="summary">${highlightText(item.summary)}</p>
        <div class="tags">${item.tags.map((tag) => `<span>${esc(tag)}</span>`).join("")}</div>
      </div></div>
      <div class="story-side">
        <div class="score"><b>${item.score ?? "—"}</b><small>${esc(item.scoreBasis)}</small></div>
        <div class="story-actions">
          <button type="button" data-bookmark title="${saved ? "取消收藏" : "收藏"}" aria-label="${saved ? "取消收藏" : "收藏"}">${saved ? "★" : "☆"}</button>
          <button type="button" data-share title="复制本条链接" aria-label="复制本条链接">⌁</button>
          ${item.url ? `<a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer" title="打开主来源" aria-label="打开主来源">↗</a>` : ""}
        </div>
      </div>
      <details class="details" id="${detailsId}" data-details-key="${esc(key)}"${opened}>
        <summary>${item._compact ? "加载完整详情" : "展开关键事实、来源与评分解释"}</summary>
        ${detailContent}
      </details>
    </article>`;
  }

  function renderStories() {
    const viewport = captureViewportAnchor();
    const saved = bookmarkSet();
    const visible = viewFilteredItems(true).sort((a, b) => state.sort === "latest"
      ? new Date(b.publishedAt) - new Date(a.publishedAt)
      : Number(b.score ?? -1) - Number(a.score ?? -1) || new Date(b.publishedAt) - new Date(a.publishedAt));
    state.visible = visible.slice(0, 200);
    const noteParts = [`显示 ${state.visible.length} 条`];
    if (state.view === "history" && state.query) noteParts.push("按月分片的跨日期索引");
    if (state.view === "watchlist") noteParts.push(`${state.watchwords.length} 个关注词`);
    $("resultNote").textContent = noteParts.join(" · ");
    if (!state.visible.length) {
      const message = state.view === "watchlist" && !state.watchwords.length
        ? "先添加一个关注词，匹配结果会显示在这里。"
        : state.view === "bookmarks" ? "尚未收藏新闻。点击新闻卡片上的 ☆ 即可收藏。"
          : "没有匹配的新闻，请更换分类、日期或搜索词。";
      $("stories").innerHTML = `<div class="empty"><b>暂无结果</b>${esc(message)}</div>`;
    } else {
      const grouped = state.view === "watchlist" || (state.view === "history" && state.query);
      let previousEdition = "";
      $("stories").innerHTML = state.visible.map((item, index) => {
        const heading = grouped && item.editionDate !== previousEdition
          ? `<h3 class="edition-group">${esc(item.editionDate || "日期未知")} 版</h3>` : "";
        previousEdition = item.editionDate;
        return heading + renderStory(item, index, saved.has(itemKey(item)));
      }).join("");
    }
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
    renderBrief();
    renderWatchwords();
    renderFilters();
    renderStories();
    const report = state.currentReport || state.latestReport;
    $("dataNote").textContent = report?.generatedAt
      ? `数据生成于 ${formatDate(report.generatedAt)}；军事、冲突与前沿技术信息请优先核验一手来源。`
      : "当前视图没有远程日报元数据。";
    syncUrl();
  }

  async function switchView(view, options = {}) {
    if (!VIEWS.has(view)) return;
    state.view = view;
    state.category = "全部";
    if (view === "latest") {
      state.currentReport = state.latestReport;
      state.items = state.latestReport?.items || [];
      state.editionDate = state.latestReport?.editionDate || "";
    } else if (view === "history") {
      await ensureArchiveIndex(Boolean(options.bypassCache));
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
    if (type === "email") {
      $("dialogEyebrow").textContent = "DAILY EMAIL DIGEST";
      $("dialogTitle").textContent = "每日邮件推送";
      $("dialogContent").innerHTML = `<p>邮件由 GitHub Actions 在日报成功生成后，通过管理员配置的 SMTP 账户发送。收件人地址只存放在加密的 GitHub Secrets 中，不会出现在网页或源码里。</p><ol><li>在仓库 Actions Secrets 配置 <code>SMTP_HOST</code>、<code>SMTP_USERNAME</code>、<code>SMTP_PASSWORD</code>、<code>EMAIL_FROM</code> 和 <code>EMAIL_TO</code>。</li><li>可选配置 <code>SITE_URL</code>，让邮件中的“查看日报”链接指向正式域名。</li><li>手动运行一次 Daily news update 验证邮件。未配置时流程会安全跳过，不影响网站更新。</li></ol><p>普通访问者可以通过页面顶部的 <a href="./feed.xml">Atom 订阅</a>在阅读器中接收更新，无需提交邮箱。公开网页仍不开放匿名邮件登记，以避免邮箱收集、滥发和合规风险；管理员可在 <code>EMAIL_TO</code> 中维护多个收件人。</p>`;
    } else {
      $("dialogEyebrow").textContent = "SCORING METHODOLOGY";
      $("dialogTitle").textContent = "评分与置信度如何理解";
      $("dialogContent").innerHTML = `<ul><li><b>重要度：</b>综合基础分、来源权重、主题优先级、时效、影响词、主题相关性、描述完整度和多源印证，并扣除评论、播客等编辑降权。</li><li><b>AI 编辑分：</b>启用 AI 时，模型只可依据候选标题、描述、来源和时间重新选择与评分；规则分仍作为解释性参考。</li><li><b>置信度：</b>只反映收录来源权重和独立来源数量，不是“为真概率”。“待核验”意味着当前仅有单一来源。</li><li><b>关键事实：</b>必须能由候选元数据直接支持；任何重要决定仍应打开来源并寻找一手文件。</li></ul>`;
    }
    $("infoDialog").showModal();
  }

  let searchTimer;
  async function handleSearch(value) {
    state.query = clean(value);
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
    const viewButton = event.target.closest("[data-view]");
    if (viewButton) { await switchView(viewButton.dataset.view); return; }
    const categoryButton = event.target.closest("[data-category]");
    if (categoryButton?.closest("#filters")) {
      state.category = categoryButton.dataset.category;
      renderFilters(); renderStories(); return;
    }
    const bookmarkButton = event.target.closest("[data-bookmark]");
    if (bookmarkButton) { toggleBookmark(bookmarkButton.closest(".story").dataset.key); return; }
    const shareButton = event.target.closest("[data-share]");
    if (shareButton) { await shareStory(shareButton.closest(".story").dataset.key); return; }
    const removeWord = event.target.closest("[data-remove-word]");
    if (removeWord) {
      state.watchwords = state.watchwords.filter((word) => word !== removeWord.dataset.removeWord);
      writeStorage(WATCH_KEY, state.watchwords);
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
    const item = state.visible.find((candidate) => itemKey(candidate) === key);
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

  $("search").value = state.query;
  $("search").addEventListener("input", (event) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { handleSearch(event.target.value); }, 180);
  });
  document.querySelectorAll("[data-sort]").forEach((button) => button.addEventListener("click", () => {
    state.sort = button.dataset.sort;
    document.querySelectorAll("[data-sort]").forEach((item) => item.classList.toggle("active", item === button));
    renderStories();
  }));
  $("editionPicker").addEventListener("change", async (event) => {
    state.query = ""; $("search").value = "";
    await switchView("history", { date: event.target.value });
  });
  [$("previousEdition"), $("nextEdition")].forEach((button) => button.addEventListener("click", async () => {
    if (!button.dataset.date) return;
    state.query = ""; $("search").value = "";
    await switchView("history", { date: button.dataset.date });
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
    state.archiveIndex = null; state.searchManifest = null; state.searchItems = null; state.editionCache.clear();
    await loadLatest(true, true);
    await switchView(state.view, { date: state.editionDate, bypassCache: true });
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
  $("emailBtn").addEventListener("click", () => openDialog("email"));
  $("themeBtn").addEventListener("click", () => applyTheme(state.theme === "dark" ? "light" : "dark", true));
  $("scoringHelp").addEventListener("click", () => openDialog("scoring"));
  document.querySelector("[data-close-dialog]").addEventListener("click", () => $("infoDialog").close());
  $("infoDialog").addEventListener("click", (event) => { if (event.target === $("infoDialog")) $("infoDialog").close(); });
  $("alertClose").addEventListener("click", hideAlert);
  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) {
      event.preventDefault(); $("search").focus();
    }
  });

  async function init() {
    applyTheme(state.theme);
    $("stories").innerHTML = '<div class="loading"></div><div class="loading"></div>';
    await loadLatest();
    await ensureArchiveIndex();
    await switchView(initialView, { date: initialDate });
    scrollToInitialHash();
    if ("serviceWorker" in navigator && location.protocol.startsWith("http")) {
      navigator.serviceWorker.register("./sw.js").catch(() => { /* offline support is optional */ });
    }
  }

  init().catch((error) => {
    state.items = [];
    showAlert("failed", "页面初始化失败", clean(error?.message, "未知错误"));
    renderAll();
  });
})();
