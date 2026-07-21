#!/usr/bin/env python3
"""Build the daily Frontier Pulse static news dataset.

The collector uses only Python's standard library so GitHub Actions can run it
without a dependency install. DeepSeek or OpenAI editorial translation is
optional. When neither provider is configured or an API is unavailable,
deterministic ranking and evidence-preserving summaries keep the pipeline
operational.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import html
import json
import logging
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

LOGGER = logging.getLogger("frontier-pulse")
USER_AGENT = "FrontierPulseBot/1.6 (+https://github.com/voilalz/frontier-pulse; public-interest news and research index)"
CATEGORIES = ("AI", "航空航天", "军事动态", "局部冲突", "前沿技术", "无人系统")


@dataclass
class Article:
    id: str
    title: str
    description: str
    url: str
    source: str
    domain: str
    country: str
    published_at: datetime
    category: str = "前沿技术"
    image: str = ""
    date_estimated: bool = False
    tags: list[str] = field(default_factory=list)
    raw_score: float = 0.0
    corroboration: int = 1
    evidence_sources: list[dict[str, str]] = field(default_factory=list)
    score_components: dict[str, int] = field(default_factory=dict)
    score_reasons: list[str] = field(default_factory=list)
    is_supplemental: bool = False
    selection_window_hours: int = 24
    selection_note: str = ""
    diversity_relaxed: bool = False


@dataclass
class ResearchPaper:
    id: str
    title: str
    abstract: str
    url: str
    pdf_url: str
    source: str
    published_at: datetime
    updated_at: datetime
    authors: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    primary_category: str = ""
    research_area: str = "前沿研究"
    tags: list[str] = field(default_factory=list)
    collection_keywords: list[str] = field(default_factory=list)
    score: float = 0.0
    date_estimated: bool = False


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def clean_text(value: Any, limit: int = 0) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+The post .+? appeared first on .*$", "", text, flags=re.I)
    if limit and len(text) > limit:
        return text[: limit - 1].rstrip(" ,.;，。；") + "…"
    return text


def parse_datetime_checked(value: Any, fallback: datetime) -> tuple[datetime, bool]:
    """Parse a timestamp and report whether the safe fallback had to be used."""
    raw = clean_text(value)
    if not raw:
        return fallback, True
    candidates = [raw, raw.replace("Z", "+00:00")]
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc), False
        except ValueError:
            pass
    for pattern in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, pattern).replace(tzinfo=timezone.utc), False
        except ValueError:
            pass
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc), False
    except (TypeError, ValueError, OverflowError):
        return fallback, True


def parse_datetime(value: Any, fallback: datetime) -> datetime:
    return parse_datetime_checked(value, fallback)[0]


def canonical_url(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value.strip())
    except ValueError:
        return value.strip()
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(k, v) for k, v in query if not k.lower().startswith("utm_") and k.lower() not in {"ref", "source", "output"}]
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path.rstrip("/") or "/", urllib.parse.urlencode(query), ""))


def article_id(url: str, title: str) -> str:
    material = (canonical_url(url) or clean_text(title).lower()).encode("utf-8")
    return hashlib.sha1(material).hexdigest()[:14]


def http_get(url: str, *, timeout: int = 18, max_bytes: int = 5_000_000, attempts: int = 2) -> bytes:
    error: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/rss+xml, application/atom+xml, text/xml;q=0.9, */*;q=0.5"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read(max_bytes + 1)
                if len(payload) > max_bytes:
                    raise ValueError(f"response exceeded {max_bytes} bytes")
                return payload
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
            error = exc
            if attempt + 1 < attempts:
                retry_after = 0.0
                delay = 1.2 * (attempt + 1)
                if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
                    try:
                        retry_after = float(exc.headers.get("Retry-After", "0"))
                    except (TypeError, ValueError):
                        retry_after = 0.0
                    delay = max(delay, min(10.0, retry_after or 5.0))
                time.sleep(delay)
    raise RuntimeError(f"GET {url} failed: {error}")


def http_post_json(
    url: str,
    body: dict[str, Any],
    api_key: str,
    *,
    timeout: int = 120,
    attempts: int = 2,
) -> dict[str, Any]:
    """POST JSON with one bounded backoff retry for transient API failures."""
    encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
    error: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(
            url,
            data=encoded,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error = exc
            if exc.code not in {408, 409, 425, 429, 500, 502, 503, 504}:
                break
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            error = exc
        if attempt + 1 < attempts:
            time.sleep(1.5 * (2 ** attempt))
    raise RuntimeError(f"POST {url} failed after {attempts} attempts: {error}")


def domain_from_url(url: str) -> str:
    try:
        return urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    missing = [name for name in CATEGORIES if name not in config.get("categories", {})]
    if missing:
        raise ValueError(f"config is missing categories: {', '.join(missing)}")
    return config


def resolve_ai_runtime(config: dict[str, Any]) -> dict[str, str] | None:
    """Resolve one server-side editorial provider without exposing keys to output."""
    requested = clean_text(os.getenv("AI_PROVIDER") or config.get("ai_provider") or "auto").lower()
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if requested in {"", "auto"}:
        requested = "deepseek" if deepseek_key else "openai" if openai_key else "none"
    if requested == "deepseek" and deepseek_key:
        return {
            "provider": "deepseek",
            "api_key": deepseek_key,
            "model": clean_text(os.getenv("DEEPSEEK_MODEL") or config.get("deepseek_model") or "deepseek-v4-flash"),
            "endpoint": "https://api.deepseek.com/chat/completions",
        }
    if requested == "openai" and openai_key:
        return {
            "provider": "openai",
            "api_key": openai_key,
            "model": clean_text(os.getenv("OPENAI_MODEL") or config.get("openai_model") or "gpt-5.6-luna"),
            "endpoint": "https://api.openai.com/v1/responses",
        }
    return None


def collect_gdelt(
    config: dict[str, Any], now: datetime, *, lookback_hours: int | None = None
) -> list[Article]:
    endpoint = config["gdelt_endpoint"]
    lookback = int(lookback_hours or config["lookback_hours"])
    combined_query = "(" + " OR ".join(definition["query"] for definition in config["categories"].values()) + ")"
    params = {
        "query": combined_query,
        "mode": "artlist",
        "maxrecords": "250",
        "format": "json",
        "sort": "datedesc",
        "timespan": f"{lookback}h",
    }
    url = endpoint + "?" + urllib.parse.urlencode(params)
    try:
        payload: dict[str, Any] | None = None
        error: Exception | None = None
        for attempt in range(2):
            try:
                payload = json.loads(http_get(url, attempts=3).decode("utf-8"))
                break
            except json.JSONDecodeError as exc:
                error = exc
                if attempt == 0:
                    time.sleep(5.0)
        if payload is None:
            raise RuntimeError(f"GDELT returned non-JSON data: {error}")
    except Exception as exc:
        LOGGER.warning("GDELT failed: %s", exc)
        return []
    collected: list[Article] = []
    for item in payload.get("articles", []):
        title = clean_text(item.get("title"), 300)
        target = canonical_url(str(item.get("url") or ""))
        if not title or not target:
            continue
        domain = clean_text(item.get("domain")) or domain_from_url(target)
        published_at, date_estimated = parse_datetime_checked(
            item.get("seendate"), now - timedelta(hours=lookback)
        )
        collected.append(
            Article(
                id=article_id(target, title),
                title=title,
                description=clean_text(item.get("description") or item.get("snippet"), 900),
                url=target,
                source=domain or "GDELT",
                domain=domain,
                country=clean_text(item.get("sourcecountry")) or "国际",
                published_at=published_at,
                category="前沿技术",
                image=str(item.get("socialimage") or ""),
                date_estimated=date_estimated,
            )
        )
    LOGGER.info("GDELT produced %d candidates", len(collected))
    return collected


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def child_text(node: ET.Element, names: Iterable[str]) -> str:
    wanted = {name.lower() for name in names}
    for child in list(node):
        if local_name(child.tag) in wanted:
            return "".join(child.itertext()).strip()
    return ""


def entry_link(node: ET.Element) -> str:
    for child in list(node):
        if local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        rel = child.attrib.get("rel", "alternate")
        if href and rel in {"alternate", ""}:
            return href
        if child.text and child.text.strip():
            return child.text.strip()
    return ""


def entry_image(node: ET.Element) -> str:
    for child in node.iter():
        if local_name(child.tag) in {"thumbnail", "content", "enclosure"}:
            url = child.attrib.get("url", "")
            medium = child.attrib.get("medium", "")
            mime = child.attrib.get("type", "")
            if url and (medium == "image" or mime.startswith("image/") or local_name(child.tag) == "thumbnail"):
                return url
    return ""


def collect_rss(config: dict[str, Any], now: datetime) -> list[Article]:
    feeds = list(config.get("rss_feeds", []))
    safe_date_fallback = now - timedelta(hours=int(config.get("lookback_hours", 24)))

    def fetch_feed(feed: dict[str, Any]) -> list[Article]:
        try:
            root = ET.fromstring(http_get(feed["url"]))
        except Exception as exc:
            LOGGER.warning("RSS %s failed: %s", feed["name"], exc)
            return []
        entries = [node for node in root.iter() if local_name(node.tag) in {"item", "entry"}]
        batch: list[Article] = []
        for node in entries[:50]:
            title = clean_text(child_text(node, ("title",)), 300)
            target = canonical_url(entry_link(node) or child_text(node, ("guid", "id")))
            if not title or not target.startswith(("http://", "https://")):
                continue
            description = child_text(node, ("description", "summary", "content", "encoded"))
            published = child_text(node, ("pubdate", "published", "updated", "date"))
            domain = domain_from_url(target)
            published_at, date_estimated = parse_datetime_checked(published, safe_date_fallback)
            batch.append(
                Article(
                    id=article_id(target, title),
                    title=title,
                    description=clean_text(description, 900),
                    url=target,
                    source=feed["name"],
                    domain=domain,
                    country="国际",
                    published_at=published_at,
                    category=feed.get("default_category", "前沿技术"),
                    image=entry_image(node),
                    date_estimated=date_estimated,
                )
            )
        LOGGER.info("RSS %s produced %d candidates", feed["name"], len(batch))
        return batch

    collected: list[Article] = []
    if not feeds:
        return collected
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(feeds))) as pool:
        for batch in pool.map(fetch_feed, feeds):
            collected.extend(batch)
    return collected


def collect_fixture(path: Path, now: datetime) -> list[Article]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    items = payload.get("items", payload) if isinstance(payload, dict) else payload
    articles: list[Article] = []
    for item in items:
        url = canonical_url(str(item.get("url") or ""))
        title = clean_text(item.get("title"), 300)
        if not title or not url:
            continue
        published_at, date_estimated = parse_datetime_checked(
            item.get("publishedAt") or item.get("published_at"), now - timedelta(hours=24)
        )
        articles.append(
            Article(
                id=str(item.get("id") or article_id(url, title)),
                title=title,
                description=clean_text(item.get("description") or item.get("summary"), 900),
                url=url,
                source=clean_text(item.get("source")) or domain_from_url(url),
                domain=clean_text(item.get("domain")) or domain_from_url(url),
                country=clean_text(item.get("country")) or "国际",
                published_at=published_at,
                category=item.get("category", "前沿技术"),
                image=str(item.get("image") or ""),
                date_estimated=date_estimated,
            )
        )
    return articles


def article_from_public_item(item: dict[str, Any], now: datetime) -> Article | None:
    """Rehydrate one previously published item without inventing missing source data."""
    target = canonical_url(str(item.get("url") or ""))
    title = clean_text(item.get("originalTitle") or item.get("title"), 300)
    published_at, date_estimated = parse_datetime_checked(item.get("publishedAt"), now)
    if not title or not target.startswith(("http://", "https://")) or date_estimated:
        return None
    sources: list[dict[str, str]] = []
    for source in item.get("sources", []):
        if not isinstance(source, dict):
            continue
        source_url = canonical_url(str(source.get("url") or ""))
        source_name = clean_text(source.get("name") or source.get("domain"), 120)
        if not source_url.startswith(("http://", "https://")) or not source_name:
            continue
        sources.append({
            "name": source_name,
            "domain": clean_text(source.get("domain")) or domain_from_url(source_url),
            "url": source_url,
            "publishedAt": clean_text(source.get("publishedAt") or item.get("publishedAt")),
            "evidenceGroup": clean_text(source.get("evidenceGroup")),
        })
    if not sources:
        sources = [{
            "name": clean_text(item.get("source")) or domain_from_url(target),
            "domain": domain_from_url(target),
            "url": target,
            "publishedAt": clean_text(item.get("publishedAt")),
            "evidenceGroup": "",
        }]
    independent = {
        clean_text(source.get("evidenceGroup") or source.get("domain") or source.get("name")).lower()
        for source in sources
        if source.get("evidenceGroup") or source.get("domain") or source.get("name")
    }
    category = clean_text(item.get("category"))
    return Article(
        id=clean_text(item.get("id")) or article_id(target, title),
        title=title,
        description=clean_text(item.get("summary"), 900),
        url=target,
        source=clean_text(item.get("source")) or sources[0]["name"],
        domain=domain_from_url(target),
        country=clean_text(item.get("country")) or "国际",
        published_at=published_at,
        category=category if category in CATEGORIES else "前沿技术",
        image=str(item.get("image") or ""),
        corroboration=max(1, len(independent)),
        evidence_sources=sources,
    )


def collect_public_cache(
    path: Path,
    now: datetime,
    *,
    max_item_age_hours: int,
    max_generated_age_hours: int | None = None,
) -> list[Article]:
    """Read a bounded, already-published cache as a resilience input for the daily run."""
    payload = read_json_safe(path, {})
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        return []
    if max_generated_age_hours is not None:
        generated_at, estimated = parse_datetime_checked(
            payload.get("generatedAt"), now - timedelta(days=365)
        )
        age_hours = (now - generated_at).total_seconds() / 3600
        if estimated or age_hours < -2 or age_hours > max_generated_age_hours:
            LOGGER.warning("Ignoring stale cache %s (age %.1f hours)", path, age_hours)
            return []
    threshold = now - timedelta(hours=max_item_age_hours)
    articles: list[Article] = []
    for item in payload["items"]:
        if not isinstance(item, dict):
            continue
        article = article_from_public_item(item, now)
        if article and threshold <= article.published_at <= now + timedelta(hours=2):
            articles.append(article)
    LOGGER.info("Recovered %d bounded candidates from %s", len(articles), path)
    return articles


def research_definitions(config: dict[str, Any]) -> list[dict[str, Any]]:
    definitions = config.get("research", {}).get("arxiv_categories", [])
    return [
        definition for definition in definitions
        if isinstance(definition, dict) and clean_text(definition.get("id"))
    ]


def research_keyword_definitions(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize up to 20 administrator-managed arXiv keyword queries."""
    raw_definitions = config.get("research", {}).get("collection_keywords", [])
    normalized: list[dict[str, Any]] = []
    for raw in raw_definitions if isinstance(raw_definitions, list) else []:
        definition = {"query": raw, "label": raw} if isinstance(raw, str) else raw
        if not isinstance(definition, dict):
            continue
        query = clean_text(definition.get("query") or definition.get("term"), 120)
        label = clean_text(definition.get("label") or query, 40)
        if not query or not label:
            continue
        aliases = [
            clean_text(alias, 120) for alias in definition.get("aliases", [])
            if clean_text(alias)
        ] if isinstance(definition.get("aliases", []), list) else []
        try:
            priority = int(definition.get("priority", 8))
        except (TypeError, ValueError):
            priority = 8
        normalized.append({
            "query": query,
            "label": label,
            "priority": max(1, min(10, priority)),
            "aliases": list(dict.fromkeys([query, *aliases])),
        })
        if len(normalized) >= 20:
            break
    return normalized


