"""Select bounded public evidence without confusing neighbouring news stories.

This deliberately conservative, offline selector is not a semantic fact checker.
An explicit conflicting headline vetoes a body; body length never establishes
relevance. ``candidateCount`` counts paragraph/sentence candidates examined across
the page and feed, before deduplication and relevance filtering.
"""

from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
import json
import re
import unicodedata


_BUDGET = 6000
_INPUT_LIMIT = 1_000_000
_DASHES = str.maketrans({char: "-" for char in "‐‑‒–—−"})
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_WORD = re.compile(r"[^\W_]+(?:[-.][^\W_]+)*", re.UNICODE)
_STOP = set("""
a an and are as at be been being but by can could did do does for from had has
have he her his how i in into is it its may more most not of on or our out over
she so than that the their them there these they this those to up us was we were
what when where which who why will with would you your about after before during
new news latest breaking update first last next today yesterday tomorrow monday
tuesday wednesday thursday friday saturday sunday one two three say said says
report reports reported reporting release released releases launch launched launches
launching complete completes completed trial test tests testing announce announced
announces announcement reveal reveals revealed plan plans planned start starts
started begin begins began make makes made get gets go goes take takes now year
years day days month months week weeks world global international recent major
big small support government official officials detail details programme program
project system technology tech research study result results mission model ai
""".split())
_SKIP_TAGS = {"nav", "aside", "footer", "form", "button", "select", "input",
              "svg", "canvas", "iframe", "style", "script", "noscript", "template",
              "figcaption", "head"}
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
              "meta", "param", "source", "track", "wbr"}
_BLOCK_TAGS = {"p", "div", "section", "article", "main", "li", "ul", "ol",
               "blockquote", "br", "hr", "tr"}
_NOISE_ATTR = re.compile(
    r"(?:^|[\s_-])(?:ads?|advert(?:isement|ising)?|sponsored|newsletter|related|"
    r"recommend(?:ed|ation|ations)?|recirculation|most-popular|promo(?:tion)?|"
    r"share|social|navigation|sidebar|teaser|outbrain|taboola|breadcrumb|cookie|"
    r"consent)(?:$|[\s_-])", re.I)
_RESTRICTED_ATTR = re.compile(
    r"(?:^|[\s_-])(?:paywall|subscription-wall|subscriber-only|subscribers-only|"
    r"members-only|premium-content|restricted-content)(?:$|[\s_-])", re.I)
_RESTRICTED_TEXT = re.compile(
    r"\b(?:sign\s+in|log\s*in|subscribe|subscription\s+required)\s+"
    r"(?:to\s+(?:continue\s+)?(?:read|access|view)|for\s+full\s+access)\b", re.I)
_NOISE_TEXT = re.compile(
    r"^(?:read\s+(?:more|next)|also\s+read|related(?:\s+stories)?|recommended|"
    r"subscribe|sign\s+(?:in|up)|log\s*in|advertisement|sponsored|follow\s+us|"
    r"share\s+this|copyright|all\s+rights\s+reserved|newsletter|continue\s+reading|"
    r"more\s+from|most\s+(?:read|popular))\b", re.I)
_BODY_ATTR = re.compile(
    r"(?:^|[\s_-])(?:article|story|post|entry)[_-](?:body|content|text)(?:$|[\s_-])", re.I)
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_EVENT_ACTIONS = {
    "launch": re.compile(r"\b(?:launch(?:es|ed|ing)?|lift(?:s|ed)?\s+off|liftoff)\b"),
    "release": re.compile(r"\b(?:releas(?:e[sd]?|ing)|unveil(?:s|ed|ing)?|"
                          r"introduc(?:e[sd]?|ing)|debut(?:s|ed|ing)?)\b"),
}
_BLOCKED_EVENT = re.compile(
    r"\b(?:delay(?:s|ed|ing)?|postpon(?:e[sd]?|ing)|cancel(?:s|led|ed|ling|ing)?|"
    r"withdraw(?:s|n|ing)?|withdrew|halt(?:s|ed|ing)?|suspend(?:s|ed|ing)?|"
    r"discontinu(?:e[sd]?|ing)|retir(?:e[sd]?|ing)|no\s+longer\s+available)\b")


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()


def _normal(value: str) -> str:
    return unicodedata.normalize("NFKC", value).translate(_DASHES).casefold()


def _terms(value: str) -> set[str]:
    value = _CJK.sub(" ", _normal(value))
    # Keep product identifiers atomic, including typography such as GPT‑5/GPT 5.
    value = re.sub(r"\b([a-z][a-z0-9]{1,})[- ](\d+(?:\.\d+)*)\b",
                   lambda m: m[0] if m[1] in _STOP else m[1] + "-" + m[2], value)
    return {word for word in _WORD.findall(value)
            if len(word) >= 3 and not word.isdigit() and word not in _STOP}


