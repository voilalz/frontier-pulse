# News quality and Daily Deep Read

The user requests four improvements: align summaries with the actual story, grow effective international news coverage toward 100–300 qualified candidates per day with more AI/aerospace/unmanned/frontier reporting, make event identities precise and persistent, and add a tab containing an illustrated daily analysis of 10–15 important events.

## Constraints

- Preserve the simplified Chinese reading interface and collapsed event timelines.
- Exclude China as the primary news subject using the existing shared content policy; paper nationality is not a filter.
- Python 3.11+ standard library and plain browser JavaScript; no new service, database, paid data subscription, or model provider.
- Only public article evidence; no access-control bypass, fabricated facts, synthetic news illustrations, or forced candidate counts.
- Preserve published article anchors, archive dates, and existing news IDs. New event logic must not trust broad historical similarity as proof of event identity.
- GitHub Connector handles remote source mutations. Deploy via the existing Cloudflare workflow after checks.

## 1. Evidence selection

Introduce a pure paragraph-selection module. Parse article containers and JSON-LD as separate candidates; compare their headline and paragraphs with the feed headline. Reject unrelated bodies, navigation, promotions, recommendations and mismatched structured articles. Rank paragraphs by distinctive title terms and entities, retain qualifying paragraphs in source order, and enforce a bounded evidence budget. Missing or rejected bodies use a relevant feed lead; an unrelated lead becomes title-only evidence. Record evidence status and paragraph counts internally. LLM input receives only selected evidence with explicit prohibition on inventing missing details. Bump summary revision to invalidate prior cached summaries.

## 2. Effective source coverage

Audit live RSS/Atom responses, entry counts, current 24-hour items, topical/policy exclusions and duplicates. Expand verified first-party and established specialist feeds in AI, space, unmanned systems and frontier science. Recognize explicitly scoped specialist feeds while still filtering unrelated general news. Keep per-source acquisition diagnostics and collection totals in data/status, with a reproducible audit command. Count qualified unique candidates before display/translation caps; do not report configured source count as effective coverage. Favor technical topic coverage in the daily shortlist and selection. A real shortfall remains visible in operational data and is not padded with stale or duplicate stories.

## 3. Event identity

Introduce a pure event matching module for both same-day and cross-day matching. Match immutable article URLs/IDs first, then require discriminative entity/object/action and time evidence. Reject different locations, product/mission identifiers and distant repeated generic events. Ambiguous candidates stay separate. Historical context remains related background only. Stable event IDs are reused from registry representatives, with current batch members assigned together deterministically. Record matching version, representative evidence, decision reason and aliases where needed. Update event registry from the qualified stream, including stream-only runs, so events persist beyond Top 10. Migrate conservatively: exact legacy memberships remain traceable, but legacy topic links cannot propagate merges.

## 4. Daily Deep Read

Add the “每日深读” tab (`?view=deepread`). Select 10–15 distinct, policy-eligible events from the current qualified news pool with technical topic and source diversity. Produce an integrated Chinese article with title, introduction, thematic sections, individual event reports, bounded analysis, follow-up questions and sources. Use existing public news thumbnails with source attribution and a graceful no-image layout. Each factual section is linked to its evidence IDs; model output cannot create or replace news sources or images. Validate article structure and evidence references; preserve a useful fact-based editorial fallback when AI is unavailable. Do not pretend a short edition contains 10 events. Archive each daily article and keep the current edition date visible.

## Acceptance

Offline tests reproduce title/body mismatch, multi-article JSON-LD, missing evidence, temporal and entity false merges, duplicate paraphrases, stable cross-day identities, degraded source responses, candidate accounting, longform citations, policy filtering and safe browser rendering. A fixture pipeline validates all output files. A real public-source audit records achieved coverage. CI, deployment and browser navigation must pass before completion is claimed.
