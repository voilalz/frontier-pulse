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
        self.assertTrue(all(item["originalTitle"] and item["keyFacts"] for item in report["items"]))
        self.assertTrue(all(item["scoreReasons"] and item["confidenceReason"] for item in report["items"]))
        self.assertTrue(all(item["sources"] for item in report["items"]))

    def test_deduplicate_merges_tracking_urls(self):
        first = self.articles[0]
        duplicate = MODULE.Article(**{**MODULE.asdict(first), "id": "duplicate", "url": first.url + "?utm_source=test"})
        result = MODULE.deduplicate([first, duplicate])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].corroboration, 1)
        self.assertEqual(len(result[0].evidence_sources), 1)

    def test_deduplicate_preserves_independent_sources(self):
        first = self.articles[0]
        second = MODULE.Article(**{
            **MODULE.asdict(first),
            "id": "second-source",
            "source": "Reuters",
            "domain": "reuters.com",
            "url": "https://www.reuters.com/example/same-ai-release",
        })
        second.evidence_sources = []
        result = MODULE.deduplicate([first, second])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].corroboration, 2)
        self.assertEqual({item["domain"] for item in result[0].evidence_sources}, {
            "technologyreview.com", "reuters.com",
        })
        self.assertEqual(MODULE.source_weight(result[0], self.config), 20)

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
            root = Path(directory)
            output = root / "news.json"
            archive = root / "archive"
            archive_index = archive / "index.json"
            search_index = archive / "search-index.json"
            status_output = root / "status.json"
            status = MODULE.main([
                "--config", str(ROOT / "config" / "news_config.json"),
                "--fixture", str(ROOT / "tests" / "fixtures" / "articles.json"),
                "--output", str(output),
                "--archive-dir", str(archive),
                "--archive-index", str(archive_index),
                "--search-index", str(search_index),
                "--status-output", str(status_output),
                "--skip-ai",
                "--now", "2026-07-16T00:00:00Z",
            ])
            self.assertEqual(status, 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["editionDate"], "2026-07-16")
            self.assertEqual(payload["timezone"], "Asia/Tokyo")
            self.assertEqual(payload["method"], "rules")
            self.assertEqual(len(payload["items"]), 10)
            self.assertTrue((archive / "2026-07-16.json").exists())
            self.assertEqual(json.loads(archive_index.read_text(encoding="utf-8"))["editions"][0]["editionDate"], "2026-07-16")
            search_payload = json.loads(search_index.read_text(encoding="utf-8"))
            self.assertEqual(len(search_payload["items"]), 10)
            self.assertTrue(all(item.get("scoreComponents") for item in search_payload["items"]))
            self.assertEqual(json.loads(status_output.read_text(encoding="utf-8"))["state"], "ok")

    def test_failure_writes_status_without_overwriting_latest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "news.json"
            output.write_text('{"sentinel": true}\n', encoding="utf-8")
            too_small = root / "small.json"
            too_small.write_text(json.dumps([MODULE.asdict(item) for item in self.articles[:2]], default=str), encoding="utf-8")
            status_output = root / "status.json"
            result = MODULE.main([
                "--config", str(ROOT / "config" / "news_config.json"),
                "--fixture", str(too_small),
                "--output", str(output),
                "--archive-dir", str(root / "archive"),
                "--archive-index", str(root / "archive" / "index.json"),
                "--search-index", str(root / "archive" / "search-index.json"),
                "--status-output", str(status_output),
                "--skip-ai",
                "--now", "2026-07-16T00:00:00Z",
            ])
            self.assertEqual(result, 2)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), {"sentinel": True})
            status = json.loads(status_output.read_text(encoding="utf-8"))
            self.assertEqual(status["state"], "failed")
            self.assertIn("低于安全阈值", status["message"])

    def test_sponsored_content_is_excluded(self):
        sponsored = MODULE.Article(**{
            **MODULE.asdict(self.articles[0]),
            "id": "sponsored",
            "title": "[Sponsored] New AI model launch",
        })
        scored = MODULE.score_articles(MODULE.deduplicate([sponsored]), self.config, self.now)
        self.assertEqual(scored, [])

    def test_edition_uses_tokyo_calendar_date(self):
        now = datetime(2026, 7, 16, 23, 30, tzinfo=timezone.utc)
        candidates = MODULE.score_articles(MODULE.deduplicate(self.articles), self.config, self.now)
        report = MODULE.build_report(candidates, self.config, now, skip_ai=True)
        self.assertEqual(report["editionDate"], "2026-07-17")
        self.assertEqual(report["timezone"], "Asia/Tokyo")


if __name__ == "__main__":
    unittest.main()
