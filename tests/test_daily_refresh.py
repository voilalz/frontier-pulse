import tempfile
import unittest
from pathlib import Path

from scripts.check_daily_refresh import decide_refresh, load_status, parse_bool


TODAY = "2026-08-05"


class DailyRefreshGateTests(unittest.TestCase):
    def test_scheduled_primary_runs_when_edition_is_missing(self):
        should_run, reason = decide_refresh(
            {"state": "ok", "editionDate": "2026-08-04", "itemCount": 10},
            today=TODAY,
            event_name="schedule",
            force_refresh=False,
        )
        self.assertTrue(should_run)
        self.assertEqual(reason, "edition_missing_or_unhealthy")

    def test_scheduled_recovery_skips_a_healthy_current_edition(self):
        should_run, reason = decide_refresh(
            {"state": "ok", "editionDate": TODAY, "itemCount": 10},
            today=TODAY,
            event_name="schedule",
            force_refresh=False,
        )
        self.assertFalse(should_run)
        self.assertEqual(reason, "healthy_edition_exists")

    def test_unhealthy_or_short_current_edition_is_rebuilt(self):
        for status in (
            {"state": "failed", "editionDate": TODAY, "itemCount": 10},
            {"state": "ok", "editionDate": TODAY, "itemCount": 9},
            {},
        ):
            with self.subTest(status=status):
                self.assertTrue(decide_refresh(
                    status,
                    today=TODAY,
                    event_name="schedule",
                    force_refresh=False,
                )[0])

    def test_manual_force_bypasses_the_guard(self):
        healthy = {"state": "ok", "editionDate": TODAY, "itemCount": 10}
        self.assertTrue(decide_refresh(
            healthy,
            today=TODAY,
            event_name="workflow_dispatch",
            force_refresh=True,
        )[0])

    def test_workflow_change_push_is_idempotent(self):
        healthy = {"state": "ok", "editionDate": TODAY, "itemCount": 10}
        self.assertFalse(decide_refresh(
            healthy,
            today=TODAY,
            event_name="push",
            force_refresh=False,
        )[0])
        self.assertTrue(decide_refresh(
            {"state": "ok", "editionDate": "2026-08-04", "itemCount": 10},
            today=TODAY,
            event_name="push",
            force_refresh=False,
        )[0])

    def test_manual_non_forced_run_is_idempotent(self):
        healthy = {"state": "ok", "editionDate": TODAY, "itemCount": 10}
        self.assertFalse(decide_refresh(
            healthy,
            today=TODAY,
            event_name="workflow_dispatch",
            force_refresh=False,
        )[0])

    def test_status_loading_and_boolean_parsing_fail_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "status.json"
            invalid.write_text("not-json", encoding="utf-8")
            self.assertEqual(load_status(invalid), {})
        for value in ("true", "1", "YES", "on", True):
            self.assertTrue(parse_bool(value))
        for value in ("false", "0", "", None, False):
            self.assertFalse(parse_bool(value))


if __name__ == "__main__":
    unittest.main()