def arxiv_keyword_query(term: str) -> str:
    """Build a literal title-or-abstract query instead of accepting raw Lucene syntax."""
    literal = clean_text(term, 120).replace('"', " ")
    literal = re.sub(r"\s+", " ", literal).strip()
    if not literal:
        return ""
    encoded = f'"{literal}"' if " " in literal else literal
    return f"(ti:{encoded} OR abs:{encoded})"


def research_area_for(categories: list[str], config: dict[str, Any]) -> tuple[str, int]:
    category_set = set(categories)
    for definition in research_definitions(config):
        category_id = clean_text(definition.get("id"))
        if category_id in category_set or (
            category_id == "astro-ph" and any(category.startswith("astro-ph.") for category in category_set)
        ):
            return clean_text(definition.get("label")) or "前沿研究", int(definition.get("priority", 8))
    return "前沿研究", 7


def collect_arxiv(config: dict[str, Any], now: datetime) -> list[ResearchPaper]:
    """Collect relevant preprints from arXiv's public Atom API."""
    research = config.get("research", {})
    definitions = research_definitions(config)
    keyword_definitions = research_keyword_definitions(config)
    if not definitions and not keyword_definitions:
        return []
    endpoint = str(research.get("arxiv_endpoint", "https://export.arxiv.org/api/query"))
    fetch_limit = max(1, min(100, int(research.get("per_area_fetch_limit", 24))))
    delay = max(0.0, float(research.get("request_delay_seconds", 3.1)))
    roots: list[ET.Element] = []
    query_groups: dict[str, list[str]] = {}
    for definition in definitions:
        label = clean_text(definition.get("label")) or clean_text(definition["id"])
        query_groups.setdefault(label, []).append(clean_text(definition["id"]))
    query_specs: list[tuple[str, str, int]] = []
    for label, category_ids in query_groups.items():
        category_query = " OR ".join(f"cat:{category_id}" for category_id in category_ids)
        query_specs.append((label, f"({category_query})" if len(category_ids) > 1 else category_query, fetch_limit))
    keyword_fetch_limit = max(1, min(100, int(research.get("per_keyword_fetch_limit", 20))))
    for definition in keyword_definitions:
        alias_queries: list[str] = []
        for alias in definition["aliases"][:6]:
            query = arxiv_keyword_query(str(alias))
            if query and query not in alias_queries:
                alias_queries.append(query)
        if alias_queries:
            query = f"({' OR '.join(alias_queries)})" if len(alias_queries) > 1 else alias_queries[0]
            query_specs.append((f"关键词：{definition['label']}", query, keyword_fetch_limit))
    for index, (label, search_query, result_limit) in enumerate(query_specs):
        params = {
            "search_query": search_query,
            "start": "0",
            "max_results": str(result_limit),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        if index and delay:
            time.sleep(delay)
        url = endpoint + "?" + urllib.parse.urlencode(params)
        try:
            root = ET.fromstring(http_get(url, timeout=30, max_bytes=8_000_000, attempts=1))
            roots.append(root)
            count = sum(1 for node in root.iter() if local_name(node.tag) == "entry")
            LOGGER.info("arXiv query %s produced %d entries", label, count)
        except Exception as exc:
            LOGGER.warning("arXiv area %s failed: %s", label, exc)
    if not roots:
        return []

    fallback = now - timedelta(days=int(research.get("lookback_days", 7)))
    threshold = fallback
    papers: list[ResearchPaper] = []
    known_ids: set[str] = set()
    entries = [node for root in roots for node in root.iter() if local_name(node.tag) == "entry"]
    for node in entries:
        title = clean_text(child_text(node, ("title",)), 400)
        abstract = clean_text(child_text(node, ("summary",)), 4000)
        raw_id = clean_text(child_text(node, ("id",)))
        arxiv_id = re.sub(r"v\d+$", "", raw_id.rstrip("/").rsplit("/", 1)[-1])
        if not title or not arxiv_id or arxiv_id in known_ids:
            continue
        published_at, date_estimated = parse_datetime_checked(child_text(node, ("published",)), fallback)
        updated_at = parse_datetime(child_text(node, ("updated",)), published_at)
        if max(published_at, updated_at) < threshold or published_at > now + timedelta(hours=2):
            continue
        authors = [
            clean_text(child_text(child, ("name",)), 120)
            for child in list(node)
            if local_name(child.tag) == "author"
        ]
        authors = [author for author in authors if author][:20]
        categories = [
            clean_text(child.attrib.get("term"))
            for child in node.iter()
            if local_name(child.tag) == "category" and child.attrib.get("term")
        ]
        categories = list(dict.fromkeys(category for category in categories if category))
        primary = next((
            clean_text(child.attrib.get("term"))
            for child in node.iter()
            if local_name(child.tag) == "primary_category" and child.attrib.get("term")
        ), categories[0] if categories else "")
        area, _priority = research_area_for(categories or [primary], config)
        source_text = f"{title} {abstract}".lower()
        keyword_labels = [
            str(definition["label"])
            for definition in keyword_definitions
            if any(keyword_matches(source_text, alias) for alias in definition["aliases"])
        ]
        if area == "前沿研究" and keyword_labels:
            area = keyword_labels[0]
        alternate = ""
        pdf_url = ""
        for child in node.iter():
            if local_name(child.tag) != "link":
                continue
            href = clean_text(child.attrib.get("href"))
            if not href:
                continue
            if child.attrib.get("title") == "pdf" or child.attrib.get("type") == "application/pdf":
                pdf_url = href
            elif child.attrib.get("rel", "alternate") == "alternate":
                alternate = href
        canonical = f"https://arxiv.org/abs/{arxiv_id}"
        papers.append(ResearchPaper(
            id=f"arxiv:{arxiv_id}",
            title=title,
            abstract=abstract,
            url=canonical_url(alternate) or canonical,
            pdf_url=canonical_url(pdf_url) or f"https://arxiv.org/pdf/{arxiv_id}",
            source="arXiv",
            published_at=published_at,
            updated_at=updated_at,
            authors=authors,
            categories=categories,
            primary_category=primary,
            research_area=area,
            collection_keywords=keyword_labels,
            date_estimated=date_estimated,
        ))
        known_ids.add(arxiv_id)
    LOGGER.info("arXiv produced %d relevant papers", len(papers))
    return papers


def collect_research_fixture(path: Path, now: datetime, config: dict[str, Any]) -> list[ResearchPaper]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    items = payload.get("items", payload) if isinstance(payload, dict) else payload
    papers: list[ResearchPaper] = []
    fallback = now - timedelta(days=int(config.get("research", {}).get("lookback_days", 7)))
    for index, item in enumerate(items):
        title = clean_text(item.get("title"), 400)
        target = canonical_url(str(item.get("url") or ""))
        if not title or not target:
            continue
        published_at, date_estimated = parse_datetime_checked(item.get("publishedAt"), fallback)
        updated_at = parse_datetime(item.get("updatedAt"), published_at)
        categories = [clean_text(category) for category in item.get("categories", []) if clean_text(category)]
        primary = clean_text(item.get("primaryCategory")) or (categories[0] if categories else "")
        area, _priority = research_area_for(categories or [primary], config)
        papers.append(ResearchPaper(
            id=clean_text(item.get("id")) or f"paper-{index}",
            title=title,
            abstract=clean_text(item.get("abstract") or item.get("summary"), 4000),
            url=target,
            pdf_url=canonical_url(str(item.get("pdfUrl") or "")),
            source=clean_text(item.get("source")) or "arXiv",
            published_at=published_at,
            updated_at=updated_at,
            authors=[clean_text(author, 120) for author in item.get("authors", []) if clean_text(author)][:20],
            categories=categories,
            primary_category=primary,
            research_area=clean_text(item.get("researchArea")) or area,
            collection_keywords=[
                clean_text(keyword, 40) for keyword in item.get("collectionKeywords", [])
                if clean_text(keyword)
            ][:20],
            date_estimated=date_estimated,
        ))
    return papers


def score_research_papers(
    papers: list[ResearchPaper], config: dict[str, Any], now: datetime
) -> list[ResearchPaper]:
    """Rank research by topical relevance and freshness, separately from news importance."""
    research = config.get("research", {})
    threshold = now - timedelta(days=int(research.get("lookback_days", 7)))
    scored: list[ResearchPaper] = []
    signal_keywords = {
        keyword.lower()
        for definition in config.get("categories", {}).values()
        for keyword in definition.get("keywords", [])
    }
    collection_definitions = research_keyword_definitions(config)
    for paper in papers:
        if max(paper.published_at, paper.updated_at) < threshold or paper.published_at > now + timedelta(hours=2):
            continue
        area, priority = research_area_for(paper.categories or [paper.primary_category], config)
        paper.research_area = paper.research_area or area
        text = f"{paper.title} {paper.abstract}".lower()
        matched = [keyword for keyword in signal_keywords if keyword_matches(text, keyword)]
        collection_matches = [
            definition for definition in collection_definitions
            if any(keyword_matches(text, alias) for alias in definition["aliases"])
        ]
        paper.collection_keywords = list(dict.fromkeys([
            *paper.collection_keywords,
            *(str(definition["label"]) for definition in collection_matches),
        ]))[:20]
        if paper.research_area == "前沿研究" and paper.collection_keywords:
            paper.research_area = paper.collection_keywords[0]
        age_days = max(0.0, (now - max(paper.published_at, paper.updated_at)).total_seconds() / 86_400)
        freshness = max(0.0, 28.0 - age_days * 4)
        evidence = 8 if len(paper.abstract) >= 500 else 5 if len(paper.abstract) >= 180 else 2
        collection_boost = min(18, sum(max(2, int(definition["priority"]) - 5) for definition in collection_matches))
        paper.score = min(100.0, 35 + priority * 2 + freshness + min(14, len(matched) * 2) + collection_boost + evidence)
        human_tags = [
            paper.research_area, *paper.collection_keywords, paper.primary_category,
            *sorted(matched, key=len, reverse=True),
        ]
        paper.tags = list(dict.fromkeys(clean_text(tag, 28) for tag in human_tags if clean_text(tag)))[:5]
        scored.append(paper)
    return sorted(scored, key=lambda paper: (paper.score, paper.updated_at), reverse=True)


def choose_research_diverse(
    papers: list[ResearchPaper], config: dict[str, Any]
) -> list[ResearchPaper]:
    """Prevent high-volume arXiv categories from crowding every other research area out."""
    research = config.get("research", {})
    limit = max(1, int(research.get("limit", 60)))
    per_area_limit = max(1, int(research.get("per_area_limit", 12)))
    selected: list[ResearchPaper] = []
    deferred: list[ResearchPaper] = []
    area_counts: dict[str, int] = {}
    for paper in papers:
        area = paper.research_area or "前沿研究"
        if area_counts.get(area, 0) < per_area_limit:
            selected.append(paper)
            area_counts[area] = area_counts.get(area, 0) + 1
        else:
            deferred.append(paper)
        if len(selected) >= limit:
            return selected
    for paper in deferred:
        if len(selected) >= limit:
            break
        selected.append(paper)
    return sorted(selected, key=lambda paper: (paper.score, paper.updated_at), reverse=True)


def normalized_title(title: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", title.lower())


def keyword_matches(text: str, keyword: str) -> bool:
    """Match Latin keywords on token boundaries and CJK keywords by substring."""
    needle = keyword.lower().strip()
    if not needle:
        return False
    if re.search(r"[\u3400-\u9fff]", needle):
        return needle in text
    return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", text) is not None


TITLE_STOPWORDS = {
    "a", "an", "and", "after", "as", "at", "by", "for", "from", "in", "into", "its", "new", "of", "on", "out", "over",
    "the", "to", "us", "with", "says", "said",
}
TITLE_ALIASES = {
    "sue": "lawsuit", "sued": "lawsuit", "sues": "lawsuit", "suing": "lawsuit", "lawsuits": "lawsuit",
}


def title_tokens(title: str) -> tuple[set[str], set[str]]:
    raw_tokens = re.findall(r"[A-Za-z][A-Za-z0-9-]*|[\u3400-\u9fff]{2,}", title)
    acronyms = {token.lower() for token in raw_tokens if re.fullmatch(r"[A-Z][A-Z0-9-]{2,}", token)}
    tokens = {
        TITLE_ALIASES.get(token.lower(), token.lower())
        for token in raw_tokens
        if token.lower() not in TITLE_STOPWORDS
    }
    return tokens, acronyms


def same_event_title(first: str, second: str) -> bool:
    normalized_first = normalized_title(first)
    normalized_second = normalized_title(second)
    if normalized_first == normalized_second:
        return True
    if min(len(normalized_first), len(normalized_second)) > 24 and SequenceMatcher(None, normalized_first, normalized_second).ratio() >= 0.9:
        return True
    first_tokens, first_acronyms = title_tokens(first)
    second_tokens, second_acronyms = title_tokens(second)
    if not first_tokens or not second_tokens:
        return False
    shared = first_tokens.intersection(second_tokens)
    overlap = len(shared) / min(len(first_tokens), len(second_tokens))
    if len(shared) >= 4 and overlap >= 0.5:
        return True
    return len(shared) >= 3 and overlap >= 0.35 and bool(shared.intersection(first_acronyms, second_acronyms))


def wire_family(article: Article) -> str:
    """Identify explicit wire-service provenance without treating republishers as independent."""
    domain = article.domain.lower()
    source = clean_text(article.source).lower()
    description = clean_text(article.description)[:500]
    if domain == "reuters.com" or domain.endswith(".reuters.com") or source == "reuters":
        return "wire:reuters"
    if domain == "apnews.com" or domain.endswith(".apnews.com") or source in {"ap", "associated press"}:
        return "wire:ap"
    if re.search(r"(?:^|[\s(—-])reuters(?:[\s),.:;—-]|$)", description, flags=re.I):
        return "wire:reuters"
    if re.search(r"\bassociated press\b", description, flags=re.I) or re.search(
        r"(?:^|[\s(—-])AP(?:[\s),.:;—-]|$)", description
    ):
        return "wire:ap"
    return ""


def source_group(article: Article) -> str:
    family = wire_family(article)
    if family:
        return family
    identity = (article.domain or article.source or canonical_url(article.url)).strip().lower()
    return "outlet:" + identity


def descriptions_look_syndicated(first: Article, second: Article) -> bool:
    first_text = clean_text(first.description).lower()
    second_text = clean_text(second.description).lower()
    if len(first_text) >= 80 and len(second_text) >= 80:
        if SequenceMatcher(None, first_text[:700], second_text[:700]).ratio() >= 0.88:
            return True
    if wire_family(first) or wire_family(second):
        first_title = normalized_title(first.title)
        second_title = normalized_title(second.title)
        return min(len(first_title), len(second_title)) >= 24 and SequenceMatcher(
            None, first_title, second_title
        ).ratio() >= 0.94
    return False


def source_evidence(article: Article) -> dict[str, str]:
    """Return the public metadata needed to inspect one supporting source."""
    return {
        "name": article.source,
        "domain": article.domain,
        "url": article.url,
        "publishedAt": article.published_at.isoformat().replace("+00:00", "Z"),
        "evidenceGroup": source_group(article),
    }


def ensure_evidence_sources(article: Article) -> None:
    if not article.evidence_sources:
        article.evidence_sources = [source_evidence(article)]


def merge_evidence_sources(target: Article, incoming: Article) -> None:
    ensure_evidence_sources(target)
    ensure_evidence_sources(incoming)
    if descriptions_look_syndicated(target, incoming):
        wire_group = wire_family(target) or wire_family(incoming)
        group = wire_group or target.evidence_sources[0].get("evidenceGroup")
        if not group or group.startswith("outlet:"):
            digest = hashlib.sha1(normalized_title(target.title).encode("utf-8")).hexdigest()[:12]
            group = f"syndication:{digest}"
        target.evidence_sources[0]["evidenceGroup"] = group
        for evidence in incoming.evidence_sources:
            evidence["evidenceGroup"] = group
    known_urls = {canonical_url(item.get("url", "")) for item in target.evidence_sources}
    for evidence in incoming.evidence_sources:
        url = canonical_url(evidence.get("url", ""))
        if url and url not in known_urls:
            target.evidence_sources.append(evidence)
            known_urls.add(url)
    independent_sources = {
        (item.get("evidenceGroup") or item.get("domain") or item.get("name") or "").strip().lower()
        for item in target.evidence_sources
        if item.get("evidenceGroup") or item.get("domain") or item.get("name")
    }
    target.corroboration = max(1, len(independent_sources))


def deduplicate(articles: Iterable[Article]) -> list[Article]:
    unique: list[Article] = []
    urls: dict[str, Article] = {}
    for article in sorted(articles, key=lambda item: item.published_at, reverse=True):
        ensure_evidence_sources(article)
        key = canonical_url(article.url)
        if key in urls:
            merge_evidence_sources(urls[key], article)
            if not urls[key].description and article.description:
                urls[key].description = article.description
            continue
        duplicate = False
        for existing in unique:
            close_in_time = abs((existing.published_at - article.published_at).total_seconds()) <= 24 * 3600
            if close_in_time and same_event_title(article.title, existing.title):
                merge_evidence_sources(existing, article)
                if not existing.description and article.description:
                    existing.description = article.description
                duplicate = True
                break
        if duplicate:
            continue
        urls[key] = article
        unique.append(article)
    return unique


def classify(article: Article, config: dict[str, Any]) -> tuple[str, list[str]]:
    text = f"{article.title} {article.description}".lower()
    scores: dict[str, int] = {}
    matched: dict[str, list[str]] = {}
    for category, definition in config["categories"].items():
        hits = [keyword for keyword in definition["keywords"] if keyword_matches(text, keyword)]
        scores[category] = len(hits) * 3 + (2 if article.category == category else 0)
        matched[category] = hits
    winner = max(scores, key=scores.get)
    if scores[winner] == 0 and article.category in CATEGORIES:
        winner = article.category
    tags = sorted(matched[winner], key=len, reverse=True)[:3]
    return winner, tags


def outlet_weight(article_domain: str, name: str, config: dict[str, Any]) -> int:
    for weighted_domain, weight in config.get("source_weights", {}).items():
        if article_domain == weighted_domain or article_domain.endswith("." + weighted_domain):
            return int(weight)
    for feed in config.get("rss_feeds", []):
        if name == feed["name"]:
            return int(feed.get("weight", 12))
    if article_domain.endswith((".gov", ".mil")):
        return 18
    return 10


def source_weight(article: Article, config: dict[str, Any]) -> int:
    ensure_evidence_sources(article)
    return max(
        outlet_weight(evidence.get("domain", ""), evidence.get("name", ""), config)
        for evidence in article.evidence_sources
    )


def score_articles(
    articles: list[Article],
    config: dict[str, Any],
    now: datetime,
    *,
    lookback_hours: int | None = None,
) -> list[Article]:
    primary_window = int(config["lookback_hours"])
    active_window = int(lookback_hours or primary_window)
    threshold = now - timedelta(hours=active_window)
    scored: list[Article] = []
    for article in articles:
        if article.published_at < threshold or article.published_at > now + timedelta(hours=2):
            continue
        article.category, article.tags = classify(article, config)
        text = f"{article.title} {article.description}".lower()
        if any(keyword_matches(text, keyword) for keyword in config.get("editorial_exclude_keywords", [])):
            continue
        relevance_hits = {
            keyword.lower()
            for definition in config["categories"].values()
            for keyword in definition["keywords"]
            if keyword_matches(text, keyword)
        }
        if not relevance_hits:
            continue
        impact_hits = [
            keyword
            for keyword in config.get("impact_keywords", {})
            if keyword_matches(text, keyword)
        ]
        keyword_score = sum(int(config["impact_keywords"][keyword]) for keyword in impact_hits)
        age_hours = max(0.0, (now - article.published_at).total_seconds() / 3600)
        article.diversity_relaxed = False
        article.is_supplemental = age_hours > primary_window
        article.selection_window_hours = active_window if article.is_supplemental else primary_window
        article.selection_note = (
            f"24 小时候选不足，作为 {active_window} 小时窗口补充观察"
            if article.is_supplemental else ""
        )
        supplemental_penalty = (
            min(18, 4 + int(max(0.0, age_hours - primary_window) // 12) * 3)
            if article.is_supplemental else 0
        )
        recency = max(0.0, 20.0 - age_hours * 0.5)
        priority = int(config["categories"][article.category].get("priority", 8))
        # GDELT and some high-quality feeds expose title/link metadata but no description.
        # Give complete title/link metadata a small baseline instead of systematically
        # treating those collectors as evidence-free.
        evidence = 3 if len(article.description) >= 80 else 2
        corroboration = min(12, max(0, article.corroboration - 1) * 4)
        relevance = min(12, len(relevance_hits) * 2)
        penalty = min(24, sum(12 for keyword in config.get("editorial_penalty_keywords", []) if keyword_matches(text, keyword)))
        date_penalty = 7 if article.date_estimated else 0
        source = source_weight(article, config)
        article.score_components = {
            "基础分": 15,
            "来源": source,
            "主题优先级": priority,
            "时效": round(recency),
            "影响信号": min(22, keyword_score),
            "主题相关性": relevance,
            "证据完整度": evidence,
            "多源印证": corroboration,
            "编辑降权": penalty,
            "日期异常降权": date_penalty,
            "补充窗口降权": supplemental_penalty,
        }
        positive = sum(
            value for key, value in article.score_components.items() if not key.endswith("降权")
        )
        negative = sum(
            value for key, value in article.score_components.items() if key.endswith("降权")
        )
        total = positive - negative
        article.raw_score = min(100.0, max(0.0, total))
        reasons = [
            f"来源权重 {source}/20",
            f"发布约 {age_hours:.1f} 小时",
            f"命中 {len(relevance_hits)} 个主题信号",
        ]
        if impact_hits:
            reasons.append("影响信号：" + "、".join(impact_hits[:3]))
        if article.corroboration > 1:
            reasons.append(f"{article.corroboration} 个独立来源相互印证")
        if penalty:
            reasons.append(f"编辑质量降权 -{penalty}")
        if article.date_estimated:
            reasons.append(f"发布时间无法解析，按 {active_window} 小时窗口边缘处理并降权")
        if article.is_supplemental:
            reasons.append(f"超过 24 小时，作为补充观察并降权 -{supplemental_penalty}")
        article.score_reasons = reasons
        scored.append(article)
    return sorted(scored, key=lambda item: (item.raw_score, item.published_at), reverse=True)


def choose_diverse(candidates: list[Article], config: dict[str, Any], count: int) -> list[Article]:
    category_limit = int(config["per_category_limit"])
    domain_limit = int(config["per_domain_limit"])
    selected: list[Article] = []
    selected_ids: set[str] = set()
    category_counts: dict[str, int] = {}
    domain_counts: dict[str, int] = {}

    def add(article: Article, *, relaxed: bool = False, note: str = "") -> None:
        selected.append(article)
        selected_ids.add(article.id)
        category_counts[article.category] = category_counts.get(article.category, 0) + 1
        domain_key = article.domain or article.source
        domain_counts[domain_key] = domain_counts.get(domain_key, 0) + 1
        if relaxed:
            article.diversity_relaxed = True
            article.selection_note = "；".join(part for part in (article.selection_note, note) if part)

    # Pass 1: preserve the configured editorial mix.
    for article in candidates:
        if category_counts.get(article.category, 0) >= category_limit:
            continue
        domain_key = article.domain or article.source
        if domain_counts.get(domain_key, 0) >= domain_limit:
            continue
        add(article)
        if len(selected) == count:
            return selected

    # Pass 2: low-volume days may be concentrated in one topic. Keep the source
    # cap, but allow the strongest remaining topics to fill the edition.
    for article in candidates:
        if article.id in selected_ids:
            continue
        domain_key = article.domain or article.source
        if domain_counts.get(domain_key, 0) >= domain_limit:
            continue
        add(article, relaxed=True, note="为补足 Top 10 放宽主题配额")
        if len(selected) == count:
            return selected

    # Pass 3: only after topic relaxation, allow another story from a source.
    # This is preferable to dropping the whole daily edition while remaining
    # transparent in the item metadata and public pipeline warning.
    for article in candidates:
        if article.id in selected_ids:
            continue
        add(article, relaxed=True, note="为补足 Top 10 放宽来源配额")
        if len(selected) == count:
            return selected
    raise ValueError(
        f"去重后仅有 {len(selected)} 条可发布候选；需要 {count} 条"
    )


def validate_ai_diversity(
    selected: list[Article],
    editorial_by_id: dict[str, dict[str, Any]],
    config: dict[str, Any],
) -> None:
    """Apply the same hard diversity limits after the AI editorial pass."""
    category_limit = int(config["per_category_limit"])
    domain_limit = int(config["per_domain_limit"])
    categories: dict[str, int] = {}
    domains: dict[str, int] = {}
    for article in selected:
        editorial = editorial_by_id.get(article.id, {})
        category = editorial.get("category") if editorial.get("category") in CATEGORIES else article.category
        domain = article.domain or article.source
        categories[category] = categories.get(category, 0) + 1
        domains[domain] = domains.get(domain, 0) + 1
    crowded_categories = {name: count for name, count in categories.items() if count > category_limit}
    crowded_domains = {name: count for name, count in domains.items() if count > domain_limit}
    if crowded_categories or crowded_domains:
        raise ValueError(
            "OpenAI 选稿未通过多样性校验："
            f"类别超限={crowded_categories or '无'}，域名超限={crowded_domains or '无'}"
        )


WHY_TEMPLATES = {
    "AI": "该进展可能影响模型能力、安全治理、算力需求或产业竞争格局。",
    "航空航天": "该进展可能改变发射、轨道基础设施、航空平台或深空任务的能力边界。",
    "军事动态": "该动态可能影响装备采购、战备部署、工业产能或跨域作战体系。",
    "局部冲突": "该事件可能影响冲突强度、地区安全、武器运用方式或外交空间。",
    "前沿技术": "该进展可能缩短技术工程化周期，并改变关键产业与供应链竞争。",
    "无人系统": "该进展可能推动无人平台从单机应用转向协同、规模化与体系化运用。",
}


def fallback_summary(article: Article) -> str:
    if article.description:
        return clean_text(article.description, 180)
    return f"据{article.source}公开信息，{article.title}。现有元数据有限，详情应以原始报道为准。"


def confidence_assessment(article: Article, config: dict[str, Any]) -> tuple[str, str]:
    """Explain source confidence without pretending to verify the underlying claim."""
    weight = source_weight(article, config)
    count = max(1, article.corroboration)
    if count >= 3 or (count >= 2 and weight >= 17):
        return "高", f"主来源权重 {weight}/20，且有 {count} 个独立来源报道；仍应以原文和一手材料为准。"
    if count >= 2 or weight >= 16:
        return "中", f"来源权重 {weight}/20，共 {count} 个独立来源；关键事实建议继续交叉核验。"
    return "待核验", f"当前仅收录 1 个来源（权重 {weight}/20），不代表事实已经独立证实。"


def extract_response_text(payload: dict[str, Any]) -> str:
    for output in payload.get("output", []):
        if output.get("type") != "message":
            continue
        for content in output.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                return str(content["text"])
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    raise ValueError("OpenAI response did not contain output_text")


def extract_chat_completion_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices", [])
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str) and content.strip():
            return content
    raise ValueError("DeepSeek response did not contain message content")


def parse_json_object(value: str) -> dict[str, Any]:
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("AI response must be one JSON object")
    return parsed


def request_structured_json(
    runtime: dict[str, str],
    *,
    instructions: str,
    input_text: str,
    schema_name: str,
    schema: dict[str, Any],
    example: dict[str, Any],
    max_tokens: int,
) -> dict[str, Any]:
    """Call OpenAI Responses or DeepSeek ChatCompletions with local validation."""
    if runtime["provider"] == "deepseek":
        system_prompt = (
            instructions
            + " 只输出一个合法 JSON 对象，不要输出 Markdown、解释或思考过程。"
            + " JSON 输出示例："
            + json.dumps(example, ensure_ascii=False)
            + " 字段约束："
            + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
        )
        body = {
            "model": runtime["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": input_text},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "max_tokens": max_tokens,
            "stream": False,
        }
        payload = http_post_json(runtime["endpoint"], body, runtime["api_key"])
        return parse_json_object(extract_chat_completion_text(payload))
    body = {
        "model": runtime["model"],
        "store": False,
        "instructions": instructions,
        "input": input_text,
        "text": {"format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": schema}},
        "max_output_tokens": max_tokens,
    }
    payload = http_post_json(runtime["endpoint"], body, runtime["api_key"])
    return parse_json_object(extract_response_text(payload))


def ai_select(candidates: list[Article], config: dict[str, Any], runtime: dict[str, str]) -> dict[str, Any]:
    category_enum = list(CATEGORIES)
    item_schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "titleZh": {"type": "string"},
            "category": {"type": "string", "enum": category_enum},
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "summary": {"type": "string"},
            "keyFacts": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 3},
            "why": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        },
        "required": ["id", "titleZh", "category", "score", "summary", "keyFacts", "why", "tags"],
        "additionalProperties": False,
    }
    schema = {
        "type": "object",
        "properties": {
            "brief": {
                "type": "object",
                "properties": {
                    "headline": {"type": "string"},
                    "summary": {"type": "string"},
                    "signals": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
                },
                "required": ["headline", "summary", "signals"],
                "additionalProperties": False,
            },
            "items": {"type": "array", "items": item_schema, "minItems": 10, "maxItems": 10},
        },
        "required": ["brief", "items"],
        "additionalProperties": False,
    }
    evidence = [
        {
            "id": article.id,
            "title": article.title,
            "description": clean_text(article.description, 650),
            "source": article.source,
            "country": article.country,
            "publishedAt": article.published_at.isoformat().replace("+00:00", "Z"),
            "ruleCategory": article.category,
            "ruleScore": round(article.raw_score),
            "corroboration": article.corroboration,
            "sources": article.evidence_sources,
        }
        for article in candidates
    ]
    instructions = (
        "你是国际科技与安全新闻编辑。只能依据提供的标题、描述、来源和时间工作，不得补写候选材料中没有的事实。"
        "从候选中选择恰好10条最重要且类别尽量多样的新闻，优先考虑全球影响、技术/政策拐点、可信来源、时效与多源印证。"
        "为每条生成忠实、自然的中文标题（保留机构、型号和专有名词），并输出不超过90字的中文摘要、2至3条可由候选材料直接支持的关键事实、"
        "不超过70字的为什么重要、0-100重要度和最多3个短标签。关键事实不得把推断写成事实。"
        "军事与冲突新闻保持中性、事实与判断分离；信息不足时明确使用‘据公开信息’等保守表达。"
    )
    example_item = {
        "id": candidates[0].id,
        "titleZh": "忠实的中文标题",
        "category": candidates[0].category,
        "score": 80,
        "summary": "不超过90字的中文摘要",
        "keyFacts": ["可核验事实一", "可核验事实二"],
        "why": "为什么重要",
        "tags": ["标签"],
    }
    example = {
        "brief": {"headline": "今日态势标题", "summary": "总体摘要", "signals": ["信号一", "信号二", "信号三"]},
        "items": [example_item],
    }
    error: Exception | None = None
    for attempt in range(2):
        try:
            result = request_structured_json(
                runtime,
                instructions=instructions,
                input_text="候选新闻证据：\n" + json.dumps(evidence, ensure_ascii=False),
                schema_name="frontier_daily",
                schema=schema,
                example=example,
                max_tokens=int(config.get("ai_max_output_tokens", config.get("openai_max_output_tokens", 8000))),
            )
            items = result.get("items", [])
            if not isinstance(items, list) or len(items) != 10:
                raise ValueError("structured response did not contain exactly 10 items")
            allowed_ids = {article.id for article in candidates}
            seen_ids: set[str] = set()
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError("daily editorial item must be an object")
                item_id = clean_text(item.get("id"))
                if item_id not in allowed_ids or item_id in seen_ids:
                    raise ValueError(f"daily editorial response contained invalid or duplicate id: {item_id}")
                seen_ids.add(item_id)
                if item.get("category") not in CATEGORIES:
                    raise ValueError(f"daily editorial response contained invalid category: {item.get('category')}")
                try:
                    score = int(item.get("score"))
                except (TypeError, ValueError):
                    raise ValueError("daily editorial score must be an integer") from None
                if not 0 <= score <= 100:
                    raise ValueError("daily editorial score must be between 0 and 100")
                if not all(clean_text(item.get(field_name)) for field_name in ("titleZh", "summary", "why")):
                    raise ValueError("daily editorial item is missing title, summary or importance")
                facts = item.get("keyFacts")
                tags = item.get("tags")
                if not isinstance(facts, list) or not 2 <= len([fact for fact in facts if clean_text(fact)]) <= 3:
                    raise ValueError("daily editorial item must contain 2-3 key facts")
                if not isinstance(tags, list):
                    raise ValueError("daily editorial tags must be an array")
                item["score"] = score
            return result
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            error = exc
            if attempt == 0:
                time.sleep(1.5)
    raise RuntimeError(f"{runtime['provider']} structured output could not be parsed after one retry: {error}")


