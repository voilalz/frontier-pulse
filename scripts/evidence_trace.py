"""Bounded, immutable excerpts captured from feeds or publisher pages.

References prove provenance, not semantic truth. The conservative claim gate
accepts extractive/abridged statements; unverifiable translations fall back to
the source excerpt rather than acquiring authority from a model summary.
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
import unicodedata
from decimal import Decimal
from datetime import datetime
from urllib.parse import urlsplit, unquote

from news_evidence import strip_caption_text

TRACE_VERSION = 1
_MISSING = re.compile(r"现有元数据|未提取到正文|正文(?:获取|提取)失败|没有详细摘要|详情应以原始报道为准")
_ABSENCE = re.compile(r"未披露|未公布|尚未公布|未说明|未提供|not (?:disclosed|published|provided)|undisclosed", re.I)
_STRONG = ("证明", "证实", "量产", "安全", "独立验证", "proven", "confirmed", "production", "safe")
_NUMERIC = re.compile(r"\d+(?:[.,]\d+)*(?:\s*(?:%|分钟|秒|小时|年|月|日|人|台|次|公里|米|美元|seconds?|minutes?|hours?|km|meters?|years?))?", re.I)
_NEGATED = re.compile(r"(?:尚未|并未|未曾|没有|未能|未)(完成|发射|部署|验证|量产|批准)|\b(?:not|never)\s+(?:yet\s+)?(completed?|launched?|deployed|approved|verified)\b", re.I)
_QUALIFIERS = tuple(re.compile(pattern, re.I) for pattern in (
    r"计划|拟开展|预计|将于|即将|\b(?:plans?|planned|will|scheduled|expected)\b",
    r"仅|只在|只进行|\b(?:only|limited)\b",
    r"模拟|\b(?:simulation|simulated)\b",
    r"初步|\bpreliminary\b",
    r"部分|小规模|\b(?:some|partial|small.scale)\b",
))
_STOP = set("a an the and or to of in on for with by is are was were has have that it said says".split())


def safe_url(value):
    if not isinstance(value, str) or re.search(r"[\s<>\\\x00-\x1f\x7f]", value):
        return False
    if re.search(r"[\\\x00-\x1f\x7f]", unquote(value)):
        return False
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        _ = parsed.port
        if parsed.scheme not in {"http", "https"} or parsed.username is not None or parsed.password is not None:
            return False
        if "." not in host or host.endswith((".localhost", ".local")):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return bool(re.fullmatch(r"[a-z0-9\u0080-\uffff.-]+", host))
    except ValueError:
        return False


def _stamp(value):
    try:
        return isinstance(value, str) and datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def _id(text, url, kind):
    return "evd-" + hashlib.sha256((url + "\n" + kind + "\n" + text).encode()).hexdigest()[:20]


def make_evidence(text, url, fetched_at, kind="body"):
    if not safe_url(url) or not _stamp(fetched_at) or kind not in {"body", "feed"}:
        return []
    records = []
    cleaned = strip_caption_text(text)
    for paragraph in re.split(r"\n\s*\n", cleaned):
        # Preserve sentence wording exactly after extraction whitespace cleanup.
        for sentence in re.split(r"(?<=[。！？])\s*|(?<=[.!?])\s+(?=[A-Z])", paragraph):
            sentence = re.sub(r"\s+", " ", sentence).strip()
            if len(sentence) < 10 or _MISSING.search(sentence):
                continue
            if len(sentence) > 600:
                sentence = sentence[:600].rsplit(" ", 1)[0] if " " in sentence[:600] else sentence[:600]
            records.append({"evidenceId": _id(sentence, url, kind), "text": sentence,
                            "url": url, "fetchedAt": fetched_at, "kind": kind})
            if len(records) >= 12:
                return merge_evidence(records)
    return merge_evidence(records)


def validate_evidence(records):
    if not isinstance(records, list) or len(records) > 144:
        raise ValueError("invalid evidence collection")
    seen = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {"evidenceId", "text", "url", "fetchedAt", "kind"}:
            raise ValueError("invalid evidence fields")
        text = record["text"]
        if (not isinstance(text, str) or not 10 <= len(text) <= 600
                or text != text.strip() or re.search(r"[<>\x00-\x1f]", text)
                or _MISSING.search(text) or strip_caption_text(text) != text
                or not safe_url(record["url"]) or not _stamp(record["fetchedAt"])
                or record["kind"] not in {"feed", "body"}
                or record["evidenceId"] != _id(text, record["url"], record["kind"])
                or record["evidenceId"] in seen):
            raise ValueError("invalid source evidence")
        seen.add(record["evidenceId"])


def merge_evidence(*groups):
    result, seen = [], set()
    for group in groups:
        for record in group:
            if record["evidenceId"] not in seen:
                result.append(dict(record)); seen.add(record["evidenceId"])
    return result[:144]


def _scope_preserved(source, claim):
    """A quoted fragment must not drop uncertainty, negation or units."""
    for pattern in _QUALIFIERS:
        if pattern.search(source) and not pattern.search(claim):
            return False
    negation = re.compile(r"并不|并非|尚未|并未|没有|未能|失败|不支持|不可靠|\b(?:not|never|failed|unsuccessful)\b", re.I)
    if negation.search(source) and not negation.search(claim):
        return False
    source_numbers = {re.sub(r"\s+", "", n.casefold()) for n in _NUMERIC.findall(source)}
    return all(re.sub(r"\s+", "", n.casefold()) in source_numbers for n in _NUMERIC.findall(claim))


def _literal_supported(claim, source):
    normalized = re.sub(r"\s+", " ", claim).strip().rstrip("。！？.!?").casefold()
    return bool(normalized and normalized in re.sub(r"\s+", " ", source).casefold()
                and _scope_preserved(source, claim))


def validate_claim_refs(text, refs, records):
    try:
        validate_evidence(records)
    except (ValueError, TypeError, KeyError):
        return False
    if not isinstance(text, str) or not text.strip() or not isinstance(refs, list) or not refs:
        return False
    by_id = {record["evidenceId"]: record for record in records}
    if any(not isinstance(ref, str) or ref not in by_id for ref in refs) or len(set(refs)) != len(refs):
        return False
    # Keep a complete sentence/clause relationship. Splitting at commas or
    # deleting arbitrary characters can attach ESA's number to NASA's action.
    sentences = re.split(r"(?<=[。！？])\s*|(?<=[.!?])\s+(?=[A-Z])", text)
    if all(any(_literal_supported(sentence, by_id[ref]["text"]) for ref in refs)
           for sentence in sentences if sentence.strip()):
        return True
    # A quoted next paragraph can defeat punctuation-based sentence splitting.
    # Accept only complete, unchanged referenced excerpts joined by spaces.
    claim = text.strip()
    quotes = {by_id[ref]["text"] for ref in refs}
    pending, visited = [0], set()
    while pending:
        start = pending.pop()
        if start in visited:
            continue
        visited.add(start)
        for quote in quotes:
            if not claim.startswith(quote, start):
                continue
            end = start + len(quote)
            if end == len(claim):
                return True
            if claim[end:end + 1] == " ":
                pending.append(end + 1)
    return False


def excerpt_summary(records, limit=600):
    """Choose whole bounded source excerpts, never truncate into new prose."""
    parts = []
    for record in records:
        if len(" ".join([*parts, record["text"]])) <= limit:
            parts.append(record["text"])
        if len(parts) == 3:
            break
    return " ".join(parts)


def source_limit_judgment(quote):
    match = re.search(r"(?:^|，)([^，。！？]{4,44}?)(?:尚未披露|尚未公布|未披露|未说明|未提供)", quote)
    return f"现有材料尚不足以判断{match[1].strip()}，需等后续公开信息。" if match else ""


def validate_observation(text, supports, events):
    if not isinstance(text, str) or not isinstance(supports, list) or not supports:
        return False
    records, quotes = [], []
    for support in supports:
        if not isinstance(support, dict): return False
        event = events.get(support.get("newsId"), {})
        available = event.get("evidenceRecords", [])
        try: validate_evidence(available)
        except (ValueError, TypeError, KeyError): return False
        quote = support.get("supportQuote")
        if not isinstance(quote, str) or not 10 <= len(quote) <= 220: return False
        matched = next((r for r in available if r["evidenceId"] == support.get("evidenceId") and quote in r["text"]), None)
        if matched is None: return False
        records.append(matched); quotes.append(quote)
    records = merge_evidence(records)
    if text in {source_limit_judgment(quote) for quote in quotes}:
        return len(supports) == 1
    return (validate_claim_refs(text, [r["evidenceId"] for r in records], records)
            and all(any(_literal_supported(sentence, quote) for quote in quotes)
                    for sentence in re.split(r"(?<=[。！？])\s*|(?<=[.!?])\s+(?=[A-Z])", text) if sentence.strip()))


def trace_claim(text, records):
    for record in records:
        refs = [record["evidenceId"]]
        if validate_claim_refs(text, refs, records):
            return refs
    refs = [record["evidenceId"] for record in records]
    return refs if validate_claim_refs(text, refs, records) else []


def safe_title(text, original, records):
    """Retain the raw headline unless the edit is a faithful literal excerpt."""
    if text == original:
        return original
    return text if isinstance(text, str) and _literal_supported(text, original) else original


def framing_supported(text, records, headlines=(), neutral=()):
    """Headings are source statements or exact editorial metadata templates."""
    return isinstance(text, str) and (text in headlines or text in neutral or bool(trace_claim(text, records)))


_NUMBER_WORDS = dict(zip(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety first second third fourth fifth sixth seventh eighth ninth tenth half".split(),
    list(range(21)) + list(range(30, 100, 10)) + list(range(1, 11)) + [0.5]))
_SCALES = {"hundred":100, "thousand":1000, "million":10**6, "billion":10**9, "trillion":10**12,
           "decade":10, "decades":10, "century":100, "centuries":100,
           "百":100, "千":1000, "万":10**4, "百万":10**6, "千万":10**7,
           "亿":10**8, "十亿":10**9, "万亿":10**12}
_SCALE_PATTERN = "|".join(sorted(_SCALES, key=len, reverse=True))
_MONTHS = "Jan(?:uary)? Feb(?:ruary)? Mar(?:ch)? Apr(?:il)? May Jun(?:e)? Jul(?:y)? Aug(?:ust)? Sep(?:tember)? Oct(?:ober)? Nov(?:ember)? Dec(?:ember)?".split()


def _quantity_key(amount):
    decimal = format(amount, "f")
    return "number:" + (decimal.rstrip("0").rstrip(".") if "." in decimal else decimal)


def quantity_values(text):
    """Normalize digits, ordinary number words, dates and decimal scale units."""
    text = unicodedata.normalize("NFKC", text)
    values = set()
    for match in re.finditer(r"(\d+(?:[.,]\d+)*)(?:\s*(" + _SCALE_PATTERN + r"))?", text, re.I):
        token = match[1].replace(",", "")
        if token.count(".") > 1:
            values.add("id:" + token)
            continue
        amount = Decimal(token) * _SCALES.get((match[2] or "").lower(), 1)
        values.add(_quantity_key(amount))
    words = "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True))
    tens = "twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"
    ones = "one|two|three|four|five|six|seven|eight|nine"
    expression = r"(?:" + tens + r")(?:[-\s]+(?:" + ones + r"))?|" + words
    for match in re.finditer(r"\b(" + expression + r")\b(?:\s+(" + _SCALE_PATTERN + r"))?", text, re.I):
        amount = sum(Decimal(str(_NUMBER_WORDS[word])) for word in re.split(r"[-\s]+", match[1].lower()))
        amount *= _SCALES.get((match[2] or "").lower(), 1)
        values.add(_quantity_key(amount))
    for month, pattern in enumerate(_MONTHS, 1):
        if re.search(r"\b" + pattern + r"\.?\s+\d{1,4}\b", text, re.I):
            values.add("number:" + str(month))
    for match in re.finditer(r"\b(\d{1,2})[.:](\d{2})\s*(am|pm)\b", text, re.I):
        hour, minute = int(match[1]), int(match[2])
        if 1 <= hour <= 12 and minute < 60:
            values.update("number:" + str(n) for n in (hour, minute, hour % 12 + (12 if match[3].lower() == "pm" else 0)))
    for match in re.finditer(r"\b(\d+(?:\.\d+)?)m\s+years?\b", text, re.I):
        values.add(_quantity_key(Decimal(match[1]) * 10**6))
    return values


def translation_text_valid(text, source):
    """Language/quantity sanity checks, not proof of semantic equivalence."""
    if not isinstance(source, str) or not isinstance(text, str) or not re.search(r"[\u4e00-\u9fff]", text):
        return False
    return quantity_values(text) <= quantity_values(source)


_TRANSLATION_SCOPE = tuple(re.compile(pattern, re.I) for pattern in (
    r"计划|规划|拟|预计|预期|将|即将|有望|预定|未来|可能|\b(?:plans?|planned|will|scheduled|expected|may|might|could)\b",
    r"仅|只|唯一|有限|限定|受限|限制|\b(?:only|limited)\b",
    r"模拟|仿真|\b(?:simulation|simulated)\b",
    r"初步|初期|初始|\bpreliminary\b",
    r"部分|一些|若干|少数|小规模|\b(?:some|partial|small.scale)\b",
    r"不|未|没有|无|失败|\b(?:not|no|without|never|failed|unsuccessful)\b|\b\w+n['’]t\b",
))


def _chinese_number(token):
    digits = dict(zip("零〇一二两三四五六七八九", [0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9]))
    if "点" in token:
        whole, fraction = token.split("点", 1)
        return _chinese_number(whole) + Decimal("0." + "".join(str(digits[char]) for char in fraction))
    for unit, scale in (("亿", 10**8), ("万", 10**4)):
        if unit in token:
            left, right = token.split(unit, 1)
            return _chinese_number(left or "一") * scale + _chinese_number(right)
    if not any(unit in token for unit in "十百千"):
        return Decimal("".join(str(digits[char]) for char in token) or "0")
    total, current = 0, 0
    for char in token:
        if char in digits:
            current = digits[char]
        else:
            total += (current or 1) * {"十": 10, "百": 100, "千": 1000}[char]
            current = 0
    return Decimal(total + current)


def _prose_quantities(text):
    text = unicodedata.normalize("NFKC", text)
    values = quantity_values(text)
    numeral = r"[零〇一二两三四五六七八九十百千万亿]+(?:点[零〇一二三四五六七八九]+)?"
    units = r"个|项|名|人|家|台|艘|架|颗|枚|辆|套|组|种|年|月|日|天|次|倍|米|秒|小时|美元|元|%|％"
    magnitudes = {"十": 10, "百": 100, "千": 1000, "万": 10**4, "百万": 10**6,
                  "千万": 10**7, "亿": 10**8, "十亿": 10**9, "万亿": 10**12}
    approximate = r"(?:数|几)(" + "|".join(sorted(magnitudes, key=len, reverse=True)) + r")(?=" + units + r")"
    def collect_approximate(match):
        values.add("approx:" + str(magnitudes[match[1]]))
        return " "
    exact_text = re.sub(approximate, collect_approximate, text)
    # Arabic coefficients and Chinese scales were already normalized together.
    # Do not count the 亿 in 244亿美元 a second time as an independent quantity.
    exact_text = re.sub(r"\d+(?:[.,]\d+)*\s*(?:万亿|百万|千万|十亿|亿|万|千|百)", " ", exact_text)
    for word, magnitude in {"tens": 10, "hundreds": 100, "thousands": 1000,
                            "millions": 10**6, "billions": 10**9, "trillions": 10**12}.items():
        if re.search(r"\b" + word + r"\b", text, re.I):
            values.add("approx:" + str(magnitude))
    # Count explicit quantities, rather than idioms such as '下一次' or '一同'.
    for match in re.finditer(r"(?<![上下每这那另唯])(" + numeral + r")(?=" + units + r")|百分之(" + numeral + r")", exact_text):
        values.add(_quantity_key(_chinese_number(match[1] or match[2])))
    if re.search(r"\b(?:a|an)\b", text, re.I):
        values.add("number:1")
    # 'The only ... weapon' entails a singular type; do not read 唯一一种 as 11.
    for match in re.finditer(r"\bonly\s+((?:[a-z]+[- ]+){0,4})(?:weapon|model|system|ship|capsule|company)\b", text, re.I):
        if not any(word.lower() in _NUMBER_WORDS for word in re.findall(r"[a-z]+", match[1], re.I)):
            values.add("number:1")
    return values


_NEGATIVE_ACTIONS = (
    (r"approv\w*|permission|clearance|authori[sz]\w*", r"批准|获批|许可|授权"),
    (r"production|commercial\w*", r"量产|生产|商用|商业化"),
    (r"publish\w*|reveal\w*|disclos\w*|announc\w*", r"公布|披露|发布|公开|宣布"),
    (r"launch\w*", r"发射|推出|发布"),
    (r"deploy\w*", r"部署"),
    (r"test\w*|validat\w*|prov\w*", r"测试|验证|证明"),
    (r"success\w*|succeed\w*", r"成功"),
)


def _translation_negation_valid(text, source):
    for clause in re.split(r"[.;,:]|\b(?:and|but)\b", source, flags=re.I):
        if not _TRANSLATION_SCOPE[-1].search(clause):
            continue
        for original, translated in _NEGATIVE_ACTIONS:
            if re.search(r"\b(?:" + original + r")\b", clause, re.I):
                # An unrelated negative date cannot negate an affirmative approval.
                if not re.search(r"(?:不|未|没有|无|失败)[^，。；！？,;.!?]{0,16}(?:" + translated + r")|(?:" + translated + r")(?:失败|未成功)", text):
                    return False
                break
    return True


def prose_translation_issue(value, source_text, evidence_refs):
    """Return a bounded reason without logging source prose or model content."""
    if not (isinstance(value, dict) and value.get("version") == 1
            and value.get("language") == "zh-CN" and isinstance(value.get("provider"), str)
            and value["provider"] in {"deepseek", "openai"}
            and isinstance(source_text, str) and 10 <= len(source_text) <= 900 and source_text == source_text.strip()
            and isinstance(evidence_refs, list) and bool(evidence_refs)
            and value.get("sourceText") == source_text and value.get("sourceEvidenceRefs") == evidence_refs
            and isinstance(value.get("text"), str) and 10 <= len(value["text"]) <= 900
            and value["text"] == value["text"].strip()
            and not re.search(r"[<>\x00-\x1f]|(?:https?|javascript|data|file|vbscript)\s*:", value["text"], re.I)):
        return "binding/format"
    text = value["text"]
    if not re.search(r"[\u4e00-\u9fff]", text):
        return "language"
    if re.search(r"(?a:\b)[a-z]{2,}(?:[\s\ufeff]+[a-z]{2,}){2,}(?a:\b)", text):
        return "untranslated-phrase"
    introduced = _prose_quantities(text) - _prose_quantities(source_text)
    if introduced:
        return "quantities:" + ",".join(sorted(introduced))
    if re.search(r"[\u4e00-\u9fff]", source_text) and text != source_text:
        return "Chinese-source-rewritten"
    if not _translation_negation_valid(text, source_text):
        return "negated-action"
    for label, pattern in zip(("planned", "limited", "simulation", "preliminary", "partial", "negation"), _TRANSLATION_SCOPE):
        if pattern.search(source_text) and not pattern.search(text):
            return "qualifier:" + label
    return ""


def valid_prose_translation(value, source_text, evidence_refs):
    """Validate a display translation bound to a separately verified source claim."""
    return not prose_translation_issue(value, source_text, evidence_refs)


def valid_display_translation(item):
    """Bind a display-only translation to the exact traceable source payload."""
    from reader_quality import chinese_reader_text
    value = item.get("displayTranslation")
    if not isinstance(value, dict):
        return False
    return (value.get("version") == 1 and value.get("language") == "zh-CN"
            and isinstance(value.get("provider"), str)
            and value.get("provider") in {"deepseek", "openai"}
            and isinstance(value.get("sourceTitle"), str)
            and isinstance(value.get("sourceSummary"), str)
            and value.get("sourceTitle") == item.get("originalTitle")
            and value.get("sourceSummary") == item.get("summary")
            and value.get("sourceEvidenceRefs") == item.get("summaryEvidenceRefs")
            and chinese_reader_text(value.get("title"))
            and translation_text_valid(value.get("title"), value["sourceTitle"])
            and ((chinese_reader_text(value.get("summary"))
                  and translation_text_valid(value.get("summary"), value["sourceTitle"] + " " + value["sourceSummary"]))
                 or (item.get("evidenceRecords") == [] and item.get("summaryEvidenceRefs") == []
                     and item.get("summary") == value.get("summary") == ""))
            and (validate_claim_refs(item.get("summary"), item.get("summaryEvidenceRefs"), item.get("evidenceRecords"))
                 or (item.get("evidenceRecords") == [] and item.get("summaryEvidenceRefs") == []
                     and item.get("summary") == ""
                     and value.get("summary") == item.get("summary"))))


def validate_news_trace(item):
    records = item.get("evidenceRecords")
    validate_evidence(records)
    allowed = {item.get("url"), *(s.get("url") for s in item.get("sources", []) if isinstance(s, dict))}
    if item.get("traceVersion") != TRACE_VERSION or any(r["url"] not in allowed for r in records):
        raise ValueError("foreign/missing news evidence")
    if safe_title(item.get("title", ""), item.get("originalTitle", ""), records) != item.get("title", ""):
        raise ValueError("unsupported title quantities/outcome")
    if records:
        if not validate_claim_refs(item.get("summary"), item.get("summaryEvidenceRefs"), records):
            raise ValueError("untraced summary")
    elif item.get("summary") not in {"", "未提取到可引用的正文，请查看原始报道。"} or item.get("summaryEvidenceRefs"):
        raise ValueError("title-only story invents source facts")
    facts = item.get("keyFactEvidence")
    if not isinstance(facts, list) or item.get("keyFacts") != [f.get("text") for f in facts]:
        raise ValueError("untraced key facts")
    if any(not validate_claim_refs(f.get("text"), f.get("evidenceIds"), records) for f in facts):
        raise ValueError("unsupported key fact")
    if "displayTranslation" in item and not valid_display_translation(item):
        raise ValueError("display translation differs from source")


def validate_deepread_trace(article):
    from deepread_editorial_signals import is_political_policy
    by_id = {event["newsId"]: event for event in article["events"]}
    for event in by_id.values():
        records = event.get("evidenceRecords")
        validate_evidence(records)
        allowed = {s.get("url") for s in event.get("sources", [])}
        if (not records or any(r["url"] not in allowed for r in records)
                or not validate_claim_refs(event.get("excerpt"), event.get("summaryEvidenceRefs"), records)
                or is_political_policy({**event, "summary": event.get("excerpt")})
                or safe_title(event.get("title"), event.get("originalTitle", ""), records) != event.get("title")):

            raise ValueError("invalid deepread event evidence")
        if "displayTranslation" in event and not valid_display_translation({
                **event, "summary": event.get("excerpt")}):
            raise ValueError("deepread display translation differs from source")
        for history in event.get("history", []):
            if is_political_policy(history):
                raise ValueError("political historical reference")
    if is_political_policy({"title": str(article.get("headline", "")) + " " + str(article.get("lead", ""))}):
        raise ValueError("political deepread framing")
    records = merge_evidence(*(event['evidenceRecords'] for event in by_id.values()))
    headlines = [event['title'] for event in by_id.values()]
    count, edition = len(by_id), article.get('editionDate')
    heading = f"每日深读｜{edition}：{count}项值得追踪的进展" if count else f"每日深读｜{edition}"
    lead = (f"本期从过去24小时的{article.get('candidateCount')}项合格候选中，选取{count}项有来源的报道，按具体进展展开。"
            if count else "本期暂无合格的最新事件。")
    if (not framing_supported(article.get('headline'), records, headlines, [heading])
            or not framing_supported(article.get('lead'), records, (), [lead])):
        raise ValueError("unsupported deepread headline/lead")
    for chapter in article["chapters"]:
        if is_political_policy({"title": str(chapter.get("title", "")) + " " + str(chapter.get("angle", ""))}):
            raise ValueError("political chapter")
        from deepread_editorial import COMPARISON_NOTE, _COMPARISON_LABELS
        members = chapter.get('newsIds', [])
        if not members or any(ref not in by_id for ref in members):
            raise ValueError("foreign chapter reference")
        records = merge_evidence(*(by_id[ref]['evidenceRecords'] for ref in members))
        titles = [by_id[ref]['title'] for ref in members]
        label = _COMPARISON_LABELS.get(chapter.get('comparisonKey'))
        amount = {2:'两', 3:'三'}.get(len(members))
        neutral_titles, neutral_angles = [], ['追踪本次报道中的具体变化']
        if chapter.get('kind') == 'comparison' and label and amount:
            neutral_titles = [f'{label}：{amount}项独立进展']
            neutral_angles = [f'分别核对{amount}项报道在{label}上披露的事实与未知事项']
        if (not framing_supported(chapter.get('title'), records, titles, neutral_titles)
                or not framing_supported(chapter.get('angle'), records, (), neutral_angles)):
            raise ValueError("unsupported chapter title/angle")
        for block in chapter["blocks"]:
            refs = block.get("newsIds", [])
            if not refs or any(ref not in by_id for ref in refs):
                raise ValueError("foreign event reference")
            records = merge_evidence(*(by_id[ref]["evidenceRecords"] for ref in refs))
            # This exact sentence describes the editorial arrangement, not a
            # factual conclusion. All other prose must pass the source gate.
            method = f"本章按{_COMPARISON_LABELS.get(chapter.get('comparisonKey'), '')}并列呈现以上原文证据。{COMPARISON_NOTE}"
            supported = (block.get("type") == "comparison" and block.get("text") == method
                         and set(block.get("evidenceIds", [])) == {r["evidenceId"] for r in records})
            if (is_political_policy({"title": block.get("text")})
                    or not (supported or validate_claim_refs(block.get("text"), block.get("evidenceIds"), records))
                    or any(not set(block.get("evidenceIds", [])) & {r["evidenceId"] for r in by_id[ref]["evidenceRecords"]} for ref in refs)):
                raise ValueError("unsupported/political deepread paragraph")
            if "displayTranslation" in block and (
                    not valid_prose_translation(block["displayTranslation"], block.get("text"), block.get("evidenceIds"))
                    or is_political_policy({"title": block["displayTranslation"].get("text")})):
                raise ValueError("deepread prose translation differs from source")
    for observation in article.get("observations", []):
        refs = observation.get("newsIds", [])
        supports = observation.get("supports", [])
        if (is_political_policy({"title": observation.get("text")})
                or not refs or len(refs) != len(set(refs)) or any(ref not in by_id for ref in refs)
                or {s.get("newsId") for s in supports} != set(refs)
                or len(supports) != len(refs)
                or not validate_observation(observation.get("text"), supports, by_id)):
            raise ValueError("unsupported/political observation")
        if "displayTranslation" in observation and (
                not valid_prose_translation(observation["displayTranslation"], observation.get("text"),
                                            [support.get("evidenceId") for support in supports])
                or is_political_policy({"title": observation["displayTranslation"].get("text")})):
            raise ValueError("deepread observation translation differs from source")
