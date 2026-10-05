"""Shared reader-facing rules; source evidence stays in its original language."""
from __future__ import annotations

import re

CONTENT_RULES_REVISION = 1
_FILLER = re.compile(r"现有元数据|元数据未(?:提供|说明)|未提取到可引用的正文|"
                     r"未提供更多(?:摘要|信息|细节)|这条新闻来自|"
                     r"现有(?:信息|报道)(?:仅包含|未提供)|目前披露的信息仅涉及|"
                     r"文章.{0,180}(?:最初发表于|最先发表于)")


def metadata_filler(value) -> bool:
    return isinstance(value, str) and bool(_FILLER.search(value))


def chinese_reader_text(value) -> bool:
    return (isinstance(value, str) and bool(value.strip())
            and bool(re.search(r"[\u3400-\u9fff]", value)) and not metadata_filler(value)
            and not re.search(r"\b[a-z]{2,}(?:\s+[a-z]{2,}){2,}\b",
                              re.sub(r"\([^)]*\)|（[^）]*）", "", value)))


def content_availability(records, status="") -> str:
    if not records or status == "title-only":
        return "title-only"
    text = " ".join(r.get("text", "") for r in records)
    body = status == "body" or any(r.get("kind") == "body" for r in records)
    # Full-content RSS may supply a body. A short feed lead cannot establish
    # one, even if an earlier stage mislabeled its availability.
    chinese = len(re.findall(r"[\u3400-\u9fff]", text))
    enough = chinese >= (12 if body else 100) or len(text) >= (40 if body else 280)
    return "body" if enough and len(records) >= (1 if body else 3) else "lead-only"


def assess_admissibility(item) -> dict:
    """A conservative genre/body gate applied before featured selection."""
    title = str(item.get("originalTitle") or item.get("title") or "")
    url = str(item.get("url") or "").lower()
    text = "\n".join(r.get("text", "") for r in item.get("evidenceRecords", []))
    if text.rstrip('.。').strip() == title.rstrip('.。').strip():
        return {"eligible":False,"reason":"title-only"}
    if title and len(re.findall(re.escape(title),text,re.I)) >= 2 and re.search(r'\b(?:accessed|retrieved)\b',text,re.I):
        # A repeated headline plus a bibliographic citation is not article text.
        remainder=re.sub(re.escape(title),'',text,flags=re.I)
        remainder=re.sub(r'(?:https?://|www\.)\S+|\bScienceDaily\b|\([^)]*(?:accessed|retrieved)[^)]*\)','',remainder,flags=re.I)
        if len(re.findall(r'\w',remainder)) < 40:
            return {"eligible":False,"reason":"source-boilerplate"}
    rules = [
        ("live-container", r"(?:[–—:]\s*(?:\w+\s+)?live$|^live\s*:|\blive (?:updates|blog|coverage)\b|直播|实时滚动)", r"/(?:live|liveblog)/"),
        ("roundup", r"\b(?:weekly roundup|weekly digest|week in|news roundup|this week)\b|周报|本周综述", r"/(?:roundup|weekly-digest)/"),
        ("qa", r"\bq\s*&\s*a\b|^ask\b|问答|专家答疑", r"/(?:q-and-a|questions-answers)/"),
        ("historical-column", r"\bon this day\b|\bfrom the archives\b|历史上的今天|历史回顾", r"/(?:on-this-day|today-in-the-history-of-astronomy)/"),
        ("marketing", r"\b(?:sponsored|advertorial|buy now|limited.time offer)\b|付费推广|限时优惠|立即购买", r"/(?:sponsored|advertorial)/"),
    ]
    for reason, heading, path in rules:
        if re.search(heading, title, re.I) or re.search(path, url):
            return {"eligible":False,"reason":reason}
    if ((title.rstrip().endswith(('?','？')) and re.search(r'\b(?:tell|tells|told)\s+(?:the\s+)?host\b',text,re.I))
            or len(re.findall(r'(?:^|\s)Q\s*:',text,re.I)) >= 2):
        return {"eligible":False,"reason":"qa"}
    # Time-stamped repeated headings distinguish a live container from a
    # technical release containing the ordinary word "live".
    if len(re.findall(r"(?:^|\s)\d{1,2}:\d{2}\s*(?:GMT|UTC|BST|ET|AM|PM)", text, re.I)) >= 3:
        return {"eligible":False,"reason":"live-container"}
    if item.get("articleType") in {"sponsored", "advertorial", "marketing"}:
        return {"eligible":False,"reason":"marketing"}
    availability = content_availability(item.get("evidenceRecords", []), item.get("summaryEvidence", {}).get("status", ""))
    return {"eligible":availability == "body","reason":"qualified-body" if availability == "body" else availability}

