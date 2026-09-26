#!/usr/bin/env python3
"""Decide whether a scheduled daily edition should run.

Scheduled primary/recovery events and workflow-definition pushes are
idempotent: a healthy 10-item edition for the current publication date and
current data and summary contracts is retained. Manual force or a contract
upgrade bypasses that guard.
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
    required_schema: int = 0,
    required_summary_revision: int = 0,
    require_history_analysis: bool = False,
    deepread: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    event = str(event_name or "").strip()
    if event == "workflow_dispatch" and force_refresh:
        return True, "manual_force_refresh"

    healthy_today = (
        status.get("state") == "ok"
        and status.get("editionDate") == today
        and status.get("itemCount") == 10
        and status.get("translationStatus") not in {"partial", "failed"}
    )
    try:
        current_schema = int(status.get("schemaVersion", 0) or 0)
    except (TypeError, ValueError):
        current_schema = 0
    if healthy_today and required_schema > 0 and current_schema < required_schema:
        return True, "schema_upgrade_required"
    try:
        summary_revision = int(status.get("summaryRevision", 0) or 0)
    except (TypeError, ValueError):
        summary_revision = 0
    if healthy_today and required_summary_revision > 0 and summary_revision < required_summary_revision:
        return True, "summary_upgrade_required"
    if healthy_today and require_history_analysis and status.get("historyAnalysisStatus") in {None, "", "disabled"}:
        return True, "history_analysis_required"
    if healthy_today and deepread is not None and (
        deepread.get("editionDate") != today or deepread.get("generationStatus") != "ok"
    ):
        return True, "deepread_missing_or_incomplete"
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
    parser.add_argument("--deepread", type=Path)
    parser.add_argument("--timezone", default="Asia/Shanghai")
    parser.add_argument("--event-name", default="schedule")
    parser.add_argument("--force", default="false")
    parser.add_argument("--required-schema", type=int, default=0)
    parser.add_argument("--required-summary-revision", type=int, default=0)
    parser.add_argument("--require-history-analysis", action="store_true")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()

    today = datetime.now(ZoneInfo(args.timezone)).date().isoformat()
    should_run, reason = decide_refresh(
        load_status(args.status),
        today=today,
        event_name=args.event_name,
        force_refresh=parse_bool(args.force),
        required_schema=max(0, args.required_schema),
        required_summary_revision=max(0, args.required_summary_revision),
        require_history_analysis=args.require_history_analysis,
        deepread=load_status(args.deepread) if args.deepread else None,
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
