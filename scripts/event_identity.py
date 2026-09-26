"""Conservative article/event identity, with no network or model dependencies.

Article IDs and article URLs are immutable evidence. Semantic matches require a
dated headline with a shared action and a discriminative object/place. Missing
evidence means separate events. A related-story score is deliberately never read.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


IDENTITY_VERSION = 2
_EVENT_ID = re.compile(r"evt-[0-9a-f]{12}\Z")
_TRACKING = {"fbclid", "gclid", "dclid", "msclkid", "igshid", "mc_cid", "mc_eid"}
_GENERIC_PATHS = {"", "/", "/news", "/latest", "/articles", "/index.html", "/index.htm"}
_STOP = set("""a an the and or but for to of at in on by with from into over under
after before as its it their his her this that these those is are was were be been
has have had will would could may says said say new latest officials official
report reports reporting update updates developments development artificial
intelligence technology tech company companies program programme marketplace
mission missions model models satellite satellites rocket rockets spacecraft
vehicle vehicles fleet defense military army air force navy us united states
government ministry ministry's leaves leave dead death toll kills killed killing
three seven one two four five six eight nine ten first second third more least
people person injured injury injuries damages damage hit hits hospital power
station drone drones attack strike launch flight released release developer
developers russian russia ukrainian ukraine american european continues continue
journey toward towards aboard space NASA SpaceX""".lower().split())
_ALIASES = (
    (r"\brussian\b|俄罗斯", "russia"),
    (r"\bukrainian\b|乌克兰", "ukraine"),
    (r"\bisraeli\b|以色列", "israel"),
    (r"\biranian\b|伊朗", "iran"),
    (r"\bkiev\b|基辅", "kyiv"),
    (r"\bkharkov\b|哈尔科夫", "kharkiv"),
    (r"莫斯科", "moscow"),
    (r"\bopen ai\b", "openai"),
    (r"\bspace x\b", "spacex"),
    (r"\bu\.s\.(?:a\.)?|\bunited states\b", "us"),
    (r"\blifts? off\b|\blifted off\b|\bblasts? off\b", "launch"),
)
_ACTIONS = {
    "lawsuit": r"\bsu(?:e|es|ed|ing)\b|\blawsuits?\b|\blitigation\b|起诉|诉讼",
    "attack": r"\battack(?:s|ed|ing)?\b|\bstrikes?\b|\bassault(?:s|ed)?\b|\bbomb(?:ing|ings|ed)?\b|袭击|轰炸",
    "launch": r"\blaunch(?:es|ed|ing)?\b|\bliftoff\b|发射|升空",
    "release": r"\breleas(?:e|es|ed|ing)\b|\bunveil(?:s|ed|ing)?\b|\bintroduc(?:e|es|ed|ing)\b|\bdebut(?:s|ed)?\b|发布|推出",
    "withdraw": r"\bwithdraw(?:s|n|ing)?\b|\bretract(?:s|ed|ing)?\b|\brecall(?:s|ed|ing)?\b|撤回|召回",
    "funding": r"\brais(?:e|es|ed|ing)\b|\bfunding\b|\bfundrais(?:e|ing)\b|融资",
    "acquire": r"\bacquir(?:e|es|ed|ing)\b|\bacquisition\b|\bbuys?\b|\bbought\b|收购",
    "approve": r"\bapprov(?:e|es|ed|al)\b|\bauthoriz(?:e|es|ed|ation)\b|批准|获批",
    "reject": r"\breject(?:s|ed|ion)?\b|\bblocks?\b|\bban(?:s|ned)?\b|拒绝|禁止",
    "discover": r"\bdiscover(?:s|ed|y)?\b|\bdetect(?:s|ed|ion)?\b|发现|探测到",
    "test": r"\btest(?:s|ed|ing)?\b|\bdemonstrat(?:e|es|ed|ion)\b|测试|试验",
    "investigate": r"\binvestigat(?:e|es|ed|ing|ion)\b|\binquir(?:y|ies)\b|调查",
    "land": r"\bland(?:s|ed|ing)?\b|着陆|降落",
    "establish": r"\bestablish(?:es|ed|ing)?\b|\bstands? up\b|\bstood up\b|\bsets? up\b|设立|成立",
}
_ACTORS = {
    "russia", "ukraine", "israel", "iran", "hamas", "hezbollah", "houthi",
    "openai", "anthropic", "google", "microsoft", "meta", "amazon", "apple",
    "spacex", "rocket lab", "blue origin", "nasa", "esa", "boeing", "airbus",
    "saildrone", "blue water autonomy", "anduril", "palantir", "nvidia",
}
_PLACES = {
    "kyiv", "kharkiv", "moscow", "odesa", "odessa", "lviv", "dnipro", "sumy",
    "donetsk", "zaporizhzhia", "kursk", "belgorod", "gaza", "rafah", "beirut",
    "tehran", "haifa", "tel aviv", "jerusalem", "baghdad", "damascus", "yemen",
    "florida", "texas", "california", "virginia", "new zealand", "london",
    "paris", "berlin", "new york", "washington", "tokyo", "seoul", "taipei",
}
_OBJECTS = {
    "europa clipper", "starship", "starlink", "siriusxm", "artemis", "orion",
    "crew dragon", "cygnus", "progress", "soyuz", "new glenn", "electron",
    "gpt", "claude", "gemini", "llama", "grok", "musv",
}
_FOLLOWUP = re.compile(
    r"\b(?:death toll|toll) (?:rises|rose|reaches|climbs)\b|\baftermath\b|"
    r"\b(?:investigation|inquiry) (?:into|of)\b|\b(?:update|updates) (?:on|to)\b|"
    r"\b(?:continues|ongoing|survivors|rescued|recovery effort)\b|"
    r"\b(?:healthy|operational|communicating)\b.*\bafter\b.*\blaunch\b|"
    r"死亡人数.*(?:升至|上升)|后续|事故调查"
)
_RECURRENCE = re.compile(r"\banother\b|\bagain\b|\b(?:fresh|new|renewed|second) (?:attack|strike|assault)\b|再次|又一次|新一轮")
_WEEKDAYS = {day.lower(): index for index, day in enumerate(
    ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
)}
_ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10"}
_MONTHS = {name.lower(): index for index, name in enumerate(
    ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1
)}
_ACTION_PATTERNS = {name: re.compile(pattern) for name, pattern in _ACTIONS.items()}
_ACTION_WORDS = frozenset(word for pattern in _ACTIONS.values() for word in re.findall(r"[a-z]{3,}", pattern))
_NAMED_PHRASE = re.compile(r"\b[A-Z][A-Za-z0-9-]*(?:\s+[A-Z][A-Za-z0-9-]*)*\b")
_PLACE_PATTERN = re.compile(r"\b(?:in|at|near|from)\s+([A-Z][A-Za-z-]*(?:\s+[A-Z][A-Za-z-]*)*)\b")
_STATUS = re.compile(r"\b(?:plans?|planned|planning|proposes?|proposed|scheduled|expected|will|prepares?|preparing|delays?|delayed|postpones?|postponed|cancels?|cancelled|canceled)\b")


def _text(value: Any, limit: int = 2000) -> str:
    return " ".join(html.unescape(value).split())[:limit] if isinstance(value, str) else ""


def _normal(value: Any) -> str:
    text = unicodedata.normalize("NFKC", _text(value)).lower().replace("’", "'")
    for pattern, replacement in _ALIASES:
        text = re.sub(pattern, replacement, text)
    return re.sub(r"'s\b", "", text)


def _article_url(value: Any) -> str:
    raw = _text(value, 4096)
    try:
        parsed = urlsplit(raw)
        if parsed.scheme.lower() not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            return ""
        host = parsed.hostname.lower()
        port = parsed.port
        if port and (parsed.scheme.lower(), port) not in {("https", 443), ("http", 80)}:
            host += f":{port}"
        query = sorted((key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                       if not key.lower().startswith("utm_") and key.lower() not in _TRACKING)
        path = parsed.path.rstrip("/") or "/"
        if path.lower() in _GENERIC_PATHS and not any(key.lower() in {"id", "p", "story", "article", "aid"} for key, _ in query):
            return ""
        if re.match(r"^/(?:tags?|category|search|feeds?)(?:/|$)", path, re.I) or path.endswith((".rss", ".xml")):
            return ""
        return urlunsplit((parsed.scheme.lower(), host, path, urlencode(query), ""))
    except (TypeError, ValueError):
        return ""


def evidence_urls(item: dict[str, Any]) -> list[str]:
    """Return canonical article URLs, including corroborating source links."""
    values = [item.get("url")]
    if isinstance(item.get("urls"), list):
        values.extend(item["urls"])
    if isinstance(item.get("sources"), list):
        values.extend(source.get("url") for source in item["sources"] if isinstance(source, dict))
    return sorted({url for value in values if (url := _article_url(value))})


def _day(item: dict[str, Any]) -> date | None:
    for value in (item.get("publishedAt"), item.get("editionDate")):
        text = _text(value, 64)
        if not text:
            continue
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc).date() if parsed.tzinfo else parsed.date()
        except ValueError:
            continue
    return None


def _names(text: str, vocabulary: set[str]) -> frozenset[str]:
    return frozenset(name for name in vocabulary if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text))


def _identifiers(text: str, original: str) -> dict[str, frozenset[str]]:
    values: dict[str, set[str]] = {}
    # Only numbers bound to a named object matter. Casualties and funding
    # amounts are expected to change in follow-up reporting.
    for match in re.finditer(
        r"\b(gpt|claude|gemini|llama|grok|artemis|starlink|falcon|crew|soyuz|progress|"
        r"flight|mission|iphone|galaxy|sls|vulcan|ariane)\s*[- ]?\s*(\d+(?:[.\-]\d+)*(?:[a-z])?|viii|vii|iii|vi|iv|ii|ix|v|i|x)\b",
        text,
    ):
        family, number = match.groups()
        values.setdefault(family, set()).add(_ROMAN.get(number, number))
    # A capitalized unfamiliar product/mission can also carry a discriminating
    # number; bare counts such as casualties must never become identifiers.
    for match in re.finditer(r"\b([A-Z][A-Za-z]+)[ -]+(\d+(?:[.\-]\d+)*)\b", original):
        family, number = match.groups()
        if family.lower() not in _MONTHS and family.lower() not in _STOP:
            values.setdefault(_normal(family), set()).add(number)
    return {family: frozenset(numbers) for family, numbers in values.items()}


def _incident_dates(text: str, published: date | None) -> frozenset[str]:
    dates: set[str] = set(re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", text))
    months = "|".join(_MONTHS)
    for match in re.finditer(r"\b(" + months + r")\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(20\d{2}))?\b", text):
        month, day_number, year = match.groups()
        try:
            dates.add(date(int(year) if year else (published.year if published else 2000),
                           _MONTHS[month], int(day_number)).isoformat())
        except ValueError:
            continue
    for weekday, index in _WEEKDAYS.items():
        if re.search(r"\b" + weekday + r"\b", text):
            dates.add((published - timedelta(days=(published.weekday() - index) % 7)).isoformat()
                      if published else weekday)
    return frozenset(dates)


def _named_phrases(text: str) -> frozenset[str]:
    return frozenset(name for match in _NAMED_PHRASE.finditer(text)
                     if (name := _normal(match.group())) not in _STOP or name in _ACTORS)


def _roles(original: str, actions: frozenset[str]) -> tuple[frozenset[str], frozenset[str]]:
    """Use explicit headline positions only as conflict checks, never proof.

    This deliberately small English grammar catches unfamiliar companies and
    payloads without guessing entities from a shared carrier or generic words.
    """
    matches = [(name, match) for name, pattern in _ACTION_PATTERNS.items()
               if name in actions and (match := pattern.search(original.lower()))]
    if not matches:
        return frozenset(), frozenset()
    action_name, action = min(matches, key=lambda entry: entry[1].start())
    subject = _named_phrases(original[:action.start()])
    # A spacecraft can itself "lift off"; it is not a conflicting operator.
    subject = frozenset(name for name in subject if name not in _OBJECTS)
    after = original[action.end():]
    after = re.split(r"\b(?:aboard|on|from|to|for|in|at|after|with|over|against)\b", after, maxsplit=1, flags=re.I)[0]
    target = _named_phrases(after) if action_name in {"launch", "release", "acquire"} else frozenset()
    return subject, target


@dataclass(frozen=True)
class _Evidence:
    news_id: str
    urls: frozenset[str]
    headline: str
    day: date | None
    actions: frozenset[str]
    actors: frozenset[str]
    places: frozenset[str]
    objects: frozenset[str]
    acronyms: frozenset[str]
    identifiers: dict[str, frozenset[str]]
    anchors: frozenset[str]
    incident_dates: frozenset[str]
    followup: bool
    recurrence: bool
    subject: frozenset[str]
    target: frozenset[str]
    status: str


@lru_cache(maxsize=8192)
def _headline_evidence(original: str, day: date | None) -> _Evidence:
    headline = _normal(original)
    actions = frozenset(name for name, pattern in _ACTION_PATTERNS.items() if pattern.search(headline))
    # "Launch a lawsuit" is a filing, not a rocket or product launch.
    if "lawsuit" in actions:
        actions -= {"launch"}
    words = set(re.findall(r"[a-z][a-z0-9-]*", headline))
    anchors = words - _STOP - _ACTION_WORDS
    # U.S. Navy and US Navy must have the same explicit subject role.
    role_headline = re.sub(r"\bU\.S\.(?:A\.)?", "US", original, flags=re.I)
    subject, target = _roles(role_headline, actions)
    explicit_places = frozenset(_normal(match.group(1)) for match in _PLACE_PATTERN.finditer(original))
    status_match = _STATUS.search(headline)
    if (status_match and status_match.group().startswith("prepar")
            and re.search(r"\bto\s+$", headline[:status_match.start()])):
        # "stands up a hub to prepare systems" is an established center,
        # unlike "prepares to establish a center".
        status_match = None
    status = ""
    if status_match:
        word = status_match.group()
        status = "cancelled" if word.startswith("cancel") else "delayed" if word.startswith(("delay", "postpon")) else "planned"
    return _Evidence(
        "", frozenset(), headline, day,
        actions, _names(headline, _ACTORS), _names(headline, _PLACES) | explicit_places,
        _names(headline, _OBJECTS), frozenset(), _identifiers(headline, original), frozenset(anchors),
        _incident_dates(headline, day), bool(_FOLLOWUP.search(headline)),
        bool(_RECURRENCE.search(headline)), subject, target, status,
    )


def _evidence(item: dict[str, Any]) -> _Evidence:
    original = _text(item.get("originalTitle") or item.get("title"))
    parsed = _headline_evidence(original, _day(item))
    # Long named acronyms are discriminating objects when both publishers
    # explicitly name the same organization and founding action. A generic
    # common word or model-written summary alone never suffices to merge.
    acronyms = frozenset(re.findall(r"\b[A-Z][A-Z0-9]{4,11}\b", original + " " + _text(item.get("summary"), 600)))
    return replace(parsed, news_id=_text(item.get("id"), 200), urls=frozenset(evidence_urls(item)), acronyms=acronyms)


def _match(first: _Evidence, second: _Evidence, semantic: bool = True) -> str:
    if first.news_id and first.news_id == second.news_id:
        return "article-id"
    if first.urls & second.urls:
        return "article-url"
    if not semantic or not first.day or not second.day or not first.headline or not second.headline:
        return ""
    distance = abs((first.day - second.day).days)
    if distance > 30 or first.recurrence != second.recurrence or first.status != second.status:
        return ""
    for left, right in ((first.places, second.places), (first.actors, second.actors), (first.objects, second.objects),
                        (first.subject, second.subject), (first.target, second.target)):
        if left and right and not left & right:
            return ""
    for family in first.identifiers.keys() & second.identifiers.keys():
        if first.identifiers[family] != second.identifiers[family]:
            return ""
    if first.acronyms and second.acronyms and not first.acronyms & second.acronyms:
        return ""
    if first.incident_dates and second.incident_dates and not first.incident_dates & second.incident_dates:
        return ""

    common_objects = first.objects & second.objects
    common_anchors = first.anchors & second.anchors
    common_ids = first.identifiers.keys() & second.identifiers.keys()
    distinct_object = bool(common_objects - {"starship", "starlink", "gpt", "claude", "gemini", "llama", "grok", "artemis"})
    numbered_object = bool(common_ids and (common_objects or first.actors & second.actors))
    named_foundation = bool(
        first.acronyms & second.acronyms
        and (first.subject & second.subject or first.actors & second.actors)
        and "establish" in first.actions & second.actions
        and distance <= 7
    )
    # A repeated incident needs both a place and a concrete object; the actor
    # alone (or a generic topic such as "AI") cannot identify it.
    incident = "attack" in first.actions & second.actions
    incident_object = bool(first.places & second.places) and bool(
        set(re.findall(r"\b(?:hospital|school|airport|bridge|power station|refinery|port|market|hotel)\b", first.headline))
        & set(re.findall(r"\b(?:hospital|school|airport|bridge|power station|refinery|port|market|hotel)\b", second.headline))
    )
    anchored = distinct_object or numbered_object or (incident and incident_object) or len(common_anchors) >= 2 or named_foundation
    if not anchored:
        return ""
    shared_action = first.actions & second.actions
    # A launch failure investigation can continue a numbered mission; a
    # different business action on the same product is its own event.
    investigation_followup = numbered_object and bool(
        (first.followup or second.followup) and
        (("launch" in first.actions and "investigate" in second.actions) or
         ("launch" in second.actions and "investigate" in first.actions))
    )
    if not shared_action and not investigation_followup:
        return ""
    if shared_action and first.actions - {"investigate"} != second.actions - {"investigate"}:
        # Additional action words in "death toll ... after attack" are not
        # classified as actions; real opposing verbs remain distinct.
        if (first.actions | second.actions) & {"withdraw", "reject", "acquire", "approve", "land"}:
            return ""
    if distance:
        later = first if first.day > second.day else second
        same_incident_date = bool(first.incident_dates & second.incident_dates)
        if not later.followup and not same_incident_date and not named_foundation:
            return ""
        if distance > (30 if numbered_object else 7):
            return ""
        return "dated-specific-acronym-action" if named_foundation else "dated-followup"
    return "same-day-specific-acronym-action" if named_foundation else "same-day-object-action"


def same_event(first: dict[str, Any], second: dict[str, Any]) -> bool:
    """Match a discrete event; unrelated historical context is never evidence."""
    return bool(_match(_evidence(first), _evidence(second)))


def event_identity_record(item: dict[str, Any]) -> dict[str, Any]:
    """Make bounded, JSON-safe evidence to persist under identityRepresentatives.

    Keep ``semanticEligible`` unchanged when saving legacy exact-only members.
    Otherwise an old broad topic group would become a new fuzzy merge anchor.
    """
    identity = item.get("eventIdentity") if isinstance(item.get("eventIdentity"), dict) else {}
    record = {
        "identityVersion": IDENTITY_VERSION,
        "semanticEligible": identity.get("version") == IDENTITY_VERSION and identity.get("semanticEligible") is True,
        "id": _text(item.get("id"), 200),
        "eventId": _text(item.get("eventId"), 32),
        "originalTitle": _text(item.get("originalTitle") or item.get("title"), 400),
        "summary": _text(item.get("summary"), 600),
        "publishedAt": _text(item.get("publishedAt"), 40),
        "editionDate": _text(item.get("editionDate"), 10),
        "urls": [url for url in evidence_urls(item) if len(url) <= 512][:12],
    }
    while len(json.dumps(record)) >= 5900:
        if record["summary"]:
            record["summary"] = record["summary"][:len(record["summary"]) // 2]
        elif record["urls"]:
            record["urls"].pop()
        else:
            record["originalTitle"] = record["originalTitle"][:len(record["originalTitle"]) // 2]
    return record


def _stable_id(seed: str) -> str:
    return "evt-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def _sort_key(evidence: _Evidence) -> tuple[str, str, str, str]:
    return evidence.news_id, min(evidence.urls, default=""), str(evidence.day or ""), evidence.headline


def assign_event_ids(items: list[dict[str, Any]], previous_registry: dict[str, Any], config: dict[str, Any]) -> None:
    """Assign deterministic IDs in place, reusing only unambiguous registry evidence.

    ``config`` is accepted for pipeline compatibility. Broad association-score
    settings cannot relax the evidence requirements of this module.
    """
    del config
    evidence = [_evidence(item) for item in items]
    records = previous_registry.get("items", []) if isinstance(previous_registry, dict) else []
    saved_aliases = previous_registry.get("identityAliases", {}) if isinstance(previous_registry, dict) else {}
    saved_aliases = saved_aliases if isinstance(saved_aliases, dict) else {}
    def canonical_event(event_id: str) -> str:
        visited = set()
        while event_id in saved_aliases and event_id not in visited:
            visited.add(event_id)
            next_id = _text(saved_aliases[event_id], 32)
            if not _EVENT_ID.fullmatch(next_id):
                break
            event_id = next_id
        return event_id
    records = [record for record in records if isinstance(record, dict)
               and _EVENT_ID.fullmatch(_text(record.get("eventId")))] if isinstance(records, list) else []
    news_index: dict[str, set[str]] = {}
    url_index: dict[str, set[str]] = {}
    semantic_by_day: dict[date, list[tuple[str, _Evidence]]] = {}
    # Exact article evidence remains indexed across the full retained history.
    # Only headline parsing and semantic comparisons have a bounded time window.
    relevant_days = {current.day + timedelta(days=offset)
                     for current in evidence if current.day
                     for offset in range(-30, 31)}
    reusable: set[str] = set()
    reserved = {record["eventId"] for record in records}
    for record in records:
        event_id = canonical_event(record["eventId"])
        news_ids = record.get("newsIds", []) if isinstance(record.get("newsIds"), list) else []
        for news_id in news_ids:
            if news_id := _text(news_id, 200):
                news_index.setdefault(news_id, set()).add(event_id)
        for url in evidence_urls(record):
            url_index.setdefault(url, set()).add(event_id)
        representatives = record.get("identityRepresentatives", [])
        for representative in representatives if isinstance(representatives, list) else []:
            if not isinstance(representative, dict):
                continue
            saved_news_id = _text(representative.get("id"), 200)
            if saved_news_id:
                news_index.setdefault(saved_news_id, set()).add(event_id)
            for url in evidence_urls(representative):
                url_index.setdefault(url, set()).add(event_id)
            if representative.get("identityVersion") == IDENTITY_VERSION and representative.get("semanticEligible") is True:
                reusable.add(event_id)
                saved_day = _day(representative)
                if saved_day in relevant_days:
                    saved = _evidence(representative)
                    semantic_by_day.setdefault(saved_day, []).append((event_id, saved))

    assigned: list[str] = [""] * len(items)
    eligible = [True] * len(items)
    decisions = ["new-event"] * len(items)
    reasons = ["no-unambiguous-match"] * len(items)
    for index, current in enumerate(evidence):
        exact = set(news_index.get(current.news_id, set()))
        for url in current.urls:
            exact.update(url_index.get(url, set()))
        matches = exact
        if not matches and current.day:
            matches = {event_id
                       for offset in range(-30, 31)
                       for event_id, saved in semantic_by_day.get(current.day + timedelta(days=offset), ())
                       if _match(current, saved)}
        if len(matches) == 1:
            assigned[index] = next(iter(matches))
            eligible[index] = assigned[index] in reusable
            decisions[index] = "registry-match" if eligible[index] else "legacy-exact"
            reasons[index] = "immutable-article" if exact else "representative-object-action-time"
        elif len(matches) > 1:
            decisions[index] = "ambiguous-registry"
            reasons[index] = "multiple-event-identities"
            eligible[index] = False

    # Reconcile old split IDs only with a stronger, same-day named-founding
    # certificate. Ordinary fuzzy bridges remain separated as before.
    proposed: dict[str, set[str]] = {}
    for left in range(len(items)):
        for right in range(left + 1, len(items)):
            if (assigned[left] and assigned[right] and assigned[left] != assigned[right]
                    and eligible[left] and eligible[right]
                    and _match(evidence[left], evidence[right]) == "same-day-specific-acronym-action"):
                proposed.setdefault(assigned[left], set()).add(assigned[right])
                proposed.setdefault(assigned[right], set()).add(assigned[left])
    merges = {old: min(old, next(iter(peers)))
              for old, peers in proposed.items() if len(peers) == 1 and len(proposed.get(next(iter(peers)), ())) == 1
              and old > next(iter(peers))}
    if merges:
        assigned = [merges.get(event_id, event_id) for event_id in assigned]

    edges: dict[tuple[int, int], str] = {}
    neighbors: list[set[int]] = [set() for _ in items]
    for left in range(len(items)):
        for right in range(left + 1, len(items)):
            if assigned[left] and assigned[right] and assigned[left] != assigned[right]:
                continue
            reason = _match(evidence[left], evidence[right], eligible[left] and eligible[right])
            if reason:
                edges[left, right] = reason
                neighbors[left].add(right)
                neighbors[right].add(left)

    # A-B and B-C does not prove A-C. Remove ambiguous semantic bridges before
    # forming components instead of depending on the order of a greedy merge.
    ambiguous: set[int] = set()
    for index, adjacent in enumerate(neighbors):
        anchors = {assigned[other] for other in adjacent if assigned[other]}
        if len(anchors) > 1 or any(
            (min(left, right), max(left, right)) not in edges
            for left in adjacent for right in adjacent if left < right
        ):
            ambiguous.add(index)
            if not assigned[index]:
                decisions[index] = "ambiguous-batch"
                reasons[index] = "incompatible-matching-neighbors"
                eligible[index] = False

    remaining = set(range(len(items)))
    while remaining:
        start = min(remaining, key=lambda index: _sort_key(evidence[index]))
        group = {start}
        pending = [start]
        while pending:
            current = pending.pop()
            for other in neighbors[current] & remaining - group:
                reason = edges[min(current, other), max(current, other)]
                if (current in ambiguous or other in ambiguous) and reason not in {"article-id", "article-url"}:
                    continue
                group.add(other)
                pending.append(other)
        remaining -= group
        anchors = {assigned[index] for index in group if assigned[index]}
        # Conflicting exact URL chains also stay separate; neither registry
        # identity is silently aliased away.
        partitions = [group] if len(anchors) <= 1 else [{index} for index in sorted(group)]
        for partition in partitions:
            representative = min(partition, key=lambda index: _sort_key(evidence[index]))
            saved_id = next((assigned[index] for index in sorted(partition) if assigned[index]), "")
            seed_evidence = evidence[representative]
            seed = seed_evidence.news_id or min(seed_evidence.urls, default="") or json.dumps(_sort_key(seed_evidence))
            event_id = saved_id or _stable_id("identity-v2:" + seed)
            if not saved_id:
                while event_id in reserved:
                    event_id = _stable_id("separate:" + event_id + ":" + seed)
                reserved.add(event_id)
            group_eligible = all(eligible[index] for index in partition)
            for index in partition:
                item = items[index]
                item["eventId"] = event_id
                decision = decisions[index]
                if len(partition) > 1 and decision == "new-event":
                    decision = "batch-match"
                item["eventIdentity"] = {
                    "version": IDENTITY_VERSION,
                    "decision": decision,
                    "reason": reasons[index] if decision != "batch-match" else "unambiguous-article-or-object-action-time",
                    "semanticEligible": group_eligible,
                    "representativeId": seed_evidence.news_id,
                    "mergedFrom": sorted(old for old, canonical in merges.items() if canonical == event_id),
                    "evidence": {
                        "newsIds": sorted({evidence[member].news_id for member in partition if evidence[member].news_id})[:6],
                        "urls": sorted(set().union(*(evidence[member].urls for member in partition)))[:6],
                        "anchors": sorted(evidence[index].anchors)[:10],
                        "date": str(evidence[index].day or ""),
                    },
                }
