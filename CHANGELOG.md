# Changelog

## Unreleased — Event intelligence layer

- Fixed the three highest-value product debts: Top 3 now performs event/category/source diversity selection, rule-mode key facts never repeat the summary, and the application shell no longer needs a manually synchronized release number across HTML, assets and Service Worker caches.
- Added persistent `eventId` assignment and a 365-day event registry with cross-edition timelines, source networks, stage metadata and related research.
- Added a static weekly convergence report and robust 30-day anomaly detection for category/entity reporting volume, including minimum independent-source safeguards.
- Added typed, scored news–paper links in both directions using only collected titles, abstracts, summaries, tags and research areas.
- Added evidence/dispute matrices and a persistent, verifiable forecast ledger with due dates, validation signals and open/due status.
- Rebuilt the homepage intelligence layer around weekly event lines and anomaly signals; the lead story now uses a category-aware gradient and a brightness-safe image overlay, while secondary spotlights may show lazy-loaded thumbnails.
- Bumped public data contracts to daily/status schema 9, stream schema 5 and research schema 4; added `events.json`, `weekly.json`, weekly archives and `signals.json` to the daily workflow contract.
- The daily refresh gate now treats an older public schema as an upgrade requirement, so a same-day release regenerates data instead of incorrectly skipping because ten older-contract items already exist.

## 2.0.3 — Reliable daily scheduling and same-day health warning

- Replaced the top-of-hour daily schedule with a 07:07 China Standard Time primary run and an 08:37 recovery run to reduce GitHub Actions queue loss and delay.
- Added an idempotent preflight gate: scheduled recovery runs skip a healthy 10-item edition for the current Shanghai date, while manual forced runs remain available.
- Added a narrow, idempotent `main` push trigger for changes to `daily-news.yml`, allowing this reliability release to regenerate a missing current edition without duplicating an edition that finished while the release was in progress or creating a data-commit loop.
- Added unit coverage for stale, healthy, short, failed, manual and workflow-change refresh decisions.
- The frontend now raises a clear “今日日报尚未生成” warning after 08:15 China Standard Time when the newest edition is still older than the current Shanghai date.
- Bumped the application shell and Service Worker cache boundary to v2.0.3.

## 2.0.2 — Readability, accessibility and China timezone

- Replaced the sub-11px-heavy type scale with explicit tokens: article and detail copy is at least 14px, supporting copy is 12–13px, and metadata is 11px. Only two Latin uppercase micro-labels remain at 8px.
- Darkened the light-theme muted text token to `#4f5c63` (6.21:1 against the paper background) and raised contrast for brief text, metadata, category labels and dark-theme secondary text.
- Put the system UI font stack first so Chinese and Latin glyphs use the platform's matched type family without an unserved Inter dependency.
- Reduced Chinese heading tracking to `-0.01em` or zero, and limited wide uppercase tracking to the remaining editorial labels.
- Added a guaranteed dark safety layer and stronger text contrast over unpredictable lead-story images.
- Added explicit mobile heading and body sizing, a v2.0.2 asset/Service Worker cache boundary and typography regression coverage.
- Switched edition dates and both scheduled workflows to `Asia/Shanghai`; the daily brief now runs at 08:00 China Standard Time, while archived reports keep and display their original timezone metadata.

## 2.0.1 — Production custom domain

- Switched canonical, Open Graph and Twitter sharing metadata to `https://newsfrontier.top/`.
- Updated feed/email generation defaults, production checks and operator documentation to use the public custom domain.
- Added a regression test that prevents the former `workers.dev` hostname from returning to production metadata or configuration.

## 2.0.0 — Historical context and quieter information hierarchy

- Shortened the homepage hero and view descriptions so the feed, evidence and navigation carry the information hierarchy instead of explanatory copy.
- Added an optional lead-story backdrop using the article's own image with a responsive contrast overlay and a deterministic no-image fallback; no unstable wallpaper endpoint is required.
- Added explainable historical association across the bounded archive using mixed Chinese/English token overlap, tags and same-event title signals; category alone cannot create a link and current/future editions are excluded.
- Added per-story timelines, association reasons and scores, cautious near-/mid-term observation points, archive deep links and a clear non-causality disclaimer.
- Constrained the optional model stage to summarize only program-selected historical evidence. Structured batching, split retries and dedicated diagnostics are independent of selection and translation, while rule summaries remain available on provider failure.
- Added dark/mobile styles, search integration, daily/status schema v8, workflow contract checks and a v2.0 Service Worker cache boundary.

## 1.9.0 — AI ranking with deterministic diversity

- Changed the daily model task from directly choosing ten stories to independently scoring candidate importance; the program now blends AI and rule scores and always applies topic/domain quotas itself.
- Added `selectionStrategy`, `selectionStatus`, `selectionNotices` and before/after diversity diagnostics, including adjusted IDs, quota counts, scored coverage and blend weights.
- Treats normal quota-driven replacements as a neutral “diversity adjusted” state instead of reporting an AI failure; genuine provider or structured-output failures still fall back to the rule Top 10.
- Preserved independent Chinese translation after either constrained AI ranking or rule fallback.
- Stopped stale research retention from carrying old batch-failure warnings forever; only the current “collection empty, previous papers retained” state remains public.
- Bumped the daily/status schema and Service Worker cache boundary to v1.9.

## 1.8.0 — Independent selection and Chinese translation

- Split the daily pipeline into two independent stages: Top 10 selection first, then Chinese translation/editing of the final selected set.
- When AI selection fails parsing or diversity validation, the deterministic Top 10 is retained and still sent through the Chinese translation stage.
- Added `selectionMethod`, `translationStatus` and `translatedItemCount` as separate public health fields, with dedicated selection/translation warnings and diagnostics.
- Added five-item resilient daily translation batches with split retries and per-ID completion reasons.
- Reused unchanged full-stream translations by stable news ID, provider, model and original title before requesting new daily translations.
- Changed Top 10/full-stream merging so translated Chinese text always wins over untranslated rule fields, while ranking and evidence metadata still come from the daily item.
- Replaced the hard-coded OpenAI diversity error with the active provider's public name.
- Bumped daily/stream schemas and the Service Worker cache boundary for the new contracts.

## 1.7.0 — Resilient AI batches and conflict-safe publishing

- Reduced DeepSeek stream batches from 12 to 6 items and research batches from 10 to 5 items.
- Replaced model-facing article and paper IDs with one-based sequence indexes, then restored stable IDs after local validation.
- Added recursive split retries for only the missing records, while retaining a two-failure circuit breaker for provider outages or empty responses.
- Added structured translation diagnostics with requested/completed/missing counts, missing IDs, per-item reasons, retry counts and a machine-readable completion reason.
- Surfaced concise retry diagnostics in the stream and research health banners without exposing API keys or raw prompts.
- Kept both data workflows under one concurrency lock and added three conflict-safe fetch/rebase/push attempts when `main` changes during a long collection run.

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
