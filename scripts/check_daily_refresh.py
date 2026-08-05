#!/usr/bin/env python3
"""Decide whether a scheduled daily edition should run.

Scheduled primary/recovery events and workflow-definition pushes are
idempotent: a healthy 10-item edition for the current publication date is
retained. Only a manual forced run intentionally bypasses that guard.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


TRUE_VALUES = {"1", "true", "yes", "on"}


def parse_bool(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in TRUE_VALUES


def load_status(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def decide_refresh(
    status: dict[str, Any],
    *,
    today: str,
    event_name: str,
    force_refresh: bool,
) -> tuple[bool, str]:
    event = str(event_name or "").strip()
    if event == "workflow_dispatch" and force_refresh:
        return True, "manual_force_refresh"

    healthy_today = (
        status.get("state") == "ok"
        and status.get("editionDate") == today
        and status.get("itemCount") == 10
    )
    if healthy_today:
        return False, "healthy_edition_exists"
    return True, "edition_missing_or_unhealthy"


def append_github_output(path: Path, values: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--timezone", default="Asia/Shanghai")
    parser.add_argument("--event-name", default="schedule")
    parser.add_argument("--force", default="false")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()

    today = datetime.now(ZoneInfo(args.timezone)).date().isoformat()
    should_run, reason = decide_refresh(
        load_status(args.status),
        today=today,
        event_name=args.event_name,
        force_refresh=parse_bool(args.force),
    )
    values = {
        "should_run": "true" if should_run else "false",
        "reason": reason,
        "edition_date": today,
    }
    if args.github_output:
        append_github_output(args.github_output, values)
    print(json.dumps(values, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