def item_from_article(article: Article, config: dict[str, Any], editorial: dict[str, Any] | None = None) -> dict[str, Any]:
    editorial = editorial or {}
    translation_only = bool(editorial.get("_translationOnly"))
    score = int(editorial.get("score", round(article.raw_score)))
    category = editorial.get("category") if editorial.get("category") in CATEGORIES else article.category
    tags = [clean_text(tag, 24) for tag in editorial.get("tags", article.tags) if clean_text(tag)][:3]
    summary = clean_text(editorial.get("summary") or fallback_summary(article), 220)
    key_facts = [clean_text(fact, 140) for fact in editorial.get("keyFacts", []) if clean_text(fact)][:3]
    if not key_facts:
        key_facts = [summary]
    ensure_evidence_sources(article)
    confidence, confidence_reason = confidence_assessment(article, config)
    score_reasons = list(article.score_reasons)
    score_basis = "AI翻译 · 规则评分" if translation_only else "AI编辑评分" if editorial else "规则评分"
    if editorial and not translation_only:
        score_reasons = [f"AI 编辑重要度 {score}/100", f"规则参考分 {round(article.raw_score)}/100", *score_reasons]
    return {
        "id": article.id,
        "contentType": "news",
        "title": clean_text(editorial.get("titleZh") or article.title, 180),
        "originalTitle": article.title,
        "summary": summary,
        "keyFacts": key_facts,
        "why": clean_text(editorial.get("why") or WHY_TEMPLATES[category], 180),
        "category": category,
        "source": article.source,
        "country": article.country,
        "publishedAt": article.published_at.isoformat().replace("+00:00", "Z"),
        "url": article.url,
        "score": max(0, min(100, score)),
        "scoreBasis": score_basis,
        "scoreComponents": article.score_components,
        "scoreReasons": score_reasons,
        "confidence": confidence,
        "confidenceReason": confidence_reason,
        "tags": tags,
        "image": article.image,
        "corroboration": article.corroboration,
        "sources": article.evidence_sources,
        "translationProvider": clean_text(editorial.get("_provider")),
        "isSupplemental": article.is_supplemental,
        "selectionWindowHours": article.selection_window_hours,
        "selectionNote": article.selection_note,
        "diversityRelaxed": article.diversity_relaxed,
    }