def _cjk_grams(value: str) -> set[str]:
    return {run[index:index + 2] for run in _CJK.findall(_normal(value))
            for index in range(len(run) - 1)}


def _identifiers(words: set[str]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for word in words:
        match = re.fullmatch(r"([a-z]+)-?(\d+(?:\.\d+)*[a-z]?)", word)
        if match:
            result.setdefault(match[1], set()).add(match[2])
    return result


def _actions(text: str) -> set[str]:
    return {action for action, pattern in _EVENT_ACTIONS.items() if pattern.search(_normal(text))}


def _headline_state_conflicts(title: str, headline: str) -> bool:
    # A matching entity does not make a cancellation the launch story. Limit
    # this veto to headlines: a launch article may legitimately recount delays.
    # Trailing historical context ("launches ... after delays") is not its state.
    def state(text):
        primary = re.split(r"\b(?:after|following|despite)\b", _normal(text), maxsplit=1)[0]
        return bool(_BLOCKED_EVENT.search(primary)), bool(_actions(primary))

    title_blocked, title_active = state(title)
    headline_blocked, headline_active = state(headline)
    return ((title_active and not title_blocked and headline_blocked)
            or (headline_active and not headline_blocked and title_blocked))


def _short_feed_matches(title: str, paragraph: str, signature: "_Signature") -> bool:
    # A single short RSS lead can omit its publisher/agency while retaining a
    # subject and event. Do not give this weaker match to competing page bodies.
    common = signature.words.intersection(_terms(paragraph))
    title_acronyms = set(re.findall(r"\b[A-Z]{2,}\b", title))
    lead_acronyms = set(re.findall(r"\b[A-Z]{2,}\b", paragraph))
    return bool(len(paragraph) <= 400 and common
                and max(map(len, common)) >= 5
                and len(common) / max(len(signature.words), 1) >= 0.5
                and _actions(title).intersection(_actions(paragraph))
                and not signature.conflicts(paragraph)
                and not _headline_state_conflicts(title, paragraph)
                and not (title_acronyms and lead_acronyms - title_acronyms)
                and not _NOISE_TEXT.search(paragraph))


@dataclass
class _Signature:
    words: set[str]
    cjk: set[str]
    identifiers: dict[str, set[str]]

    def conflicts(self, text: str) -> bool:
        other = _identifiers(_terms(text))
        return any(family in other and not versions.intersection(other[family])
                   for family, versions in self.identifiers.items())

    def score(self, text: str) -> float:
        if self.conflicts(text):
            return 0.0
        words = _terms(text)
        common = self.words.intersection(words)
        identifier_hit = bool(self.identifiers.keys() & _identifiers(common).keys())
        coverage = len(common) / max(len(self.words), 1)
        latin_score = 0.0
        if identifier_hit or (len(common) >= 2 and coverage >= 0.35):
            latin_score = max(coverage, 0.65 if identifier_hit else 0.0)
        elif len(self.words) == 1 and common and len(next(iter(common))) >= 6:
            latin_score = 1.0
        cjk_common = self.cjk.intersection(_cjk_grams(text))
        cjk_coverage = len(cjk_common) / max(len(self.cjk), 1)
        cjk_score = cjk_coverage if len(cjk_common) >= 3 and cjk_coverage >= 0.4 else 0.0
        return max(latin_score, cjk_score)


@dataclass(eq=False)
class _Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    parent: "_Node | None" = None
    children: list = field(default_factory=list)
    ignored: bool = False


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("document")
        self.stack = [self.root]
        self.restricted = False
        self.meta_headline = ""

    def handle_starttag(self, tag, attrs):
        attrs = {key: value or "" for key, value in attrs}
        labels = " ".join(attrs.get(key, "") for key in ("class", "id", "role"))
        if (_RESTRICTED_ATTR.search(labels)
                or (attrs.get("itemprop", "").casefold() == "isaccessibleforfree"
                    and attrs.get("content", "").casefold() in {"false", "0"})):
            self.restricted = True
        if tag == "meta" and attrs.get("property", "").casefold() == "og:title":
            self.meta_headline = _clean(attrs.get("content", ""))
        if tag == "p" and self.stack[-1].tag == "p":
            self.stack.pop()
        if len(self.stack) > 128:
            raise ValueError("HTML nesting limit")
        hidden = ("hidden" in attrs or attrs.get("aria-hidden", "").casefold() == "true"
                  or re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)",
                               attrs.get("style", ""), re.I))
        node = _Node(tag, attrs, self.stack[-1], ignored=bool(
            self.stack[-1].ignored or tag in _SKIP_TAGS or hidden or _NOISE_ATTR.search(labels)))
        self.stack[-1].children.append(node)
        if tag not in _VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _walk(node: _Node):
    pending = [node]
    while pending:
        current = pending.pop()
        yield current
        pending.extend(child for child in reversed(current.children) if isinstance(child, _Node))


