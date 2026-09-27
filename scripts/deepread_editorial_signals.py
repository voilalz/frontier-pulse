"""Source-grounded eligibility and editorial signals for daily deep reads."""

from __future__ import annotations

import re
from typing import Any

from news_evidence import strip_caption_text


_POLITICAL_CATEGORIES = {"政治", "政策", "政治政策", "政局", "国内政治", "国际政治",
                         "局部冲突", "地缘政治", "军事冲突"}
_POLITICAL_SUBJECT = re.compile(
    r"\b(?:election|campaign|political party|diplomatic summit|foreign policy|"
    r"trade policy|immigration policy|tariff|sanctions?|regulation|legislation|"
    r"(?:senate|parliament|congress|regulator|government).{0,80}(?:bills?|laws?|legislation)|"
    r"(?:AI|artificial intelligence|safety).{0,30}(?:bill|law)|"
    r"executive order|media access|press access|export controls?|"
    r"polic(?:y|ies)(?![-\s]+(?:gradient|optimization|iteration|network|learning)))\b|"
    r"选举|竞选|政党|外交会谈|外交政策|监管政策|监管规定|政策法案|"
    r"立法|法案|政策(?!梯度)|出口管制|监管.{0,10}(?:法律|法规|条例|新规)|行政令|关税|制裁|媒体准入|记者准入|随行采访", re.I)
_POLITICAL_LEAD = re.compile(
    r"(?:政府|监管机构|国会|议会|白宫|欧盟|美国).{0,55}"
    r"(?:政策|法案|法规|条例|出口管制|禁令)|"
    r"(?:参议院|众议院|国会|议会|监管机构).{0,75}(?:调查|听证|传唤|质询)|"
    r"\b(?:government|regulator|parliament|congress|white house)\b.{0,75}"
    r"\b(?:policy|policies|bill|law|regulation|export controls?)\b|"
    r"\b(?:senate|parliament|congress|regulator)\b.{0,75}"
    r"\b(?:hearings?|inquir(?:y|ies)|summons?|investigation)\b", re.I)
_PRESS_ACCESS = re.compile(
    r"(?:white house|白宫).{0,55}(?:cnn|press|reporters?|journalists?|媒体|记者)|"
    r"(?:cnn|press|reporters?|journalists?|媒体|记者).{0,55}(?:white house|白宫)", re.I)


def is_political_policy(item: dict[str, Any]) -> bool:
    """Exclude politics and policy as the story's subject, not incidental officials."""
    if not isinstance(item, dict):
        return False
    if str(item.get("category", "")).strip() in _POLITICAL_CATEGORIES:
        return True
    title = " ".join(str(item.get(key) or "") for key in ("originalTitle", "title"))
    lead = re.split(r"[。！？!?]|(?<=\.)\s+", str(item.get("summary") or ""), maxsplit=1)[0][:240]
    return bool(_POLITICAL_SUBJECT.search(title) or _PRESS_ACCESS.search(title)
                or _POLITICAL_LEAD.search(lead))


# Specific shared subjects permit a comparison without claiming the reports
# concern the same event. Broad labels such as "technology" are deliberately absent.
_COMPARISON_SUBJECTS = {
    "ai-agent": re.compile(r"\b(?:AI[ -]?agents?|agentic[ -]?AI)\b|(?:AI|人工智能)[ -]?(?:智能体|代理)|智能体", re.I),
    "counter-uas": re.compile(r"\b(?:counter[ -]?(?:UAS|drone)|anti[ -]?drone)\b|反无人机", re.I),
    "quantum-computing": re.compile(r"\bquantum comput(?:ing|ers?)\b|量子计算", re.I),
    "hypersonic-missile": re.compile(r"\bhypersonic missiles?\b|高超音速导弹", re.I),
    "semiconductor-fabrication": re.compile(r"\b(?:semiconductor fabrication|chip fabrication)\b|芯片制造|半导体制造", re.I),
    "robotaxi": re.compile(r"\brobotaxis?\b|(?:自动驾驶|无人驾驶|机器人)(?:出租车|网约车)", re.I),
    "fusion": re.compile(r"\bfusion\b|核聚变", re.I),
    "perovskite": re.compile(r"\bperovskite\b|钙钛矿", re.I),
}


def comparison_keys(item: dict[str, Any]) -> set[str]:
    """Return narrowly defined subject keys shared across independent reports."""
    material = " ".join(str(item.get(key) or "") for key in ("title", "originalTitle", "summary"))
    return {key for key, pattern in _COMPARISON_SUBJECTS.items() if pattern.search(material)}


_ACTION_STAGES = (
    ("halt", re.compile(r"取消|暂停|中止|推迟|延期|\b(?:cancels?|cancelled|halts?|pauses?|suspends?|delays?)\b", re.I)),
    ("plan", re.compile(r"计划|筹备|准备|拟进行|拟开展|\b(?:plans?|planning|prepares?|scheduled|proposes?)\b", re.I)),
    ("done", re.compile(r"完成|交付|投入使用|部署完成|正式发射|\b(?:completed?|delivered?|deployed|launched)\b", re.I)),
    ("trial", re.compile(r"试验|测试|试飞|演示|\b(?:tests?|trials?|demonstrates?)\b", re.I)),
)


def _stage(title: str) -> str:
    if _ACTION_STAGES[0][1].search(title):
        return "halt"
    if re.search(r"将于|拟于|预计|明日|下周|未来|即将|计划于|\b(?:tomorrow|next week|will|scheduled to|to launch)\b", title, re.I):
        return "plan"
    if (re.search(r"(?:按计划|如期)(?:已)?(?:完成|交付|发射)", title)
            or re.search(r"\b(?:completed|delivered|launched)\b.{0,16}\b(?:as planned|on schedule)\b|"
                         r"\b(?:as planned|on schedule)\b.{0,16}\b(?:completed|delivered|launched)\b", title, re.I)):
        return "done"
    return next((name for name, pattern in _ACTION_STAGES if pattern.search(title)), "")


def delta_score(current: dict[str, Any], history: list[dict[str, Any]]) -> int:
    """Credit a verified same-event action transition, never a reworded headline."""
    if not history:
        return 0
    latest = history[-1]
    previous = _stage(str(latest.get("title") or ""))
    present = _stage(str(current.get("title") or "")) or _stage(str(current.get("originalTitle") or ""))
    if not previous or not present or previous == present:
        return 0
    return 3 if present == "halt" and previous != "halt" else 2


def editorial_priority(item: dict[str, Any]) -> tuple:
    """Keep news importance decisive; use delta and source quality in close calls."""
    evidence_bonus = {"primary": 3, "multi": 2, "single": 0, "opinion": -1}.get(
        item.get("_evidenceLevel"), 0)
    importance = item["_score"]
    utility = importance + 2 * item.get("_deltaScore", 0) + evidence_bonus
    return (-utility, -importance, -item["_quality"], -item["_sourceWeight"],
            -item["_published"].timestamp(), item["eventId"], item["id"])