def ai_translate_articles(
    articles: list[Article], config: dict[str, Any], runtime: dict[str, str]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Translate full-stream metadata in bounded batches without changing ranking."""
    translations: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    batch_size = max(1, min(20, int(config.get("stream_translation_batch_size", 12))))
    consecutive_failures = 0
    for start in range(0, len(articles), batch_size):
        batch = articles[start:start + batch_size]
        allowed_ids = [article.id for article in batch]
        item_schema = {
            "type": "object",
            "properties": {
                "id": {"type": "string", "enum": allowed_ids},
                "titleZh": {"type": "string"},
                "summary": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
            },
            "required": ["id", "titleZh", "summary", "tags"],
            "additionalProperties": False,
        }
        schema = {
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": item_schema, "minItems": len(batch), "maxItems": len(batch)},
            },
            "required": ["items"],
            "additionalProperties": False,
        }
        evidence = [{
            "id": article.id,
            "title": article.title,
            "description": clean_text(article.description, 900),
            "source": article.source,
            "publishedAt": article.published_at.isoformat().replace("+00:00", "Z"),
        } for article in batch]
        example = {"items": [{
            "id": allowed_ids[0], "titleZh": "忠实的中文标题",
            "summary": "不超过120字的中文摘要", "tags": ["标签"],
        }]}
        try:
            result = request_structured_json(
                runtime,
                instructions=(
                    "你是科技新闻翻译编辑。逐条把标题和已有描述忠实翻译、压缩为自然中文，保留机构、型号、数值和不确定性。"
                    "不得补充输入中不存在的事实，不得改变立场；描述为空时明确写‘现有元数据未提供摘要’。"
                    "每条输出中文标题、不超过120字的中文摘要和最多3个短标签。"
                ),
                input_text="待翻译新闻元数据：\n" + json.dumps(evidence, ensure_ascii=False),
                schema_name="frontier_stream_translation",
                schema=schema,
                example=example,
                max_tokens=int(config.get("stream_translation_max_tokens", 10000)),
            )
            batch_items: dict[str, dict[str, Any]] = {}
            for item in result.get("items", []):
                item_id = clean_text(item.get("id")) if isinstance(item, dict) else ""
                if (
                    item_id in allowed_ids
                    and item_id not in batch_items
                    and clean_text(item.get("titleZh"))
                    and clean_text(item.get("summary"))
                ):
                    batch_items[item_id] = {
                        **item,
                        "tags": item.get("tags", []) if isinstance(item.get("tags", []), list) else [],
                        "_translationOnly": True,
                        "_provider": runtime["provider"],
                    }
            translations.update(batch_items)
            consecutive_failures = 0
            if len(batch_items) != len(batch):
                warnings.append(f"新闻中文翻译批次不完整：{len(batch_items)}/{len(batch)}")
        except Exception as exc:
            reason = clean_text(str(exc), 160) or exc.__class__.__name__
            warnings.append(f"新闻中文翻译批次失败：{reason}")
            LOGGER.warning("Stream translation batch failed: %s", reason)
            consecutive_failures += 1
            if consecutive_failures >= 2 and start + batch_size < len(articles):
                warnings.append("新闻中文翻译连续失败 2 个批次，已停止后续调用并保留原始元数据")
                break
    return translations, warnings


def build_stream_report(
    candidates: list[Article],
    config: dict[str, Any],
    now: datetime,
    top_stories: set[str] | dict[str, dict[str, Any]] | None = None,
    translations: dict[str, dict[str, Any]] | None = None,
    translation_runtime: dict[str, str] | None = None,
    translation_warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Publish the complete qualified 24-hour candidate stream, capped for payload safety."""
    limit = max(1, int(config.get("stream_limit", 300)))
    selected = candidates[:limit]
    featured_items = top_stories if isinstance(top_stories, dict) else {}
    featured = set(featured_items) if featured_items else set(top_stories or set())
    translations = translations or {}
    items: list[dict[str, Any]] = []
    for article in selected:
        item = item_from_article(article, config, translations.get(article.id))
        daily_item = featured_items.get(article.id)
        if isinstance(daily_item, dict):
            for field_name in (
                "title", "originalTitle", "summary", "keyFacts", "why", "category", "score",
                "scoreBasis", "scoreComponents", "scoreReasons", "confidence", "confidenceReason",
                "tags", "sources", "corroboration", "translationProvider",
            ):
                if field_name in daily_item:
                    item[field_name] = daily_item[field_name]
        item["isTopStory"] = article.id in featured
        item["streamRank"] = len(items) + 1
        items.append(item)
    category_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    for item in items:
        category = str(item.get("category", "其他"))
        source = str(item.get("source", "未知来源"))
        category_counts[category] = category_counts.get(category, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1
    return {
        "schemaVersion": 2,
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "timezone": config.get("timezone", "Asia/Tokyo"),
        "rangeHours": int(config.get("lookback_hours", 24)),
        "itemCount": len(items),
        "totalCandidateCount": len(candidates),
        "truncated": len(candidates) > limit,
        "categoryCounts": category_counts,
        "sourceCounts": dict(sorted(source_counts.items(), key=lambda pair: (-pair[1], pair[0]))),
        "translationProvider": translation_runtime.get("provider") if translation_runtime else "",
        "translationModel": translation_runtime.get("model") if translation_runtime else "",
        "translatedItemCount": sum(bool(item.get("translationProvider")) for item in items),
        "translationWarnings": list(translation_warnings or []),
        "items": items,
    }


def ai_edit_research(
    papers: list[ResearchPaper], config: dict[str, Any], runtime: dict[str, str]
) -> dict[str, dict[str, Any]]:
    allowed_ids = [paper.id for paper in papers]
    item_schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "enum": allowed_ids},
            "titleZh": {"type": "string"},
            "summaryZh": {"type": "string"},
            "question": {"type": "string"},
            "method": {"type": "string"},
            "findings": {"type": "string"},
            "limitations": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
        },
        "required": ["id", "titleZh", "summaryZh", "question", "method", "findings", "limitations", "tags"],
        "additionalProperties": False,
    }
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": item_schema,
                "minItems": len(papers),
                "maxItems": len(papers),
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }
    evidence = [{
        "id": paper.id,
        "title": paper.title,
        "abstract": clean_text(paper.abstract, 1800),
        "authors": paper.authors[:8],
        "categories": paper.categories,
        "publishedAt": paper.published_at.isoformat().replace("+00:00", "Z"),
    } for paper in papers]
    example = {"items": [{
        "id": allowed_ids[0],
        "titleZh": "忠实的中文论文标题",
        "summaryZh": "不超过140字的中文摘要",
        "question": "研究问题",
        "method": "论文摘要明确说明的方法",
        "findings": "论文摘要明确说明的发现",
        "limitations": "摘要未说明",
        "tags": ["研究标签"],
    }]}
    result = request_structured_json(
        runtime,
        instructions=(
            "你是前沿研究编辑。只能依据论文标题和摘要，不得补充摘要中不存在的实验结果。"
            "为每篇论文生成忠实的中文标题、不超过140字的中文摘要，并分别提炼研究问题、方法、主要发现和局限性。"
            "摘要未明确局限时写‘摘要未说明’，预印本不得描述为已经同行评审。专有名词、模型名和数值必须保真。"
        ),
        input_text="研究论文元数据：\n" + json.dumps(evidence, ensure_ascii=False),
        schema_name="frontier_research",
        schema=schema,
        example=example,
        max_tokens=int(config.get("research_ai_max_output_tokens", config.get("research_openai_max_output_tokens", 10000))),
    )
    edited: dict[str, dict[str, Any]] = {}
    allowed = set(allowed_ids)
    for item in result.get("items", []):
        item_id = clean_text(item.get("id")) if isinstance(item, dict) else ""
        required_text = ("titleZh", "summaryZh", "question", "method", "findings", "limitations")
        if (
            item_id in allowed
            and item_id not in edited
            and all(clean_text(item.get(field_name)) for field_name in required_text)
            and isinstance(item.get("tags"), list)
        ):
            edited[item_id] = item
    if len(edited) != len(papers):
        raise ValueError(f"research editorial response contained {len(edited)} valid papers; expected {len(papers)}")
    for item in edited.values():
        item["_provider"] = runtime["provider"]
    return edited


