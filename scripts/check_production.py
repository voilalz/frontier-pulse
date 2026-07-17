#!/usr/bin/env python3
"""Verify that the deployed static host applies security and cache headers."""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.parse
import urllib.request
from email.message import Message


def fetch_headers(url: str, timeout: int = 20) -> tuple[int, Message]:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "FrontierPulseSmoke/1.4"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.headers


def cache_header_is_unambiguous(headers: Message, expected_max_age: int) -> bool:
    values = headers.get_all("Cache-Control", [])
    combined = ", ".join(values).lower()
    return (
        len(values) == 1
        and combined.count("max-age=") == 1
        and f"max-age={expected_max_age}" in combined
    )


def check(site_url: str) -> list[str]:
    base = site_url.rstrip("/") + "/"
    targets = [
        ("首页", base, None),
        ("最新日报", urllib.parse.urljoin(base, "data/news.json"), 300),
        ("流水线状态", urllib.parse.urljoin(base, "data/status.json"), 60),
        ("搜索清单", urllib.parse.urljoin(base, "data/archive/search-index.json"), 300),
        ("Atom 订阅", urllib.parse.urljoin(base, "feed.xml"), 300),
    ]
    failures: list[str] = []
    for label, url, expected_max_age in targets:
        try:
            status, headers = fetch_headers(url)
        except (urllib.error.URLError, TimeoutError) as exc:
            failures.append(f"{label} 无法访问：{exc}")
            continue
        if status != 200:
            failures.append(f"{label} 返回 HTTP {status}")
            continue
        if headers.get("X-Content-Type-Options", "").lower() != "nosniff":
            failures.append(f"{label} 缺少 X-Content-Type-Options: nosniff")
        if "default-src 'self'" not in headers.get("Content-Security-Policy", ""):
            failures.append(f"{label} 缺少预期 CSP")
        if label == "首页" and "worker-src 'self'" not in headers.get("Content-Security-Policy", ""):
            failures.append("首页 CSP 缺少 worker-src 'self'，离线 Service Worker 可能无法注册")
        if expected_max_age is not None and not cache_header_is_unambiguous(headers, expected_max_age):
            failures.append(
                f"{label} Cache-Control 不唯一或并非 max-age={expected_max_age}："
                f"{headers.get_all('Cache-Control', [])}"
            )
        if expected_max_age is not None and not headers.get("ETag"):
            failures.append(f"{label} 缺少 ETag，无法进行轻量再验证")
        print(f"OK {label}: HTTP {status}; cache={headers.get_all('Cache-Control', [])}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test Frontier Pulse production headers")
    parser.add_argument("--site-url", required=True)
    args = parser.parse_args(argv)
    failures = check(args.site_url)
    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    print("Production security and cache headers are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
