# Changelog

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