def research_item_from_paper(
    paper: ResearchPaper, editorial: dict[str, Any] | None = None
) -> dict[str, Any]:
    editorial = editorial or {}
    original_summary = clean_text(paper.abstract, 520)
    summary = clean_text(editorial.get("summaryZh") or original_summary, 520)
    findings = clean_text(editorial.get("findings"), 320)
    key_facts = [value for value in (
        clean_text(editorial.get("question"), 260),
        clean_text(editorial.get("method"), 260),
        findings,
    ) if value]
    if not key_facts and summary:
        key_facts = [summary]
    source = {
        "name": paper.source,
        "domain": "arxiv.org" if paper.source.lower() == "arxiv" else domain_from_url(paper.url),
        "url": paper.url,
        "publishedAt": paper.published_at.isoformat().replace("+00:00", "Z"),
        "evidenceGroup": "repository:arxiv" if paper.source.lower() == "arxiv" else f"repository:{paper.source.lower()}",
    }
    tags = [clean_text(tag, 28) for tag in editorial.get("tags", paper.tags) if clean_text(tag)][:5]
    return {
        "id": paper.id,
        "contentType": "paper",
        "title": clean_text(editorial.get("titleZh") or paper.title, 220),
        "originalTitle": paper.title,
        "summary": summary,
        "abstract": original_summary,
        "keyFacts": key_facts,
        "why": f"该研究与{paper.research_area}相关；结论仍需结合完整论文、实验设置与后续同行评审判断。",
        "category": "研究论文",
        "researchArea": paper.research_area,
        "source": paper.source,
        "country": "国际",
        "publishedAt": paper.published_at.isoformat().replace("+00:00", "Z"),
        "updatedAt": paper.updated_at.isoformat().replace("+00:00", "Z"),
        "url": paper.url,
        "pdfUrl": paper.pdf_url,
        "authors": paper.authors,
        "arxivCategories": paper.categories,
        "primaryCategory": paper.primary_category,
        "collectionKeywords": paper.collection_keywords,
        "peerReviewStatus": "预印本 · 未经 arXiv 同行评审" if paper.source.lower() == "arxiv" else "评审状态未标注",
        "question": clean_text(editorial.get("question"), 320),
        "method": clean_text(editorial.get("method"), 320),
        "findings": findings,
        "limitations": clean_text(editorial.get("limitations"), 320),
        "score": max(0, min(100, round(paper.score))),
        "scoreBasis": "研究相关度",
        "scoreComponents": {},
        "scoreReasons": [
            f"主题：{paper.research_area}",
            *([f"采集关键词：{'、'.join(paper.collection_keywords)}"] if paper.collection_keywords else []),
            "按主题相关性、摘要完整度与发布时间排序",
        ],
        "confidence": "预印本" if paper.source.lower() == "arxiv" else "资料源",
        "confidenceReason": "该条目来自论文资料库；摘要展示不等同于独立复现或同行评审结论。",
        "tags": tags,
        "translationProvider": clean_text(editorial.get("_provider")),
        "image": "",
        "corroboration": 1,
        "sources": [source],
    }


