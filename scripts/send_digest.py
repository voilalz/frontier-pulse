#!/usr/bin/env python3
"""Send the generated Frontier Pulse edition through an administrator SMTP account."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import getaddresses
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def parse_recipients(value: str) -> list[str]:
    normalized = re.sub(r"[;\n]+", ",", value or "")
    recipients: list[str] = []
    for _, address in getaddresses([normalized]):
        address = address.strip()
        if "@" in address and address not in recipients:
            recipients.append(address)
    return recipients


def safe_http_url(value: Any) -> str:
    try:
        parsed = urlsplit(str(value or "").strip())
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit(parsed)


def load_report(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list) or len(payload["items"]) != 10:
        raise ValueError("email digest requires a validated report containing exactly 10 items")
    return payload


def edition_url(site_url: str, edition: str) -> str:
    base = safe_http_url(site_url)
    if not base:
        return ""
    parsed = urlsplit(base)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({"view": "history", "date": edition})
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", urlencode(query), ""))


def render_text(report: dict[str, Any], site_url: str) -> str:
    brief = report.get("brief", {})
    lines = [
        f"智域前沿 · {report.get('editionDate', '')} 每日情报摘要",
        "",
        str(brief.get("headline") or "今日重点事件"),
        str(brief.get("summary") or ""),
        "",
    ]
    for index, item in enumerate(report["items"], 1):
        lines.extend([
            f"{index:02d}. [{item.get('category', '其他')}] {item.get('title', '')}",
            f"摘要：{item.get('summary', '')}",
            f"重要度：{item.get('score', 0)} · 来源置信度：{item.get('confidence', '待核验')}",
            f"来源：{item.get('source', '')} {safe_http_url(item.get('url'))}",
            "",
        ])
    link = edition_url(site_url, str(report.get("editionDate", "")))
    if link:
        lines.extend([f"浏览完整日报：{link}", ""])
    lines.append("本邮件为管理员维护的每日摘要。重要信息请打开原始来源并交叉核验。")
    return "\n".join(lines)


def render_html(report: dict[str, Any], site_url: str) -> str:
    brief = report.get("brief", {})
    edition = html.escape(str(report.get("editionDate", "")))
    cards: list[str] = []
    for index, item in enumerate(report["items"], 1):
        title = html.escape(str(item.get("title", "")))
        summary = html.escape(str(item.get("summary", "")))
        category = html.escape(str(item.get("category", "其他")))
        source = html.escape(str(item.get("source", "未知来源")))
        confidence = html.escape(str(item.get("confidence", "待核验")))
        score = max(0, min(100, int(item.get("score", 0))))
        target = safe_http_url(item.get("url"))
        source_link = f'<a href="{html.escape(target, quote=True)}" style="color:#176b62">{source} · 阅读原文</a>' if target else source
        facts = [str(fact).strip() for fact in item.get("keyFacts", []) if str(fact).strip()][:3]
        fact_html = ""
        if facts:
            fact_html = '<ul style="margin:10px 0 0;padding-left:18px;color:#59676e;font-size:13px;line-height:1.65">' + "".join(
                f"<li>{html.escape(fact)}</li>" for fact in facts
            ) + "</ul>"
        cards.append(f"""
          <tr><td style="padding:0 0 12px">
            <div style="border:1px solid #d9ddd8;border-radius:10px;background:#fffefa;padding:18px">
              <div style="font-size:11px;color:#67747b"><b style="color:#176b62">{index:02d} · {category}</b> · 重要度 {score} · 置信度 {confidence}</div>
              <h2 style="margin:8px 0 7px;font-size:19px;line-height:1.45;color:#10202a">{title}</h2>
              <p style="margin:0;color:#59676e;font-size:14px;line-height:1.7">{summary}</p>
              {fact_html}
              <p style="margin:12px 0 0;font-size:12px">{source_link}</p>
            </div>
          </td></tr>""")
    link = edition_url(site_url, str(report.get("editionDate", "")))
    call_to_action = ""
    if link:
        call_to_action = f'<a href="{html.escape(link, quote=True)}" style="display:inline-block;padding:11px 16px;border-radius:7px;background:#cce36d;color:#10202a;text-decoration:none;font-weight:700">浏览完整日报</a>'
    return f"""<!doctype html>
