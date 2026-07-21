(() => {
  "use strict";

  const ENDPOINTS = {
    latest: "./data/news.json",
    stream: "./data/stream.json",
    streamStatus: "./data/stream-status.json",
    research: "./data/research.json",
    status: "./data/status.json",
    archive: "./data/archive/index.json",
    search: "./data/archive/search-index.json",
  };
  const CATEGORIES = ["AI", "航空航天", "军事动态", "局部冲突", "前沿技术", "无人系统"];
  const VIEWS = new Set(["latest", "stream", "research", "history", "bookmarks", "watchlist"]);
  const PAGE_SIZE = 24;
  const CACHE_KEY = "fp-last-good-report-v2";
  const STREAM_CACHE_KEY = "fp-last-good-stream-v1";
  const RESEARCH_CACHE_KEY = "fp-last-good-research-v1";
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
  const initialRange = [6, 12, 24].includes(Number(params.get("range"))) ? Number(params.get("range")) : 24;
  const storedResearchScope = readStorage(RESEARCH_SCOPE_KEY, "all") === "mine" ? "mine" : "all";
  const initialResearchScope = params.get("scope") === "mine" ? "mine" : storedResearchScope;
  const legacyBookmarks = readStorage("fp-bookmarks", []).filter((item) => typeof item === "string");
  const storedBookmarks = readStorage(BOOKMARK_KEY, []).filter((item) => item && typeof item === "object");

  const state = {
    view: initialView,
    query: clean(params.get("q")),
    category: "全部",
    source: clean(params.get("source"), "全部"),
    rangeHours: initialRange,
    sort: "score",
    editionDate: initialDate,
    latestReport: null,
    streamReport: null,
    researchReport: null,
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
      contentType: clean(raw.contentType, "news"),
      title: clean(raw.title),
      originalTitle: clean(raw.originalTitle || raw.title),
      summary,
      keyFacts: (Array.isArray(raw.keyFacts) ? raw.keyFacts : [summary]).map((fact) => clean(fact)).filter(Boolean).slice(0, 4),
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

  function normalizeCollection(payload, type) {
    if (!payload || typeof payload !== "object" || !Array.isArray(payload.items)) {
      throw new Error(`${type === "paper" ? "论文" : "动态"}数据文件不可用`);
    }
    const limit = type === "paper" ? 200 : 500;
    return {
      ...payload,
      generatedAt: clean(payload.generatedAt),
      items: payload.items.slice(0, limit).map((item, index) => normalizeItem({ ...item, contentType: item.contentType || type }, index)),
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
    const supplemented = state.pipelineStatus?.coverageStatus === "supplemented"
      || Number(state.pipelineStatus?.supplementalItemCount) > 0
      || report?.items?.some((item) => item.isSupplemental || item.diversityRelaxed);
    if (supplemented) {
      badge.textContent = "安全补足";
      badge.classList.add("warning");
      showAlert("warning", "本期 Top 10 已使用透明补全", warnings.join("；")
        || "24 小时候选量或分布不足，系统使用了明确标记的扩展窗口或分级配额补足；没有生成虚构新闻。");
      return;
    }
    if (state.pipelineStatus?.editorialStatus === "fallback") {
      badge.textContent = "规则回退";
      badge.classList.add("warning");
      showAlert("warning", "日报已更新，但 AI 编辑发生降级", warnings.join("；") || state.pipelineStatus.message || "已使用规则模式生成本期内容。");
      return;
    }
    if (warnings.length) {
      badge.textContent = "有警告";
      badge.classList.add("warning");
      showAlert("warning", "日报已更新，但存在运行警告", warnings.join("；"));
      return;
    }
    badge.textContent = "在线";
    hideAlert();
  }

  function updateViewHealth() {
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
      const translationWarnings = [
        ...(Array.isArray(state.streamReport?.translationWarnings) ? state.streamReport.translationWarnings : []),
        ...(Array.isArray(state.streamStatus?.translationWarnings) ? state.streamStatus.translationWarnings : []),
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
      if (reportAgeHours(state.researchReport) > 36) {
        badge.textContent = "论文已过期";
        badge.classList.add("warning");
        showAlert("warning", "论文雷达可能已经过期", `当前论文数据生成于 ${formatDate(state.researchReport?.generatedAt)}，已超过 36 小时。`);
        return;
      }
      const warnings = [
        ...(Array.isArray(state.researchReport?.warnings) ? state.researchReport.warnings : []),
        ...(Array.isArray(state.pipelineStatus?.researchWarnings) ? state.pipelineStatus.researchWarnings : []),
      ].filter(Boolean);
      const researchEditorialStatus = state.pipelineStatus?.researchEditorialStatus || state.researchReport?.editorialStatus;
      if (["partial", "fallback", "stale"].includes(researchEditorialStatus) || warnings.length) {
        badge.textContent = researchEditorialStatus === "stale" ? "论文未更新"
          : researchEditorialStatus === "partial" ? "论文部分翻译" : "论文规则版";
        badge.classList.add("warning");
        showAlert("warning", researchEditorialStatus === "partial" ? "论文雷达部分批次未完成翻译" : "论文雷达已降级", [...new Set(warnings)].join("；") || "本期保留论文元数据与原始摘要，未完成 AI 中文编辑。");
        return;
      }
      badge.textContent = "论文在线";
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
    if (state.view === "stream" && state.rangeHours !== 24) query.set("range", String(state.rangeHours));
    if (state.view === "stream" && state.source !== "全部") query.set("source", state.source);
    if (state.view === "research" && state.researchScope === "mine" && state.researchKeywords.length) query.set("scope", "mine");
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
      latest: ["DAILY INTELLIGENCE BRIEF", "全球前沿情报，先看最重要的", "每日十条重点事件，先呈现必读内容，再提供证据、来源与评分解释。", "TOP 10 BRIEF", "今日完整 Top 10"],
      stream: ["QUALIFIED FULL STREAM", `过去 ${state.rangeHours} 小时全量动态`, "展示所有通过主题相关性、时间窗、去重和商业内容过滤的合格候选。", "FULL STREAM", "全部合格动态"],
      research: ["RESEARCH RADAR", "前沿论文雷达", "聚合 AI、机器人、无人系统、空间科学、量子与先进材料研究，预印本状态始终明确标注。", "PAPERS & PREPRINTS", "最新研究论文"],
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
    $("spotlightSection").hidden = state.view !== "latest";
    $("researchNotice").hidden = state.view !== "research";
    $("researchKeywordPanel").hidden = state.view !== "research";
    $("rangeControls").hidden = state.view !== "stream";
    $("sourceFilterWrap").hidden = state.view !== "stream";
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

  function valueCounts(items, getter) {
    const counts = Object.create(null);
    items.forEach((item) => {
      const key = clean(getter(item), "其他");
      counts[key] = (counts[key] || 0) + 1;
    });
    return counts;
  }

  function providerLabel(report) {
    const method = clean(report?.method).toLocaleLowerCase();
    const provider = clean(report?.translationProvider || (["deepseek", "openai"].includes(method)
      ? report?.editorialProvider || method : "")).toLocaleLowerCase();
    if (provider === "deepseek") return "DeepSeek V4 Flash";
    if (provider === "openai") return "OpenAI";
    return "";
  }

  function renderBrief() {
    const report = state.currentReport;
    const items = state.items;
    const metricItems = ["stream", "research"].includes(state.view) ? viewFilteredItems(true) : items;
    let headline = report?.brief?.headline;
    let summary = report?.brief?.summary;
    let signals = Array.isArray(report?.brief?.signals) ? report.brief.signals : [];
    const provider = providerLabel(report);
    let method = provider ? `${provider} 编辑 + 规则校验` : report ? "规则评分" : "本机视图";
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
        ? `每 3 小时采集 · ${providerLabel(report) || "AI"} 中文翻译`
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
    $("itemCount").textContent = metricItems.length;
    $("sourceCount").textContent = uniqueSourceCount(metricItems);
    $("categoryCount").textContent = new Set(metricItems.map((item) => state.view === "research" ? item.researchArea : item.category)).size;
    $("itemCountLabel").textContent = state.view === "research" ? "篇论文" : state.view === "stream" ? "条动态" : "重点事件";
    $("sourceCountLabel").textContent = state.view === "research" ? "资料库" : "公开信源";
    $("categoryCountLabel").textContent = state.view === "research" ? "研究方向" : "主题领域";
    $("briefUpdated").textContent = report?.generatedAt ? `生成于 ${formatDate(report.generatedAt)}` : "本机个性化视图";
  }

  function renderSpotlight() {
    if (state.view !== "latest") return;
    const items = (state.latestReport?.items || []).slice(0, 3);
    $("spotlightStories").innerHTML = items.length ? items.map((item, index) => `
      <article class="spotlight-card">
        <div class="spotlight-meta"><b>0${index + 1}</b><span>${esc(item.category)}</span><span>${esc(item.source)}</span>${item.isSupplemental ? `<span class="supplemental-badge">补充观察 · ${item.selectionWindowHours}h</span>` : ""}</div>
        <h3>${highlightText(item.title)}</h3>
        <p>${highlightText(item.summary)}</p>
        <a href="#${esc(anchorId(item))}">查看关键事实与来源 <span aria-hidden="true">↓</span></a>
      </article>`).join("") : '<div class="empty"><b>今日必读暂不可用</b>请检查日报更新状态。</div>';
  }

  function searchableText(item) {
    return [
      item.title, item.originalTitle, item.summary, item.abstract, item.why, item.source, item.country,
      item.researchArea, item.primaryCategory, item.question, item.method, item.findings, item.limitations,
      ...item.authors, ...item.arxivCategories, ...item.collectionKeywords, ...item.keyFacts, ...item.tags,
      ...item.sources.map((source) => source.name),
    ].join(" ").toLocaleLowerCase();
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

  function facetValue(item) {
    return state.view === "research" ? clean(item.researchArea, "前沿研究") : item.category;
  }

  function viewFilteredItems(includeCategory = true, includeSource = true) {
    const query = state.query.toLocaleLowerCase();
    const watchwords = state.watchwords.map((word) => word.toLocaleLowerCase());
    const streamAnchor = new Date(state.streamReport?.generatedAt).valueOf() || Date.now();
    const rangeThreshold = streamAnchor - state.rangeHours * 3_600_000;
    return state.items.filter((item) => {
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
          <span class="cat paper-cat">${esc(item.researchArea || "前沿研究")}</span>
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
        </div>
      </details>
    </article>`;
  }

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
          <section><h4>重要度为什么是 ${item.score}</h4><ul>${scoreReasons}</ul>${components ? `<ul class="score-components">${components}</ul>` : ""}${item.selectionNote ? `<p class="selection-note">${esc(item.selectionNote)}</p>` : ""}<p>重要度用于排序，不是对报道真伪的概率判断。</p></section>
        </div>`;
    return `<article class="story" id="${esc(anchorId(item))}" data-key="${esc(key)}">
      <span class="rank">${String(index + 1).padStart(2, "0")}</span>
      <div class="story-main${item.image ? " has-image" : ""}">${visual}<div class="story-copy">
        <div class="meta">
          <span class="cat" data-category="${esc(item.category)}">${esc(item.category)}</span>
          ${item.isTopStory ? '<span class="top-story-badge">今日 Top 10</span>' : ""}
          ${item.isSupplemental ? `<span class="supplemental-badge">补充观察 · ${item.selectionWindowHours}h</span>` : ""}
          ${item.diversityRelaxed ? '<span class="quota-badge">配额补足</span>' : ""}
          <b>${esc(item.source)}</b><span>${esc(item.country)}</span><span>${esc(formatDate(item.publishedAt))}</span>
          ${item.editionDate ? `<span>${esc(item.editionDate)} 版</span>` : ""}
          <span class="confidence" data-confidence="${esc(item.confidence)}">置信度 ${esc(item.confidence)}</span>
          ${item.translationProvider ? `<span class="translation-badge">${esc(item.translationProvider === "deepseek" ? "DeepSeek 中文" : "AI 中文")}</span>` : ""}
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

  function renderResearchKeywords() {
    const panel = $("researchKeywordPanel");
    if (!panel) return;
    const keywords = state.researchKeywords;
    const mineCount = state.items.filter((item) => item.contentType === "paper" && matchedResearchKeywords(item).length).length;
    $("researchKeywordLimit").textContent = `${keywords.length} / 20`;
    $("allResearchCount").textContent = state.items.filter((item) => item.contentType === "paper").length;
    $("mineResearchCount").textContent = mineCount;
    $("researchKeywordChips").innerHTML = keywords.length
      ? keywords.map((keyword) => `<button class="watch-chip" type="button" data-remove-research-keyword="${esc(keyword)}" title="移除论文关键词">${esc(keyword)}<span>×</span></button>`).join("")
      : '<span class="method-kicker">尚未添加论文关键词</span>';
    document.querySelectorAll("[data-research-scope]").forEach((button) => {
      const active = button.dataset.researchScope === state.researchScope;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
      if (button.dataset.researchScope === "mine") button.disabled = !keywords.length;
    });
    const configured = Array.isArray(state.researchReport?.collectionKeywords)
      ? state.researchReport.collectionKeywords : [];
    $("collectionKeywordChips").innerHTML = configured.length
      ? configured.map((definition) => {
        const label = clean(typeof definition === "string" ? definition : definition?.label || definition?.query);
        const query = clean(typeof definition === "object" ? definition?.query : "");
        return label ? `<span title="${esc(query ? `arXiv 标题/摘要查询：${query}` : label)}">${esc(label)}</span>` : "";
      }).join("")
      : '<span class="method-kicker">管理员尚未配置额外采集词</span>';
  }

  function renderAll() {
    renderViewCopy();
    renderDateControl();
    renderSpotlight();
    renderWatchwords();
    renderResearchKeywords();
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
    if (["stream", "research"].includes(view)) renderViewLoading(view);
    else state.view = view;
    state.category = "全部";
    state.visibleLimit = PAGE_SIZE;
    if (view === "latest") {
      state.sort = "score";
      state.currentReport = state.latestReport;
      state.items = state.latestReport?.items || [];
      state.editionDate = state.latestReport?.editionDate || "";
    } else if (view === "stream") {
      state.sort = "latest";
      await loadStream(Boolean(options.showToast), Boolean(options.bypassCache));
      state.currentReport = state.streamReport;
      state.items = state.streamReport?.items || [];
      state.editionDate = "";
    } else if (view === "research") {
      state.sort = "score";
      await loadResearch(Boolean(options.showToast), Boolean(options.bypassCache));
      state.currentReport = state.researchReport;
      state.items = state.researchReport?.items || [];
      state.editionDate = "";
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
    if (type === "email") {
      $("dialogEyebrow").textContent = "DAILY EMAIL DIGEST";
      $("dialogTitle").textContent = "每日邮件推送";
      $("dialogContent").innerHTML = `<p>邮件由 GitHub Actions 在日报成功生成后，通过管理员配置的 SMTP 账户发送。收件人地址只存放在加密的 GitHub Secrets 中，不会出现在网页或源码里。</p><ol><li>在仓库 Actions Secrets 配置 <code>SMTP_HOST</code>、<code>SMTP_USERNAME</code>、<code>SMTP_PASSWORD</code>、<code>EMAIL_FROM</code> 和 <code>EMAIL_TO</code>。</li><li>可选配置 <code>SITE_URL</code>，让邮件中的“查看日报”链接指向正式域名。</li><li>手动运行一次 Daily news update 验证邮件。未配置时流程会安全跳过，不影响网站更新。</li></ol><p>普通访问者可以通过页面顶部的 <a href="./feed.xml">Atom 订阅</a>在阅读器中接收更新，无需提交邮箱。公开网页仍不开放匿名邮件登记，以避免邮箱收集、滥发和合规风险；管理员可在 <code>EMAIL_TO</code> 中维护多个收件人。</p>`;
    } else {
      $("dialogEyebrow").textContent = "SCORING METHODOLOGY";
      if (state.view === "research") {
        $("dialogTitle").textContent = "论文相关度如何理解";
        $("dialogContent").innerHTML = `<ul><li><b>研究相关度：</b>综合关注领域优先级、标题与摘要的主题命中、系统采集词、摘要完整度和发布时间，仅用于排列阅读顺序。</li><li><b>我的论文关键词：</b>只在当前浏览器中筛选和高亮已采集论文；添加后自动进入专属论文流，不会上传服务器。</li><li><b>系统采集词：</b>由仓库配置直接查询 arXiv 标题与摘要，可发现既有分类候选之外的特定方向。</li><li><b>预印本：</b>arXiv 条目不代表已经同行评审、独立复现或获得学术共同体认可。</li><li><b>中文编辑：</b>配置 DeepSeek 或 OpenAI 时只依据标题与摘要提炼问题、方法、发现和局限；摘要未说明的内容必须明确标注。</li><li><b>研究判断：</b>重要结论应回到完整论文、实验设置、数据和后续评审。</li></ul>`;
      } else {
        $("dialogTitle").textContent = "评分与置信度如何理解";
        $("dialogContent").innerHTML = `<ul><li><b>重要度：</b>综合基础分、来源权重、主题优先级、时效、影响词、主题相关性、描述完整度和多源印证，并扣除评论、播客等编辑降权。</li><li><b>AI 编辑分：</b>启用 AI 时，模型只可依据候选标题、描述、来源和时间重新选择与评分；规则分仍作为解释性参考。</li><li><b>置信度：</b>只反映收录来源权重和独立来源数量，不是“为真概率”。“待核验”意味着当前仅有单一来源。</li><li><b>关键事实：</b>必须能由候选元数据直接支持；任何重要决定仍应打开来源并寻找一手文件。</li></ul>`;
      }
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
  $("researchKeywordForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = $("researchKeywordInput");
    const keyword = clean(input.value).slice(0, 60);
    if (!keyword) return;
    if (state.researchKeywords.some((item) => item.toLocaleLowerCase() === keyword.toLocaleLowerCase())) {
      toast("该论文关键词已存在");
      return;
    }
    if (state.researchKeywords.length >= 20) { toast("最多保存 20 个论文关键词"); return; }
    state.researchKeywords.push(keyword);
    state.researchScope = "mine";
    state.visibleLimit = PAGE_SIZE;
    input.value = "";
    writeStorage(RESEARCH_KEYWORDS_KEY, state.researchKeywords);
    writeStorage(RESEARCH_SCOPE_KEY, state.researchScope);
    renderAll();
    toast("已添加并切换到专属论文流");
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