def build_research_report(
    papers: list[ResearchPaper], config: dict[str, Any], now: datetime, skip_ai: bool
) -> dict[str, Any]:
    research = config.get("research", {})
    selected = choose_research_diverse(papers, config)
    editorial: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    method = "metadata"
    editorial_status = "disabled" if skip_ai else "not-configured"
    runtime = resolve_ai_runtime(config) if not skip_ai else None
    target_count = 0
    if selected and runtime:
        default_limit = research.get("deepseek_ai_limit", len(selected)) if runtime["provider"] == "deepseek" else research.get("ai_limit", 20)
        target_count = max(1, min(len(selected), int(default_limit)))
        batch_size = max(1, min(20, int(research.get("ai_batch_size", 10))))
        consecutive_failures = 0
        for start in range(0, target_count, batch_size):
            batch = selected[start:min(target_count, start + batch_size)]
            try:
                editorial.update(ai_edit_research(batch, config, runtime))
                consecutive_failures = 0
            except Exception as exc:
                reason = clean_text(str(exc), 180) or exc.__class__.__name__
                warnings.append(f"论文中文编辑批次失败（{start + 1}-{start + len(batch)}）：{reason}")
                LOGGER.warning("Research editorial batch failed: %s", reason)
                consecutive_failures += 1
                if consecutive_failures >= 2 and start + batch_size < target_count:
                    warnings.append("论文中文编辑连续失败 2 个批次，已停止后续调用并保留原始摘要")
                    break
        if editorial:
            method = runtime["provider"]
        editorial_status = "ok" if len(editorial) == target_count else "partial" if editorial else "fallback"
        if editorial_status != "ok" and not warnings:
            warnings.append(f"论文中文编辑不完整：{len(editorial)}/{target_count}")
    items = [research_item_from_paper(paper, editorial.get(paper.id)) for paper in selected]
    area_counts: dict[str, int] = {}
    for item in items:
        area = str(item.get("researchArea", "前沿研究"))
        area_counts[area] = area_counts.get(area, 0) + 1
    return {
        "schemaVersion": 2,
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "timezone": config.get("timezone", "Asia/Tokyo"),
        "rangeDays": int(research.get("lookback_days", 7)),
        "method": method,
        "editorialStatus": editorial_status,
        "editorialProvider": runtime.get("provider") if runtime else "",
        "editorialModel": runtime.get("model") if runtime else "",
        "translatedItemCount": len(editorial),
        "warnings": warnings,
        "itemCount": len(items),
        "areaCounts": area_counts,
        "collectionKeywords": [
            {"label": definition["label"], "query": definition["query"]}
            for definition in research_keyword_definitions(config)
        ],
        "items": items,
    }


def fallback_brief(items: list[dict[str, Any]], source_count: int) -> dict[str, Any]:
    leader = items[0]
    return {
        "headline": leader["title"],
        "summary": f"本期从 {source_count} 个公开信源筛选出 {len(items)} 条重点事件，覆盖科技、AI、航空航天、安全动态与无人系统。",
        "signals": [f"{item['category']}：{item['summary']}" for item in items[:3]],
    }


def build_report(candidates: list[Article], config: dict[str, Any], now: datetime, skip_ai: bool) -> dict[str, Any]:
    top_n = int(config["top_n"])
    shortlist = candidates[: int(config["candidate_limit"])]
    selected = choose_diverse(shortlist, config, top_n)
    editorial_by_id: dict[str, dict[str, Any]] = {}
    ai_brief: dict[str, Any] | None = None
    method = "rules"
    editorial_status = "disabled" if skip_ai else "not-configured"
    pipeline_warnings: list[str] = []
    runtime = resolve_ai_runtime(config) if not skip_ai else None
    if runtime:
        editorial_status = "running"
        try:
            ai_result = ai_select(shortlist, config, runtime)
            allowed = {article.id: article for article in shortlist}
            ai_order: list[Article] = []
            for item in ai_result.get("items", []):
                candidate = allowed.get(str(item.get("id")))
                if candidate and candidate not in ai_order:
                    ai_order.append(candidate)
                    item["_provider"] = runtime["provider"]
                    editorial_by_id[candidate.id] = item
            if len(ai_order) != top_n:
                raise ValueError(f"AI editorial pass returned {len(ai_order)} unique valid items; expected {top_n}")
            validate_ai_diversity(ai_order, editorial_by_id, config)
            selected = ai_order
            ai_brief = ai_result.get("brief")
            method = runtime["provider"]
            editorial_status = "ok"
        except Exception as exc:
            reason = clean_text(str(exc), 220) or exc.__class__.__name__
            editorial_status = "fallback"
            pipeline_warnings.append(f"AI 编辑失败，已使用规则选稿：{reason}")
            editorial_by_id.clear()
            LOGGER.warning("AI editorial pass failed; using deterministic fallback: %s", reason)
    if method in {"openai", "deepseek"}:
        # The AI result has already passed the strict category/domain check, so
        # discard any relaxation flags left by the deterministic preview pass.
        for article in selected:
            article.diversity_relaxed = False
            article.selection_note = (
                f"24 小时候选不足，作为 {article.selection_window_hours} 小时窗口补充观察"
                if article.is_supplemental else ""
            )
    supplemental_count = sum(article.is_supplemental for article in selected)
    diversity_relaxed_count = sum(article.diversity_relaxed for article in selected)
    if supplemental_count:
        oldest_window = max(article.selection_window_hours for article in selected)
        pipeline_warnings.append(
            f"24 小时内合格候选不足，Top 10 中有 {supplemental_count} 条来自最多 {oldest_window} 小时补充窗口，卡片已明确标注"
        )
    if diversity_relaxed_count:
        pipeline_warnings.append(
            f"候选主题或来源分布不均，已分级放宽配额补足 Top 10（{diversity_relaxed_count} 条已标注）"
        )
    items = [item_from_article(article, config, editorial_by_id.get(article.id)) for article in selected]
    items.sort(key=lambda item: (item["score"], item["publishedAt"]), reverse=True)
    source_count = len({
        (evidence.get("evidenceGroup") or evidence.get("domain") or evidence.get("name") or "").lower()
        for article in candidates
        for evidence in (article.evidence_sources or [source_evidence(article)])
        if evidence.get("evidenceGroup") or evidence.get("domain") or evidence.get("name")
    })
    brief = ai_brief if isinstance(ai_brief, dict) else fallback_brief(items, source_count)
    signals = [clean_text(signal, 180) for signal in brief.get("signals", []) if clean_text(signal)][:3]
    if len(signals) < 3:
        signals = fallback_brief(items, source_count)["signals"]
    local_time = now.astimezone(ZoneInfo(config.get("timezone", "Asia/Tokyo")))
    return {
        "schemaVersion": 4,
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "editionDate": local_time.strftime("%Y-%m-%d"),
        "timezone": config.get("timezone", "Asia/Tokyo"),
        "method": method,
        "editorialStatus": editorial_status,
        "editorialProvider": runtime.get("provider") if runtime else "",
        "editorialModel": runtime.get("model") if runtime else "",
        "translatedItemCount": len(editorial_by_id),
        "warnings": pipeline_warnings,
        "candidateCount": len(candidates),
        "freshCandidateCount": sum(not article.is_supplemental for article in candidates),
        "supplementalCandidateCount": sum(article.is_supplemental for article in candidates),
        "freshItemCount": top_n - supplemental_count,
        "supplementalItemCount": supplemental_count,
        "coverageStatus": "supplemented" if supplemental_count or diversity_relaxed_count else "complete",
        "effectiveLookbackHours": max(article.selection_window_hours for article in selected),
        "sourceCount": source_count,
        "scoring": {
            "label": "重要度，不等同于事实真伪",
            "formula": "基础分 + 来源 + 主题优先级 + 时效 + 影响信号 + 相关性 + 证据完整度 + 多源印证 - 编辑降权",
            "confidenceNote": "置信度仅反映已收录来源的权重与独立来源数量，不替代事实核查。",
        },
        "brief": {
            "headline": clean_text(brief.get("headline"), 120) or items[0]["title"],
            "summary": clean_text(brief.get("summary"), 260) or fallback_brief(items, source_count)["summary"],
            "signals": signals,
        },
        "items": items,
    }


def validate_report(report: dict[str, Any], expected_count: int) -> None:
    items = report.get("items")
    if not isinstance(items, list) or len(items) != expected_count:
        raise ValueError(f"report must contain exactly {expected_count} items")
    ids: set[str] = set()
    required = {
        "id", "title", "originalTitle", "summary", "keyFacts", "why", "category", "source",
        "publishedAt", "url", "score", "scoreBasis", "scoreComponents", "scoreReasons",
        "confidence", "confidenceReason", "tags", "sources",
    }
    for index, item in enumerate(items, 1):
        missing = required.difference(item)
        if missing:
            raise ValueError(f"item {index} missing: {', '.join(sorted(missing))}")
        if item["id"] in ids:
            raise ValueError(f"duplicate item id: {item['id']}")
        ids.add(item["id"])
        if item["category"] not in CATEGORIES:
            raise ValueError(f"invalid category: {item['category']}")
        if not str(item["url"]).startswith(("http://", "https://")):
            raise ValueError(f"invalid URL in item {index}")
        if not isinstance(item["keyFacts"], list) or not item["keyFacts"]:
            raise ValueError(f"item {index} must include at least one key fact")
        if not isinstance(item["sources"], list) or not item["sources"]:
            raise ValueError(f"item {index} must include at least one source")
    translated = sum(bool(item.get("translationProvider")) for item in items)
    if int(report.get("translatedItemCount", translated)) != translated:
        raise ValueError("daily translatedItemCount does not match items")


def validate_stream_report(report: dict[str, Any]) -> None:
    items = report.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("stream report must contain at least one qualified item")
    if int(report.get("itemCount", -1)) != len(items):
        raise ValueError("stream itemCount does not match items")
    ids = [clean_text(item.get("id")) for item in items if isinstance(item, dict)]
    if not all(ids) or len(ids) != len(set(ids)):
        raise ValueError("stream report contains missing or duplicate ids")
    if any(item.get("contentType") != "news" for item in items):
        raise ValueError("stream report may only contain news items")
    translated = sum(bool(item.get("translationProvider")) for item in items)
    if int(report.get("translatedItemCount", translated)) != translated:
        raise ValueError("stream translatedItemCount does not match items")


