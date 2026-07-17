#!/usr/bin/env python3
"""Build the daily Frontier Pulse static news dataset.

The collector uses only Python's standard library so GitHub Actions can run it
without a dependency install. OpenAI is optional: when OPENAI_API_KEY is set,
one Responses API request selects and summarizes the daily top stories. When it
is absent or unavailable, deterministic ranking and evidence-preserving
summaries keep the pipeline operational.
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
USER_AGENT = "FrontierPulseBot/1.4 (+https://github.com/voilalz/frontier-pulse; daily public-interest news index)"
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
                time.sleep(1.2 * (attempt + 1))
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


def collect_gdelt(config: dict[str, Any], now: datetime) -> list[Article]:
    endpoint = config["gdelt_endpoint"]
    lookback = int(config["lookback_hours"])
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
        payload = json.loads(http_get(url).decode("utf-8"))
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


def score_articles(articles: list[Article], config: dict[str, Any], now: datetime) -> list[Article]:
    threshold = now - timedelta(hours=int(config["lookback_hours"]))
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
        }
        total = sum(
            value for key, value in article.score_components.items() if not key.endswith("降权")
        ) - penalty - date_penalty
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
            reasons.append(f"发布时间无法解析，按 {int(config['lookback_hours'])} 小时窗口边缘处理并降权")
        article.score_reasons = reasons
        scored.append(article)
    return sorted(scored, key=lambda item: (item.raw_score, item.published_at), reverse=True)


def choose_diverse(candidates: list[Article], config: dict[str, Any], count: int) -> list[Article]:
    category_limit = int(config["per_category_limit"])
    domain_limit = int(config["per_domain_limit"])
    selected: list[Article] = []
    category_counts: dict[str, int] = {}
    domain_counts: dict[str, int] = {}
    for article in candidates:
        if category_counts.get(article.category, 0) >= category_limit:
            continue
        domain_key = article.domain or article.source
        if domain_counts.get(domain_key, 0) >= domain_limit:
            continue
        selected.append(article)
        category_counts[article.category] = category_counts.get(article.category, 0) + 1
        domain_counts[domain_key] = domain_counts.get(domain_key, 0) + 1
        if len(selected) == count:
            return selected
    raise ValueError(
        f"多样性约束后仅能选出 {len(selected)} 条；需要 {count} 条，"
        f"每类上限 {category_limit}、每域名上限 {domain_limit}"
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


def ai_select(candidates: list[Article], config: dict[str, Any], api_key: str) -> dict[str, Any]:
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
    body = {
        "model": os.getenv("OPENAI_MODEL") or config.get("openai_model", "gpt-5.6-luna"),
        "store": False,
        "instructions": (
            "你是国际科技与安全新闻编辑。只能依据提供的标题、描述、来源和时间工作，不得补写候选材料中没有的事实。"
            "从候选中选择恰好10条最重要且类别尽量多样的新闻，优先考虑全球影响、技术/政策拐点、可信来源、时效与多源印证。"
            "为每条生成忠实、自然的中文标题（保留机构、型号和专有名词），并输出不超过90字的中文摘要、2至3条可由候选材料直接支持的关键事实、"
            "不超过70字的为什么重要、0-100重要度和最多3个短标签。关键事实不得把推断写成事实。"
            "军事与冲突新闻保持中性、事实与判断分离；信息不足时明确使用‘据公开信息’等保守表达。"
        ),
        "input": "候选新闻证据：\n" + json.dumps(evidence, ensure_ascii=False),
        "text": {"format": {"type": "json_schema", "name": "frontier_daily", "strict": True, "schema": schema}},
        "max_output_tokens": int(config.get("openai_max_output_tokens", 8000)),
    }
    error: Exception | None = None
    for attempt in range(2):
        try:
            payload = http_post_json("https://api.openai.com/v1/responses", body, api_key)
            result = json.loads(extract_response_text(payload))
            if len(result.get("items", [])) != 10:
                raise ValueError("structured response did not contain exactly 10 items")
            return result
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            error = exc
            if attempt == 0:
                time.sleep(1.5)
    raise RuntimeError(f"OpenAI structured output could not be parsed after one retry: {error}")


def item_from_article(article: Article, config: dict[str, Any], editorial: dict[str, Any] | None = None) -> dict[str, Any]:
    editorial = editorial or {}
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
    score_basis = "AI编辑评分" if editorial else "规则评分"
    if editorial:
        score_reasons = [f"AI 编辑重要度 {score}/100", f"规则参考分 {round(article.raw_score)}/100", *score_reasons]
    return {
        "id": article.id,
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
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if api_key and not skip_ai:
        editorial_status = "running"
        try:
            ai_result = ai_select(shortlist, config, api_key)
            allowed = {article.id: article for article in shortlist}
            ai_order: list[Article] = []
            for item in ai_result.get("items", []):
                candidate = allowed.get(str(item.get("id")))
                if candidate and candidate not in ai_order:
                    ai_order.append(candidate)
                    editorial_by_id[candidate.id] = item
            if len(ai_order) != top_n:
                raise ValueError(f"OpenAI editorial pass returned {len(ai_order)} unique valid items; expected {top_n}")
            validate_ai_diversity(ai_order, editorial_by_id, config)
            selected = ai_order
            ai_brief = ai_result.get("brief")
            method = "openai"
            editorial_status = "ok"
        except Exception as exc:
            reason = clean_text(str(exc), 220) or exc.__class__.__name__
            editorial_status = "fallback"
            pipeline_warnings.append(f"AI 编辑失败，已使用规则选稿：{reason}")
            editorial_by_id.clear()
            LOGGER.warning("OpenAI editorial pass failed; using deterministic fallback: %s", reason)
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
        "schemaVersion": 3,
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "editionDate": local_time.strftime("%Y-%m-%d"),
        "timezone": config.get("timezone", "Asia/Tokyo"),
        "method": method,
        "editorialStatus": editorial_status,
        "warnings": pipeline_warnings,
        "candidateCount": len(candidates),
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
    "country", "publishedAt", "tags",
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
) -> None:
    previous = read_json_safe(path, {})
    previous = previous if isinstance(previous, dict) else {}
    success = state == "ok" and report is not None
    payload = {
        "schemaVersion": 2,
        "state": state,
        "lastAttemptAt": now.isoformat().replace("+00:00", "Z"),
        "lastSuccessAt": now.isoformat().replace("+00:00", "Z") if success else previous.get("lastSuccessAt"),
        "editionDate": report.get("editionDate") if success else previous.get("editionDate"),
        "itemCount": len(report.get("items", [])) if success else previous.get("itemCount", 0),
        "message": clean_text(message, 300),
        "method": report.get("method") if success else previous.get("method"),
        "editorialStatus": report.get("editorialStatus") if success else previous.get("editorialStatus"),
        "warnings": report.get("warnings", []) if success else previous.get("warnings", []),
    }
    write_json_atomic(path, payload)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the Frontier Pulse daily dataset")
    parser.add_argument("--config", type=Path, default=Path("config/news_config.json"))
    parser.add_argument("--output", type=Path, default=Path("public/data/news.json"))
    parser.add_argument("--archive-dir", type=Path, default=Path("public/data/archive"))
    parser.add_argument("--archive-index", type=Path, default=Path("public/data/archive/index.json"))
    parser.add_argument("--search-index", type=Path, default=Path("public/data/archive/search-index.json"))
    parser.add_argument("--status-output", type=Path, default=Path("public/data/status.json"))
    parser.add_argument("--feed-output", type=Path, default=Path("public/feed.xml"))
    parser.add_argument("--fixture", type=Path, help="Use a local fixture instead of live sources")
    parser.add_argument("--skip-ai", action="store_true", help="Disable the optional OpenAI editorial pass")
    parser.add_argument("--allow-low-volume", action="store_true", help="Allow fewer candidates than min_candidates")
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
        candidates = score_articles(deduplicate(raw), config, now)
        minimum = int(config["min_candidates"])
        if len(candidates) < minimum and not args.allow_low_volume:
            raise RuntimeError(
                f"只有 {len(candidates)} 条合格候选，低于安全阈值 {minimum}；已保留上一期内容"
            )
        if len(candidates) < int(config["top_n"]):
            raise RuntimeError(f"至少需要 {int(config['top_n'])} 条候选，当前仅 {len(candidates)} 条")
        report = build_report(candidates, config, now, args.skip_ai)
        validate_report(report, int(config["top_n"]))
        archive_report(
            report,
            args.archive_dir,
            args.archive_index,
            args.search_index,
            int(config.get("archive_retention_days", 730)),
        )
        write_json_atomic(args.output, report)
        write_atom_feed(
            report,
            args.feed_output,
            os.getenv("SITE_URL", "").strip() or str(config.get("site_url", "")),
        )
        success_message = "日报更新成功"
        if report.get("warnings"):
            success_message += "；" + "；".join(report["warnings"])
        write_pipeline_status(args.status_output, state="ok", now=now, message=success_message, report=report)
        LOGGER.info("Wrote %s with %d stories using %s selection", args.output, len(report["items"]), report["method"])
        return 0
    except Exception as exc:
        LOGGER.error("Daily update failed: %s", exc)
        try:
            write_pipeline_status(args.status_output, state="failed", now=now, message=str(exc))
        except Exception as status_exc:
            LOGGER.error("Could not write pipeline status: %s", status_exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
