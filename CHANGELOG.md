# Changelog

## 1.6.0 — Personal research signals and DeepSeek translation

### Research discovery

- Added up to 20 browser-local Chinese or English paper keywords, a dedicated personal paper stream, persistent scope selection, match counts and in-card highlighting.
- Added administrator-managed `research.collection_keywords`; each definition searches arXiv title and abstract fields in addition to the existing category queries, then merges results by arXiv ID.
- Published system collection keywords in `research.json` and the research UI so readers can distinguish server-side discovery from local filtering.
- Keyword hits now boost research relevance transparently and appear in the paper metadata and score explanation.

### Chinese translation and resilience

- Added a provider adapter for DeepSeek Chat Completions and OpenAI Responses. DeepSeek defaults to `deepseek-v4-flash`, JSON output and disabled thinking for deterministic translation tasks.
- Added server-side DeepSeek translation for Top 10 news, up to 120 full-stream items and up to 60 research papers; API keys never enter static assets or generated payloads.
- Split stream and research translation into bounded batches, retained successful batches on partial failure, and exposed provider, model, translated count and warnings in public status data.
- Reused translations for unchanged stream items to reduce recurring API cost and latency.
- Added dedicated GitHub Actions Secret/Variable wiring, DeepSeek setup documentation, offline provider tests and a v1.6 Service Worker cache boundary.

## 1.5.0 — Full stream, research radar and homepage hierarchy

### Information coverage

- Added a separately cached 24-hour qualified stream, capped at 300 items and refreshed every three hours without replacing the daily Top 10.
- Added 6/12/24-hour, source, topic and keyword filters plus incremental rendering for the larger stream payload.
- Added an arXiv-backed seven-day research radar for AI, robotics/autonomy, space science, quantum and advanced materials.
- Research entries have their own relevance score and schema, including authors, categories, PDF link and explicit preprint/peer-review status.
- Optional AI editing produces Chinese paper titles, summaries, research questions, methods, findings and limitations; metadata fallback remains usable and visible.

### Information hierarchy and operations

- Rebuilt the homepage around a Top 3 must-read layer, a compact executive brief and the complete Top 10.
- Added dedicated research cards, Top 10 badges inside the full stream, source filters, result counts and “load more” controls.
- Added `stream-status.json`, cache policies for the new payloads, a v1.5 offline cache, pipeline tests and a three-hour stream workflow.
- Daily status now records stream and research counts plus research editorial warnings.
- Expanded the qualified stream from 8 to 18 international feeds, adding ESA, FlightGlobal, C4ISRNET, Defense One, DARPA, BBC World, Al Jazeera, TechCrunch AI, Google DeepMind and Hugging Face.
- Fixed low-volume daily failures with a three-stage recovery path: reuse a validated stream cache no older than eight hours, progressively backfill from 36/48/72-hour windows with an explicit freshness penalty, then relax topic/source quotas in tiers.
- Supplemental or quota-relaxed stories are marked in the payload and UI; `status.json` records coverage state, fresh/supplemental counts and the effective lookback window.
- The 24-hour full stream remains semantically strict and may contain fewer than ten items; only the daily brief is required to contain exactly ten.

## 1.4.0 — Data quality, scalable archive and reader experience

### Data and reliability

- Normal page loads now reuse clean URLs, HTTP cache directives and ETags; only explicit refresh bypasses caches.
- Production smoke workflow checks CSP, security headers, ETag and non-overlapping `Cache-Control` values.
- Search data is reduced to searchable fields and split into monthly `search-YYYY-MM.json` shards; full details load from the daily archive on demand.
- Reuters/AP syndication groups prevent multiple republisher domains from inflating independent-source confidence.
- Invalid publication dates fall back to the lookback boundary and receive an explicit score penalty.
- AI HTTP/structured-output processing retries once, increases the output budget and applies hard category/domain diversity validation.
- AI fallback reasons are published in `status.json.warnings` and shown in the UI.
- Daily checkout is shallow; old archive migration to R2 or a data branch remains a later scale milestone.

### Reader experience

- Expanded details and viewport anchors survive card rerenders.
- Added lazy-loaded thumbnails, Atom feed, per-story anchors/copy links and a static social sharing card.
- Published times use the reader's local timezone with an explicit timezone suffix; edition dates remain Asia/Tokyo.
- Added dark mode, Service Worker offline fallback, search highlighting and edition grouping for cross-date results.

### Deliberately deferred

- Public email signup still requires a consent-aware backend, double opt-in and unsubscribe handling; Atom is the anonymous subscription path.
- Per-story dynamic social cards require a server-side/edge rendering path; v1.4 uses one static site card.
- R2/D1 migration is not justified at the current archive size; the v1.4 JSON contracts preserve that future migration path.