def validate_research_report(report: dict[str, Any], *, allow_empty: bool = True) -> None:
    items = report.get("items")
    if not isinstance(items, list) or (not allow_empty and not items):
        raise ValueError("research report items are missing")
    if int(report.get("itemCount", -1)) != len(items):
        raise ValueError("research itemCount does not match items")
    ids: set[str] = set()
    for index, item in enumerate(items, 1):
        if item.get("contentType") != "paper":
            raise ValueError(f"research item {index} has invalid contentType")
        item_id = clean_text(item.get("id"))
        if not item_id or item_id in ids:
            raise ValueError(f"research item {index} has missing or duplicate id")
        ids.add(item_id)
        if not str(item.get("url", "")).startswith(("http://", "https://")):
            raise ValueError(f"research item {index} has invalid URL")
    translated = sum(bool(item.get("translationProvider")) for item in items)
    if int(report.get("translatedItemCount", translated)) != translated:
        raise ValueError("research translatedItemCount does not match items")


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(encoded)
        temp_name = handle.name
    os.replace(temp_name, path)


def write_atom_feed(report: dict[str, Any], path: Path, site_url: str) -> None:
    """Publish a standards-based Atom feed without introducing a backend service."""
    atom = "http://www.w3.org/2005/Atom"
    ET.register_namespace("", atom)
    feed = ET.Element(f"{{{atom}}}feed")
    ET.SubElement(feed, f"{{{atom}}}id").text = "urn:frontier-pulse:daily"
    ET.SubElement(feed, f"{{{atom}}}title").text = "智域前沿 · 全球科技与安全态势日报"
    ET.SubElement(feed, f"{{{atom}}}updated").text = str(report["generatedAt"])
    ET.SubElement(feed, f"{{{atom}}}subtitle").text = clean_text(report.get("brief", {}).get("summary"), 260)

    base = site_url.strip().rstrip("/") + "/" if site_url.strip() else ""
    if base.startswith(("http://", "https://")):
        ET.SubElement(feed, f"{{{atom}}}link", {"rel": "self", "href": urllib.parse.urljoin(base, "feed.xml")})
        ET.SubElement(feed, f"{{{atom}}}link", {"rel": "alternate", "href": base})

    edition = str(report.get("editionDate", ""))
    for item in report.get("items", []):
        item_id = clean_text(item.get("id"))
        entry = ET.SubElement(feed, f"{{{atom}}}entry")
        ET.SubElement(entry, f"{{{atom}}}id").text = f"urn:frontier-pulse:{edition}:{item_id}"
        ET.SubElement(entry, f"{{{atom}}}title").text = clean_text(item.get("title"))
        published_at = clean_text(item.get("publishedAt") or report["generatedAt"])
        ET.SubElement(entry, f"{{{atom}}}updated").text = published_at
        ET.SubElement(entry, f"{{{atom}}}published").text = published_at
        ET.SubElement(entry, f"{{{atom}}}category", {"term": clean_text(item.get("category") or "前沿技术")})
        author = ET.SubElement(entry, f"{{{atom}}}author")
        ET.SubElement(author, f"{{{atom}}}name").text = clean_text(item.get("source") or "公开来源")
        if base.startswith(("http://", "https://")):
            anchor = re.sub(r"[^a-zA-Z0-9_-]+", "-", item_id).strip("-") or "story"
            permalink = urllib.parse.urljoin(base, f"?view=history&date={edition}#item-{anchor}")
            ET.SubElement(entry, f"{{{atom}}}link", {"rel": "alternate", "href": permalink})
        source_url = str(item.get("url", ""))
        if source_url.startswith(("http://", "https://")):
            ET.SubElement(entry, f"{{{atom}}}link", {"rel": "related", "href": source_url})
        facts = "；".join(clean_text(fact) for fact in item.get("keyFacts", []) if clean_text(fact))
        content = clean_text(item.get("summary"))
        if facts:
            content += f" 关键事实：{facts}"
        ET.SubElement(entry, f"{{{atom}}}summary").text = content

    path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(feed)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
        tree.write(handle, encoding="utf-8", xml_declaration=True)
        temp_name = handle.name
    os.replace(temp_name, path)


def read_json_safe(path: Path, fallback: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return fallback


SEARCHABLE_FIELDS = (
    "id", "title", "originalTitle", "summary", "keyFacts", "category", "source",
    "country", "publishedAt", "tags", "isSupplemental", "selectionWindowHours",
    "selectionNote", "diversityRelaxed",
)


def compact_search_item(item: dict[str, Any], edition: str) -> dict[str, Any]:
    compact = {field: item[field] for field in SEARCHABLE_FIELDS if field in item}
    compact["editionDate"] = edition
    compact["_compact"] = True
    return compact


def read_existing_search_items(search_output: Path) -> list[dict[str, Any]]:
    previous = read_json_safe(search_output, {})
    if not isinstance(previous, dict):
        return []
    if isinstance(previous.get("items"), list):
        return [item for item in previous["items"] if isinstance(item, dict)]
    items: list[dict[str, Any]] = []
    for shard in previous.get("shards", []):
        month = str(shard.get("month", "")) if isinstance(shard, dict) else ""
        if not re.fullmatch(r"\d{4}-\d{2}", month):
            continue
        payload = read_json_safe(search_output.parent / f"search-{month}.json", {})
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            items.extend(item for item in payload["items"] if isinstance(item, dict))
    return items


def archive_report(
    report: dict[str, Any],
    archive_dir: Path,
    index_output: Path,
    search_output: Path,
    retention_days: int,
) -> None:
    """Store one replaceable-by-date edition plus compact navigation/search indexes."""
    edition = str(report["editionDate"])
    archive_path = archive_dir / f"{edition}.json"
    write_json_atomic(archive_path, report)

    previous_index = read_json_safe(index_output, {})
    editions = previous_index.get("editions", []) if isinstance(previous_index, dict) else []
    category_counts: dict[str, int] = {}
    for item in report["items"]:
        category = str(item.get("category", "其他"))
        category_counts[category] = category_counts.get(category, 0) + 1
    entry = {
        "editionDate": edition,
        "generatedAt": report["generatedAt"],
        "headline": report.get("brief", {}).get("headline", ""),
        "summary": report.get("brief", {}).get("summary", ""),
        "method": report.get("method", "rules"),
        "itemCount": len(report["items"]),
        "sourceCount": int(report.get("sourceCount", 0)),
        "categoryCounts": category_counts,
        "file": f"./data/archive/{edition}.json",
    }
    editions = [item for item in editions if isinstance(item, dict) and item.get("editionDate") != edition]
    editions.append(entry)
    editions.sort(key=lambda item: str(item.get("editionDate", "")), reverse=True)
    editions = editions[: max(1, retention_days)]
    write_json_atomic(index_output, {
        "schemaVersion": 1,
        "generatedAt": report["generatedAt"],
        "timezone": report.get("timezone", "Asia/Tokyo"),
        "editions": editions,
    })

    search_items = read_existing_search_items(search_output)
    allowed_editions = {str(item.get("editionDate")) for item in editions}
    search_items = [
        item for item in search_items
        if isinstance(item, dict)
        and item.get("editionDate") != edition
        and str(item.get("editionDate")) in allowed_editions
    ]
    for item in report["items"]:
        search_items.append(compact_search_item(item, edition))
    search_items.sort(key=lambda item: (str(item.get("editionDate", "")), int(item.get("score", 0))), reverse=True)

    monthly: dict[str, list[dict[str, Any]]] = {}
    for item in search_items:
        item_edition = str(item.get("editionDate", ""))
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item_edition):
            continue
        monthly.setdefault(item_edition[:7], []).append(compact_search_item(item, item_edition))

    shards: list[dict[str, Any]] = []
    active_shard_names: set[str] = set()
    for month in sorted(monthly, reverse=True):
        items = sorted(
            monthly[month],
            key=lambda item: (str(item.get("editionDate", "")), str(item.get("publishedAt", ""))),
            reverse=True,
        )
        shard_name = f"search-{month}.json"
        active_shard_names.add(shard_name)
        shard_path = search_output.parent / shard_name
        previous_shard = read_json_safe(shard_path, {})
        shard_generated_at = report["generatedAt"]
        if month != edition[:7] and isinstance(previous_shard, dict):
            shard_generated_at = previous_shard.get("generatedAt") or shard_generated_at
        write_json_atomic(shard_path, {
            "schemaVersion": 2,
            "generatedAt": shard_generated_at,
            "timezone": report.get("timezone", "Asia/Tokyo"),
            "month": month,
            "itemCount": len(items),
            "items": items,
        })
        dates = sorted({str(item["editionDate"]) for item in items})
        shards.append({
            "month": month,
            "file": f"./data/archive/{shard_name}",
            "itemCount": len(items),
            "editionCount": len(dates),
            "fromDate": dates[0],
            "toDate": dates[-1],
        })

    for old_shard in search_output.parent.glob("search-????-??.json"):
        if old_shard.name not in active_shard_names:
            old_shard.unlink()

    write_json_atomic(search_output, {
        "schemaVersion": 2,
        "generatedAt": report["generatedAt"],
        "timezone": report.get("timezone", "Asia/Tokyo"),
        "editionCount": len(editions),
        "itemCount": sum(len(items) for items in monthly.values()),
        "searchableFields": list(SEARCHABLE_FIELDS),
        "shards": shards,
    })


def write_pipeline_status(
    path: Path,
    *,
    state: str,
    now: datetime,
    message: str,
    report: dict[str, Any] | None = None,
    stream_report: dict[str, Any] | None = None,
    research_report: dict[str, Any] | None = None,
) -> None:
    previous = read_json_safe(path, {})
    previous = previous if isinstance(previous, dict) else {}
    success = state == "ok" and report is not None
    payload = {
        "schemaVersion": 4,
        "state": state,
        "lastAttemptAt": now.isoformat().replace("+00:00", "Z"),
        "lastSuccessAt": now.isoformat().replace("+00:00", "Z") if success else previous.get("lastSuccessAt"),
        "editionDate": report.get("editionDate") if success else previous.get("editionDate"),
        "itemCount": len(report.get("items", [])) if success else previous.get("itemCount", 0),
        "message": clean_text(message, 300),
        "method": report.get("method") if success else previous.get("method"),
        "editorialStatus": report.get("editorialStatus") if success else previous.get("editorialStatus"),
        "editorialProvider": report.get("editorialProvider") if success else previous.get("editorialProvider"),
        "editorialModel": report.get("editorialModel") if success else previous.get("editorialModel"),
        "translatedItemCount": int(report.get("translatedItemCount", 0)) if success else previous.get("translatedItemCount", 0),
        "warnings": report.get("warnings", []) if success else previous.get("warnings", []),
        "coverageStatus": report.get("coverageStatus") if success else previous.get("coverageStatus"),
        "freshItemCount": int(report.get("freshItemCount", 0)) if success else previous.get("freshItemCount", 0),
        "supplementalItemCount": int(report.get("supplementalItemCount", 0)) if success else previous.get("supplementalItemCount", 0),
        "effectiveLookbackHours": int(report.get("effectiveLookbackHours", 0)) if success else previous.get("effectiveLookbackHours", 0),
        "streamItemCount": int(stream_report.get("itemCount", 0)) if success and stream_report else previous.get("streamItemCount", 0),
        "streamTranslationProvider": stream_report.get("translationProvider") if success and stream_report else previous.get("streamTranslationProvider"),
        "streamTranslationModel": stream_report.get("translationModel") if success and stream_report else previous.get("streamTranslationModel"),
        "streamTranslatedItemCount": int(stream_report.get("translatedItemCount", 0)) if success and stream_report else previous.get("streamTranslatedItemCount", 0),
        "streamTranslationWarnings": stream_report.get("translationWarnings", []) if success and stream_report else previous.get("streamTranslationWarnings", []),
        "researchItemCount": int(research_report.get("itemCount", 0)) if success and research_report else previous.get("researchItemCount", 0),
        "researchEditorialStatus": research_report.get("editorialStatus") if success and research_report else previous.get("researchEditorialStatus"),
        "researchEditorialProvider": research_report.get("editorialProvider") if success and research_report else previous.get("researchEditorialProvider"),
        "researchEditorialModel": research_report.get("editorialModel") if success and research_report else previous.get("researchEditorialModel"),
        "researchTranslatedItemCount": int(research_report.get("translatedItemCount", 0)) if success and research_report else previous.get("researchTranslatedItemCount", 0),
        "researchWarnings": research_report.get("warnings", []) if success and research_report else previous.get("researchWarnings", []),
    }
    write_json_atomic(path, payload)


