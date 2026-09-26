# News Quality and Daily Deep Read Implementation Plan

> **For agentic workers:** Use the dispatching-parallel-agents workflow for the independent evidence, event identity, and source audit modules; the primary worker owns integration and the daily article. Keep edits inside the owned files and run meaningful regression tests.

**Goal:** Ship grounded summaries, measurable coverage, stable events, and an illustrated daily analysis tab.

**Architecture:** Preserve the current static publishing pipeline. Add pure evidence and event modules; integrate them into `update_news.py`, and generate a validated daily article consumed by the existing browser app.

**Tech Stack:** Python 3.11+ standard library, native HTML/CSS/JavaScript, unittest, Node VM, GitHub Actions and Cloudflare.

**Spec:** `docs/superpowers/specs/2026-09-21-news-quality-design.md`

## Global Constraints

- Preserve the simplified Chinese reading interface and collapsed event timelines.
- Exclude China as the primary news subject using the existing shared content policy; paper nationality is not a filter.
- Python 3.11+ standard library and plain browser JavaScript; no new service, database, paid data subscription, or model provider.
- Only public article evidence; no access-control bypass, fabricated facts, synthetic news illustrations, or forced candidate counts.
- Preserve published article anchors, archive dates, and existing news IDs. New event logic must not trust broad historical similarity as proof of event identity.
- GitHub Connector handles remote source mutations. Deploy via the existing Cloudflare workflow after checks.

## Review Focus

- A long unrelated article embedded alongside the true short article must not dominate evidence selection (Task 1).
- Weekend/partial-source outages must not inflate effective candidate counts or hide shortfalls (Task 2).
- Recurrent attacks/launches with generic vocabulary must remain distinct across dates and objects (Task 3).
- Existing broad legacy event groups must not absorb newly matching topic-only articles (Task 3).
- AI article text with unknown evidence IDs, bad URLs, omitted events, or mismatched date must fall back safely (Task 4).

### Task 1: Evidence selection and integration

**Files:** Create `scripts/news_evidence.py`, `tests/test_news_evidence.py`; modify `scripts/update_news.py` and its integration tests.

**Interfaces:** `select_relevant_evidence(title: str, lead: str, page: str) -> dict` returns `text`, `paragraphs`, `status`, `candidateCount`, `selectedCount`, `reason`. The pipeline stores selected text in `Article.description` and quality metadata separately; source text never becomes public full text.

- [x] Add a failing case with a rocket launch headline and a much longer unrelated war article in the page. Assert that selected text includes mission evidence and excludes the war article.
  ```python
  result = select_relevant_evidence('NASA launches Europa Clipper', '', page)
  self.assertIn('Europa Clipper', result['text'])
  self.assertNotIn('football', result['text'])
  ```
- [x] Run `python -m unittest discover -s tests -p test_news_evidence.py -v`; confirm missing behavior.
- [x] Implement title-aware body/paragraph selection, ordered evidence budgets and honest fallback.
- [x] Integrate into feed and article enrichment and LLM prompts; bump summary revision; verify cached evidence cannot bypass filtering.
- [x] Run evidence tests and all regression tests; commit the complete unit.

### Task 2: Sources, collection accounting and editorial mix

**Files:** Modify `config/news_config.json`, `scripts/update_news.py`; create `scripts/audit_sources.py`, `tests/test_source_coverage.py` and a checked audit summary.

**Interfaces:** `collect_rss(config, now)` still returns Articles and places source diagnostics in the caller's collection report. The audit consumes the same eligibility/classification/deduplication code and emits actual counts, never LLM output.

- [x] Add failing acquisition tests for successful, empty, malformed and unavailable feeds, including Atom and RDF dates.
  ```python
  self.assertEqual(report['qualifiedCandidateCount'], 2)
  self.assertEqual(report['activeSourceCount'], 1)
  ```
- [x] Probe current and candidate official feeds; retain working endpoints with clear topic scope and bounded HTTP reads.
- [x] Add per-feed counts and errors, uncapped qualified totals, balanced candidate shortlisting and a combined conflict/military cap with an honest scarcity fallback.
- [x] Run a reproducible real 24-hour audit and record achieved counts and category coverage.
- [x] Run offline acquisition/selection tests and full suite; commit.

### Task 3: Event identity

**Files:** Create `scripts/event_identity.py`, `tests/test_event_identity.py`; modify wrappers/registry persistence in `scripts/update_news.py` and both workflows.

**Interfaces:** `same_event(first: dict, second: dict) -> bool`; `assign_event_ids(items: list[dict], previous_registry: dict, config: dict) -> None`; `event_identity_record(item: dict) -> dict` provides bounded matching evidence for persistence. Dicts accept `originalTitle` or `title`, `publishedAt`, `url`, `id`, and `eventId`.

- [x] Add failing paraphrase, different mission number, distant repeated attack, same-day order invariance, cross-day follow-up and legacy topic-only cases.
  ```python
  assign_event_ids([first, paraphrase], {}, {})
  self.assertEqual(first['eventId'], paraphrase['eventId'])
  self.assertNotEqual(first['eventId'], unrelated['eventId'])
  ```
- [x] Implement conservative discriminative matching and stable registry assignment with explicit decision metadata.
- [x] Replace title-only dedup and history-score identity assignment; populate stream and daily consistently and persist qualified stream events on every update.
- [x] Test cross-run persistence and registry boundedness with real pipeline outputs; commit.

### Task 4: Daily illustrated article and browser tab

**Files:** Create `scripts/daily_deepread.py`, `tests/test_daily_deepread.py`; modify `update_news.py`, app.js, styles.css, index.html, workflows and README.

**Interfaces:** A versioned `deepread.json` contains editionDate, generatedAt, headline, introduction, sections with eventIds/newsIds/source URLs and images, conclusion, generationStatus and counts. `build_daily_deepread(items, config, now, runtime, request_json)` validates evidence linkage and returns a publishable fallback on provider failure.

- [x] Add failing tests for distinct-event selection, missing AI sections, unknown citation IDs, invalid image/link protocols and a sparse edition.
  ```python
  self.assertEqual(len({event['eventId'] for event in article['events']}), article['eventCount'])
  self.assertTrue(all(source['url'].startswith('https://') for source in article['sources']))
  ```
- [x] Generate structured evidence-linked Chinese sections, a coherent introduction and conclusion; retain exact canonical source/image metadata from selected events.
- [x] Add the tab, readable article layout, anchored contents, source/image captions, date archive support and loading/error fallback without exposing scoring internals.
- [ ] Run renderer tests, complete offline fixture pipeline, full suite and browser interaction checks.
- [ ] Publish through Connector, wait for CI and data regeneration, verify production evidence/event/article outputs and record limitations.

## Execution rulings

- The user's four requested outcomes authorize implementation. Higher-level autonomy instructions take precedence over redundant skill approval handoffs.
- Use an external task-specific git worktree to preserve the previous completed work without adding tool directories to the production repository.
- Independent pure modules can be developed concurrently; only the primary worker changes `update_news.py`, app assets, workflows and integration docs.
- Do not promise the 100–300 daily target from a single observed collection; ship measured coverage and its gap honestly.