<html lang="zh-CN"><body style="margin:0;background:#f4f3ee;font-family:Arial,'Microsoft YaHei',sans-serif;color:#10202a">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f3ee"><tr><td align="center" style="padding:28px 12px">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:680px">
      <tr><td style="padding:25px;border-radius:12px 12px 0 0;background:#102c3a;color:white">
        <div style="font-size:11px;letter-spacing:2px;color:#cce36d">FRONTIER PULSE · {edition}</div>
        <h1 style="margin:12px 0 8px;font-size:28px;line-height:1.3">{html.escape(str(brief.get('headline') or '智域前沿每日摘要'))}</h1>
        <p style="margin:0;color:#bdc9cc;font-size:14px;line-height:1.7">{html.escape(str(brief.get('summary') or ''))}</p>
      </td></tr>
      <tr><td style="padding:14px 0"><table role="presentation" width="100%" cellspacing="0" cellpadding="0">{''.join(cards)}</table></td></tr>
      <tr><td style="padding:4px 4px 22px;text-align:center">{call_to_action}</td></tr>
      <tr><td style="padding:18px;border-top:1px solid #d9ddd8;color:#67747b;font-size:11px;line-height:1.65;text-align:center">
        本邮件由管理员配置的日报流程发送。重要信息请打开原始来源并交叉核验；收件人不会显示在公开网页中。
      </td></tr>
    </table>
  </td></tr></table>
</body></html>"""


def build_message(report: dict[str, Any], sender: str, site_url: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = f"智域前沿｜{report.get('editionDate', '')} 全球科技与安全 Top 10"
    message["From"] = sender
    message["To"] = "undisclosed-recipients:;"
    reply_to = os.getenv("EMAIL_REPLY_TO", "").strip()
    if reply_to:
        message["Reply-To"] = reply_to
    message.set_content(render_text(report, site_url))
    message.add_alternative(render_html(report, site_url), subtype="html")
    return message


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send the generated Frontier Pulse email digest")
    parser.add_argument("--input", type=Path, default=Path("public/data/news.json"))
    parser.add_argument("--dry-run", action="store_true", help="Render and validate without contacting SMTP")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    host = os.getenv("SMTP_HOST", "").strip()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("EMAIL_FROM", "").strip()
    recipients = parse_recipients(os.getenv("EMAIL_TO", ""))
    site_url = os.getenv("SITE_URL", "").strip() or "https://frontier-pulse.jiumi674.workers.dev"
    missing = [name for name, value in (("SMTP_HOST", host), ("EMAIL_FROM", sender), ("EMAIL_TO", recipients)) if not value]
    if missing and not args.dry_run:
        print(f"Email push not configured; skipping (missing {', '.join(missing)})")
        return 0
    report = load_report(args.input)
    message = build_message(report, sender or "frontier-pulse@example.invalid", site_url)
    if args.dry_run:
        print(f"Validated email digest for edition {report.get('editionDate')} with {len(report['items'])} stories")
        return 0
    port = int(os.getenv("SMTP_PORT", "").strip() or "587")
    use_ssl = env_bool("SMTP_USE_SSL", port == 465)
    context = ssl.create_default_context()
    connection = smtplib.SMTP_SSL(host, port, timeout=30, context=context) if use_ssl else smtplib.SMTP(host, port, timeout=30)
    with connection as client:
        if not use_ssl and env_bool("SMTP_STARTTLS", True):
            client.starttls(context=context)
        if username:
            client.login(username, password)
        client.send_message(message, from_addr=sender, to_addrs=recipients)
    print(f"Sent edition {report.get('editionDate')} to {len(recipients)} recipient(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