def write_stream_status(
    path: Path,
    *,
    state: str,
    now: datetime,
    message: str,
    stream_report: dict[str, Any] | None = None,
) -> None:
    previous = read_json_safe(path, {})
    previous = previous if isinstance(previous, dict) else {}
    success = state == "ok" and stream_report is not None
    write_json_atomic(path, {
        "schemaVersion": 2,
        "state": state,
        "lastAttemptAt": now.isoformat().replace("+00:00", "Z"),
        "lastSuccessAt": now.isoformat().replace("+00:00", "Z") if success else previous.get("lastSuccessAt"),
        "itemCount": int(stream_report.get("itemCount", 0)) if success else previous.get("itemCount", 0),
        "translationProvider": stream_report.get("translationProvider") if success else previous.get("translationProvider"),
        "translationModel": stream_report.get("translationModel") if success else previous.get("translationModel"),
        "translatedItemCount": int(stream_report.get("translatedItemCount", 0)) if success else previous.get("translatedItemCount", 0),
        "translationWarnings": stream_report.get("translationWarnings", []) if success else previous.get("translationWarnings", []),
        "message": clean_text(message, 300),
    })


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the Frontier Pulse daily dataset")
    parser.add_argument("--config", type=Path, default=Path("config/news_config.json"))
    parser.add_argument("--output", type=Path, default=Path("public/data/news.json"))
    parser.add_argument("--stream-output", type=Path, default=Path("public/data/stream.json"))
    parser.add_argument("--research-output", type=Path, default=Path("public/data/research.json"))
    parser.add_argument("--stream-status-output", type=Path, default=Path("public/data/stream-status.json"))
    parser.add_argument("--archive-dir", type=Path, default=Path("public/data/archive"))
    parser.add_argument("--archive-index", type=Path, default=Path("public/data/archive/index.json"))
    parser.add_argument("--search-index", type=Path, default=Path("public/data/archive/search-index.json"))
    parser.add_argument("--status-output", type=Path, default=Path("public/data/status.json"))
    parser.add_argument("--feed-output", type=Path, default=Path("public/feed.xml"))
    parser.add_argument("--fixture", type=Path, help="Use a local fixture instead of live sources")
    parser.add_argument("--research-fixture", type=Path, help="Use a local research fixture instead of arXiv")
    parser.add_argument("--skip-ai", action="store_true", help="Disable optional DeepSeek/OpenAI editorial translation")
    parser.add_argument("--skip-research", action="store_true", help="Do not refresh the research radar")
    parser.add_argument("--stream-only", action="store_true", help="Refresh the full stream without replacing the daily Top 10")
    parser.add_argument("--now", help="Override current time for deterministic tests")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(levelname)s %(message)s")
    now = parse_datetime(args.now, utc_now()) if args.now else utc_now()
    try:
        config = load_config(args.config)
        if args.fixture:
            raw = collect_fixture(args.fixture, now)
        else:
            raw = collect_rss(config, now) + collect_gdelt(config, now)
        primary_window = int(config["lookback_hours"])
        stream_candidates = score_articles(
            deduplicate(raw), config, now, lookback_hours=primary_window
        )

        # The three-hour stream is a fresh, already-validated resilience input.
        # It protects the daily job from a transient RSS/GDELT outage without
        # turning old editions into apparently new stories.
        if not args.stream_only:
            recovery = config.get("daily_recovery", {})
            stream_cache_age = max(1, int(recovery.get("stream_cache_max_age_hours", 8)))
            cached_stream = collect_public_cache(
                args.stream_output,
                now,
                max_item_age_hours=primary_window,
                max_generated_age_hours=stream_cache_age,
            )
            if cached_stream:
                recovered_primary = score_articles(
                    deduplicate([*raw, *cached_stream]),
                    config,
                    now,
                    lookback_hours=primary_window,
                )
                if len(recovered_primary) > len(stream_candidates):
                    LOGGER.info(
                        "Fresh stream cache increased the 24-hour pool from %d to %d",
                        len(stream_candidates),
                        len(recovered_primary),
                    )
                    stream_candidates = recovered_primary

        if not stream_candidates:
            raise RuntimeError("没有合格的 24 小时候选；已保留上一版全量动态与日报")

        report: dict[str, Any] | None = None
        if not args.stream_only:
            top_n = int(config["top_n"])
            candidates = list(stream_candidates)
            if len(candidates) < top_n:
                recovery = config.get("daily_recovery", {})
                windows = sorted({
                    int(window) for window in recovery.get("backfill_windows_hours", [36, 48, 72])
                    if int(window) > primary_window
                })
                if not windows:
                    windows = [max(primary_window + 24, 48)]
                maximum_window = windows[-1]
                recovery_raw = list(raw)
                if not args.fixture:
                    recovery_raw.extend(collect_gdelt(config, now, lookback_hours=maximum_window))
                recovery_raw.extend(collect_public_cache(
                    args.output,
                    now,
                    max_item_age_hours=maximum_window,
                ))
                known_ids = {article.id for article in candidates}
                for window in windows:
                    expanded = score_articles(
                        deduplicate(recovery_raw), config, now, lookback_hours=window
                    )
                    for article in expanded:
                        if article.id in known_ids:
                            continue
                        candidates.append(article)
                        known_ids.add(article.id)
                    if len(candidates) >= top_n:
                        LOGGER.warning(
                            "Only %d fresh candidates were available; recovered %d candidates within %d hours",
                            len(stream_candidates),
                            len(candidates),
                            window,
                        )
                        break
            if len(candidates) < top_n:
                raise RuntimeError(
                    f"分层补采后仍只有 {len(candidates)} 条可验证候选；需要 {top_n} 条，已保留上一期内容"
                )
            report = build_report(candidates, config, now, args.skip_ai)
            validate_report(report, int(config["top_n"]))

        if report:
            top_stories = {str(item["id"]): item for item in report["items"]}
        else:
            previous_daily = read_json_safe(args.output, {})
            previous_items = previous_daily.get("items", []) if isinstance(previous_daily, dict) else []
            top_stories = {
                str(item["id"]): item for item in previous_items
                if isinstance(item, dict) and clean_text(item.get("id"))
            }
        stream_runtime = resolve_ai_runtime(config) if not args.skip_ai else None
        stream_translations: dict[str, dict[str, Any]] = {}
        stream_translation_warnings: list[str] = []
        if (
            stream_runtime
            and stream_runtime["provider"] == "deepseek"
            and bool(config.get("stream_translation_enabled", True))
        ):
            previous_stream = read_json_safe(args.stream_output, {})
            current_by_id = {article.id: article for article in stream_candidates}
            can_reuse_translations = (
                isinstance(previous_stream, dict)
                and clean_text(previous_stream.get("translationProvider")) == stream_runtime["provider"]
                and clean_text(previous_stream.get("translationModel")) == stream_runtime["model"]
            )
            previous_stream_items = previous_stream.get("items", []) if can_reuse_translations else []
            for item in previous_stream_items if isinstance(previous_stream_items, list) else []:
                item_id = clean_text(item.get("id")) if isinstance(item, dict) else ""
                article = current_by_id.get(item_id)
                if (
                    article
                    and clean_text(item.get("translationProvider")) == stream_runtime["provider"]
                    and clean_text(item.get("originalTitle")) == clean_text(article.title)
                    and clean_text(item.get("title"))
                    and clean_text(item.get("summary"))
                ):
                    stream_translations[item_id] = {
                        "titleZh": item["title"],
                        "summary": item["summary"],
                        "tags": item.get("tags", []),
                        "_translationOnly": True,
                        "_provider": stream_runtime["provider"],
                    }
            translation_limit = max(0, min(
                int(config.get("stream_limit", 300)),
                int(config.get("stream_translation_limit", 120)),
            ))
            already_translated = {
                item_id for item_id, item in top_stories.items()
                if isinstance(item, dict) and clean_text(item.get("translationProvider"))
            } | set(stream_translations)
            translation_candidates = [
                article for article in stream_candidates[:translation_limit]
                if article.id not in already_translated
            ]
            new_translations, stream_translation_warnings = ai_translate_articles(
                translation_candidates, config, stream_runtime
            )
            stream_translations.update(new_translations)
        stream_report = build_stream_report(
            stream_candidates,
            config,
            now,
            top_stories,
            stream_translations,
            stream_runtime if stream_translations else None,
            stream_translation_warnings,
        )
        validate_stream_report(stream_report)

        research_report: dict[str, Any] | None = None
        research_should_write = False
        research_collection_warning = ""
        if not args.skip_research:
            if args.research_fixture:
                raw_papers = collect_research_fixture(args.research_fixture, now, config)
            elif args.fixture:
                raw_papers = []
            else:
                raw_papers = collect_arxiv(config, now)
            papers = score_research_papers(raw_papers, config, now)
            if papers:
                research_report = build_research_report(papers, config, now, args.skip_ai)
                validate_research_report(research_report, allow_empty=False)
                research_should_write = True
            else:
                previous_research = read_json_safe(args.research_output, {})
                if isinstance(previous_research, dict) and isinstance(previous_research.get("items"), list) and previous_research["items"]:
                    research_collection_warning = "论文抓取未返回合格条目，已保留上一版论文雷达"
                    research_report = dict(previous_research)
                    research_report["editorialStatus"] = "stale"
                    research_report["warnings"] = list(previous_research.get("warnings", [])) + [research_collection_warning]
                    LOGGER.warning(research_collection_warning)
                else:
                    research_report = build_research_report([], config, now, args.skip_ai)
                    validate_research_report(research_report)
                    research_should_write = True

        if args.stream_only:
            write_json_atomic(args.stream_output, stream_report)
            if research_report is not None and research_should_write:
                write_json_atomic(args.research_output, research_report)
            write_stream_status(
                args.stream_status_output,
                state="ok",
                now=now,
                message=f"全量动态更新成功，共 {stream_report['itemCount']} 条",
                stream_report=stream_report,
            )
            LOGGER.info("Wrote %s with %d qualified stream items", args.stream_output, stream_report["itemCount"])
            return 0

        assert report is not None
        archive_report(
            report,
            args.archive_dir,
            args.archive_index,
            args.search_index,
            int(config.get("archive_retention_days", 730)),
        )
        write_json_atomic(args.output, report)
        write_json_atomic(args.stream_output, stream_report)
        if research_report is not None and research_should_write:
            write_json_atomic(args.research_output, research_report)
        write_atom_feed(
            report,
            args.feed_output,
            os.getenv("SITE_URL", "").strip() or str(config.get("site_url", "")),
        )
        success_message = "日报更新成功"
        if report.get("warnings"):
            success_message += "；" + "；".join(report["warnings"])
        if research_report and research_report.get("warnings"):
            success_message += "；" + "；".join(research_report["warnings"])
        write_pipeline_status(
            args.status_output,
            state="ok",
            now=now,
            message=success_message,
            report=report,
            stream_report=stream_report,
            research_report=research_report,
        )
        write_stream_status(
            args.stream_status_output,
            state="ok",
            now=now,
            message=f"全量动态更新成功，共 {stream_report['itemCount']} 条",
            stream_report=stream_report,
        )
        LOGGER.info("Wrote %s with %d stories using %s selection", args.output, len(report["items"]), report["method"])
        return 0
    except Exception as exc:
        LOGGER.error("%s update failed: %s", "Stream" if args.stream_only else "Daily", exc)
        try:
            if args.stream_only:
                write_stream_status(args.stream_status_output, state="failed", now=now, message=str(exc))
            else:
                write_pipeline_status(args.status_output, state="failed", now=now, message=str(exc))
        except Exception as status_exc:
            LOGGER.error("Could not write pipeline status: %s", status_exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
