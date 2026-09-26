#!/usr/bin/env python3
"""Measure RSS coverage with the production collector, filters and deduplicator.

No article body fetching, LLM calls, cached stories, backfill windows or display
caps are involved. Only verified timestamps inside the exact prior 24 hours
count. JSON contains aggregate diagnostics, never source article text.
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import update_news as news


def summarize_coverage(
    articles: list[news.Article],
    config: dict[str, Any],
    now: datetime,
    diagnostics: list[dict[str, Any]],
) -> dict[str, Any]:
    """Account for every parsed article, with exclusion stages kept disjoint."""
    now = now.astimezone(timezone.utc)
    threshold = now - timedelta(hours=24)
    fresh = [
        article for article in articles
        if not article.date_estimated and threshold <= article.published_at <= now
    ]
    eligible = news.eligible_articles(fresh, config)
    editorial = [
        article for article in eligible
        if not any(
            news.keyword_matches(f"{article.title} {article.description}".lower(), keyword)
            for keyword in config.get("editorial_exclude_keywords", [])
        )
    ]
    audit_config = dict(config, lookback_hours=24)
    qualified = news.score_articles(copy.deepcopy(editorial), audit_config, now, lookback_hours=24)
    unique = news.deduplicate(copy.deepcopy(qualified))
    collected_counts = Counter(article.source for article in articles)
    fresh_counts = Counter(article.source for article in fresh)
    qualified_counts = Counter(article.source for article in qualified)
    contribution_counts = Counter(article.source for article in unique)
    categories = Counter(article.category for article in unique)
    reported = {(row["source"], row["url"]): row for row in diagnostics}
    sources = []
    for feed in config.get("rss_feeds", []):
        name, url = feed["name"], feed["url"]
        row = dict(reported.get((name, url), {
            "source": name, "url": url, "state": "unreported", "fetchedCount": 0, "error": "",
        }))
        row.update({
            "collectedCount": collected_counts[name],
            "freshCount": fresh_counts[name],
            "qualifiedCount": qualified_counts[name],
            "uniqueContributionCount": contribution_counts[name],
        })
        sources.append(row)
    target_min, target_max = 100, 300
    return {
        "auditAt": now.isoformat(),
        "windowStart": threshold.isoformat(),
        "lookbackHours": 24,
        "datePolicy": "Verified publication timestamps only; windowStart <= publishedAt <= auditAt",
        "configuredSourceCount": len(sources),
        "configuredPublisherCount": len({news.domain_from_url(row["url"]) for row in sources}),
        "reachableSourceCount": sum(row["state"] in {"ok", "empty"} for row in sources),
        "failedSourceCount": sum(row["state"] == "error" for row in sources),
        "emptySourceCount": sum(row["state"] == "empty" for row in sources),
        "disabledSourceCount": sum(row["state"] == "disabled" for row in sources),
        "activeSourceCount": len(qualified_counts),
        "activePublisherCount": len({article.domain for article in qualified}),
        "rawEntryCount": sum(row.get("rawEntryCount", 0) for row in sources),
        "truncatedCount": sum(row.get("truncatedCount", 0) for row in sources),
        "fetchedCount": sum(row.get("fetchedCount", 0) for row in sources),
        "collectedCount": len(articles),
        "unknownDateCount": sum(article.date_estimated for article in articles),
        "outsideWindowCount": sum(not article.date_estimated and article.published_at < threshold for article in articles),
        "futureDateCount": sum(not article.date_estimated and article.published_at > now for article in articles),
        "freshCount": len(fresh),
        "policyExcludedCount": len(fresh) - len(eligible),
        "editorialExcludedCount": len(eligible) - len(editorial),
        "topicExcludedCount": len(editorial) - len(qualified),
        "qualifiedBeforeDedupCount": len(qualified),
        "duplicateCount": len(qualified) - len(unique),
        "qualifiedCandidateCount": len(unique),
        "categoryCounts": {category: categories[category] for category in news.CATEGORIES},
        "targetMin": target_min,
        "targetMax": target_max,
        "targetGap": max(0, target_min - len(unique)),
        "targetReached": len(unique) >= target_min,
        "sources": sources,
    }


def run_audit(config: dict[str, Any], now: datetime) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    articles = news.collect_rss(config, now, diagnostics=diagnostics)
    return summarize_coverage(articles, config, now, diagnostics)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "config/news_config.json")
    parser.add_argument("--at", help="UTC ISO timestamp for reproducible window boundaries; defaults to current UTC")
    parser.add_argument("--output", type=Path, help="Write aggregate JSON here instead of stdout")
    args = parser.parse_args()
    now = news.utc_now()
    if args.at:
        try:
            now = datetime.fromisoformat(args.at.replace("Z", "+00:00"))
        except ValueError:
            parser.error("--at must be an ISO timestamp with an explicit timezone")
        if now.tzinfo is None:
            parser.error("--at must include an explicit timezone")
        now = now.astimezone(timezone.utc)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    report = run_audit(news.load_config(args.config), now)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
