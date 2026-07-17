import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("update_news", ROOT / "scripts" / "update_news.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class UpdateNewsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 16, 0, 0, tzinfo=timezone.utc)
        self.config = MODULE.load_config(ROOT / "config" / "news_config.json")
        self.articles = MODULE.collect_fixture(ROOT / "tests" / "fixtures" / "articles.json", self.now)

    def test_fixture_builds_valid_diverse_report(self):
        previous = os.environ.pop("OPENAI_API_KEY", None)
        try:
            candidates = MODULE.score_articles(MODULE.deduplicate(self.articles), self.config, self.now)
            report = MODULE.build_report(candidates, self.config, self.now, skip_ai=True)
            MODULE.validate_report(report, 10)
        finally:
            if previous is not None:
                os.environ["OPENAI_API_KEY"] = previous
        self.assertEqual(len(report["items"]), 10)
        self.assertEqual(len({item["id"] for item in report["items"]}), 10)
        self.assertGreaterEqual(len({item["category"] for item in report["items"]}), 4)
        self.assertTrue(all(item["summary"] and item["why"] for item in report["items"]))

    def test_deduplicate_merges_tracking_urls(self):
        first = self.articles[0]
        duplicate = MODULE.Article(**{**MODULE.asdict(first), "id": "duplicate", "url": first.url + "?utm_source=test"})
        result = MODULE.deduplicate([first, duplicate])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].corroboration, 2)

    def test_ascii_keywords_require_token_boundaries(self):
        self.assertFalse(MODULE.keyword_matches("newest artemis accords signatory", "nato"))
        self.assertTrue(MODULE.keyword_matches("nato tests a distributed network", "nato"))

    def test_cross_source_event_titles_are_deduplicated(self):
        first = "Blue Water Autonomy, Saildrone launch lawsuits against Navy over MUSV Marketplace"
        second = "2 defense tech companies sue US Navy after losing out on MUSV program"
        self.assertTrue(MODULE.same_event_title(first, second))
        self.assertFalse(MODULE.same_event_title(first, "Navy plans long-range carrier drone fleets"))

    def test_cli_writes_atomic_json(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "news.json"
            status = MODULE.main([
                "--config", str(ROOT / "config" / "news_config.json"),
                "--fixture", str(ROOT / "tests" / "fixtures" / "articles.json"),
                "--output", str(output),
                "--skip-ai",
                "--now", "2026-07-16T00:00:00Z",
            ])
            self.assertEqual(status, 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["editionDate"], "2026-07-16")
            self.assertEqual(payload["timezone"], "Asia/Tokyo")
            self.assertEqual(payload["method"], "rules")
            self.assertEqual(len(payload["items"]), 10)

    def test_edition_uses_tokyo_calendar_date(self):
        now = datetime(2026, 7, 16, 23, 30, tzinfo=timezone.utc)
        candidates = MODULE.score_articles(MODULE.deduplicate(self.articles), self.config, self.now)
        report = MODULE.build_report(candidates, self.config, now, skip_ai=True)
        self.assertEqual(report["editionDate"], "2026-07-17")
        self.assertEqual(report["timezone"], "Asia/Tokyo")


if __name__ == "__main__":
    unittest.main()