def _text(node: _Node, excluded: set[_Node] | None = None, raw: bool = False) -> str:
    if not raw and (node.ignored or (excluded and node in excluded)):
        return ""
    parts = []
    for child in node.children:
        if isinstance(child, str):
            parts.append(child)
        else:
            value = _text(child, excluded, raw)
            parts.append("\n" + value + "\n" if child.tag in _BLOCK_TAGS else value)
    return "".join(parts)


def _chunks(value: str, sentences: bool = False) -> list[str]:
    result = []
    for line in re.split(r"[\r\n]+", value):
        line = _clean(line)
        if not line:
            continue
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“'])|(?<=[。！？])\s*", line) if sentences or len(line) > 500 else [line]
        for part in parts:
            if not part:
                continue
            if result and re.search(r"\b(?:Mr|Mrs|Ms|Dr|Prof|Jr|Sr|Inc|Ltd|U\.S|U\.K)\.$", result[-1]):
                result[-1] += " " + part
            else:
                result.append(part)
    return result


def _paragraphs(root: _Node, excluded: set[_Node], sentences: bool = False) -> list[str]:
    result, buffer = [], []

    def flush():
        result.extend(_chunks("".join(buffer), sentences))
        buffer.clear()

    def visit(node):
        if node.ignored or node in excluded or node.tag in _HEADING_TAGS:
            flush()
            return
        if node.tag in _BLOCK_TAGS:
            flush()
        for child in node.children:
            if isinstance(child, str):
                buffer.append(child)
            else:
                visit(child)
        if node.tag in _BLOCK_TAGS:
            flush()

    visit(root)
    flush()
    return result


def _parse(value: str) -> _PageParser:
    parser = _PageParser()
    parser.feed(value[:_INPUT_LIMIT])
    parser.close()
    return parser


def _json_articles(value):
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, list):
            pending.extend(reversed(item))
        elif isinstance(item, dict):
            types = item.get("@type", [])
            types = [types] if isinstance(types, str) else types
            if isinstance(types, list) and any(
                    isinstance(kind, str) and kind.rsplit("/", 1)[-1].casefold()
                    in {"article", "newsarticle", "reportagenewsarticle", "analysisnewsarticle",
                        "techarticle", "blogposting"} for kind in types):
                yield item
            pending.extend(reversed(list(item.values())))


def _restricted_data(value) -> bool:
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            free = item.get("isAccessibleForFree", True)
            if free is False or free == 0 or (isinstance(free, str) and free.casefold() in {"false", "0"}):
                return True
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return False


def _page_candidates(page: str) -> tuple[list[tuple[str, list[str]]], bool]:
    parser = _parse(page)
    nodes = list(_walk(parser.root))
    candidates = []
    for node in nodes:
        if node.tag != "script" or node.attrs.get("type", "").split(";", 1)[0].strip().casefold() != "application/ld+json":
            continue
        try:
            data = json.loads(unescape(_text(node, raw=True)).strip())
        except (ValueError, TypeError, RecursionError):
            continue
        for article in _json_articles(data):
            parser.restricted = parser.restricted or _restricted_data(article)
            body = article.get("articleBody", "")
            headline = article.get("headline") or article.get("name") or ""
            if isinstance(body, str) and isinstance(headline, str):
                candidates.append((_clean(headline), _feed_paragraphs(body)))

    roots = set()
    for node in nodes:
        if node.ignored:
            continue
        labels = " ".join(node.attrs.get(key, "") for key in ("class", "id"))
        is_article = node.tag == "article" or node.attrs.get("role") == "article"
        is_body = (node.attrs.get("itemprop", "").casefold() == "articlebody"
                   or _BODY_ATTR.search(labels))
        parent, inside_body = node.parent, False
        while parent:
            if parent in roots and parent.tag != "main":
                inside_body = True
                break
            parent = parent.parent
        if is_article or ((is_body or node.tag == "main") and not inside_body):
            roots.add(node)

    def own_nodes(root):
        pending = [root]
        while pending:
            node = pending.pop()
            if node.ignored or (node is not root and node in roots):
                continue
            yield node
            pending.extend(child for child in reversed(node.children) if isinstance(child, _Node))

    page_headline = next((_clean(_text(node)) for node in own_nodes(parser.root)
                          if node.tag == "h1"), parser.meta_headline)
    for root in nodes:
        if root is not parser.root and root not in roots:
            continue
        local = list(own_nodes(root))
        headline = next((_clean(_text(node)) for node in local if node.tag == "h1"), "")
        if not headline and root.tag == "article":
            headline = next((_clean(_text(node)) for node in local if node.tag == "h2"), "")
        paragraphs = _paragraphs(root, roots - {root})
        if paragraphs:
            candidates.append((headline or page_headline, paragraphs))
    visible_text = _text(parser.root)
    return candidates, parser.restricted or bool(_RESTRICTED_TEXT.search(visible_text))


def _feed_paragraphs(lead: str) -> list[str]:
    if re.search(r"<[a-zA-Z][\s\S]*?>", lead):
        return _paragraphs(_parse(lead).root, set(), sentences=True)
    return _chunks(lead[:_INPUT_LIMIT], sentences=True)


def _selection(paragraphs: list[str], signature: _Signature) -> tuple[list[str], float]:
    unique, seen = [], set()
    for paragraph in paragraphs:
        paragraph = _clean(paragraph)
        key = _normal(paragraph)
        if paragraph and key not in seen:
            seen.add(key)
            unique.append(paragraph)
    scores = [0.0 if _NOISE_TEXT.search(p) else signature.score(p) for p in unique]
    context = {}
    for index, paragraph in enumerate(unique):
        if scores[index] or index == 0 or not scores[index - 1] or signature.conflicts(paragraph):
            continue
        reference = re.match(r"^(?:the|this|that|these|those|its)\s+([^\W_]+)\b", _normal(paragraph))
        if (reference and len(reference[1]) >= 5 and reference[1] not in _STOP
                and reference[1] in _terms(unique[index - 1]) and not _NOISE_TEXT.search(paragraph)):
            context[index] = index - 1

    selected, remaining = {}, _BUDGET
    ranked = sorted((index for index, score in enumerate(scores) if score),
                    key=lambda index: (-scores[index], index))
    ranked.extend(context)
    for index in ranked:
        if index in context and context[index] not in selected:
            continue
        paragraph = unique[index]
        separator = 2 if selected else 0
        if len(paragraph) + separator > remaining:
            if selected or remaining <= separator:
                continue
            paragraph = paragraph[:remaining].rsplit(" ", 1)[0].rstrip()
        if paragraph:
            selected[index] = paragraph
            remaining -= len(paragraph) + separator
    return [selected[index] for index in sorted(selected)], max(scores, default=0.0)


def select_relevant_evidence(title: str, lead: str, page: str) -> dict:
    """Return ordered evidence (at most 6,000 characters) and honest provenance.

    Public bodies compete as separate candidates. Restricted pages are discarded
    before selection; the independently supplied feed lead remains eligible.
    Unsupported titles return empty evidence rather than echoing their headline.
    """
    title, lead, page = (value if isinstance(value, str) else "" for value in (title, lead, page))
    words = _terms(title)
    signature = _Signature(words, _cjk_grams(title), _identifiers(words))
    try:
        candidates, restricted = _page_candidates(page) if page else ([], False)
    except (ValueError, RecursionError):
        candidates, restricted = [], False
    try:
        feed = _feed_paragraphs(lead)
    except (ValueError, RecursionError):
        feed = []
    count = sum(len(paragraphs) for _, paragraphs in candidates) + len(feed)
    best, best_rank = [], (-1.0, -1.0, -1.0)
    if not restricted:
        for headline, paragraphs in candidates:
            headline_score = signature.score(headline) if headline else 0.0
            if headline and (not headline_score or _headline_state_conflicts(title, headline)):
                continue
            chosen, score = _selection(paragraphs, signature)
            rank = (float(bool(headline)), headline_score, score)
            if chosen and rank > best_rank:
                best, best_rank = chosen, rank
    status, reason = "body", "selected-public-body"
    if not best:
        best, _ = _selection(feed, signature)
        if not best and len(feed) == 1 and _short_feed_matches(title, feed[0], signature):
            best = feed
        status = "feed" if best else "title-only"
        reason = ("restricted-page-" if restricted else "") + ("selected-feed" if best else "no-relevant-evidence")
    return {"text": "\n\n".join(best), "paragraphs": best, "status": status,
            "candidateCount": count, "selectedCount": len(best), "reason": reason}
