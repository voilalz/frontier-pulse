"""Run the real stream pipeline against a deterministic provider boundary."""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_news_reading as reading
from test_update_news import MODULE, ROOT


class StreamTranslationCoverageTests(unittest.TestCase):
    setUp = reading.NewsReadingTests.setUp

    def prepare_run(self, root, count, config=None):
        fixture = [{"id": f"craft-{i}", "title": f"NASA tests satellite Craft{i} from Facility{i}",
                    "description": f"NASA tests satellite Craft{i} from Facility{i}. NASA plans to collect measurements from the satellite during the test.",
                    "source": "NASA", "publishedAt": self.now.isoformat(),
                    "url": f"https://www.nasa.gov/craft-{i}"} for i in range(count)]
        (root / "fixture.json").write_text(json.dumps(fixture))
        (root / "config.json").write_text(json.dumps(config or self.config))
        return ["--config", str(root / "config.json"), "--fixture", str(root / "fixture.json"),
                "--output", str(root / "news.json"), "--stream-output", str(root / "stream.json"),
                "--stream-status-output", str(root / "stream-status.json"), "--stream-only", "--now", self.now.isoformat()]

    def provider(self, requested):
        def request(runtime, **kwargs):
            rows = json.loads(kwargs["input_text"].split("\n", 1)[1])
            requested.extend(row["title"] for row in rows)
            return {"items": [{"index": row["index"],
                               "titleZh": "美国航天局测试Craft" + re.search(r"Craft(\d+)", row["title"])[1] + "卫星",
                               "summary": "美国航天局测试卫星，计划在试验中收集观测数据。", "tags": ["卫星"]}
                              for row in rows]}
        return request

    def test_default_run_translates_all_visible_items_including_rank_121_and_later(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.prepare_run(root, 135)
            requested = []
            with mock.patch.object(MODULE, "resolve_ai_runtime", return_value={"provider": "deepseek", "model": "fixture-model"}), \
                 mock.patch.object(MODULE, "request_structured_json", side_effect=self.provider(requested)):
                self.assertEqual(MODULE.main(args), 0)
            report = json.loads((root / "stream.json").read_text())
            self.assertEqual(report["itemCount"], 135)
            self.assertEqual(len(requested), 135)
            self.assertTrue(any("Craft134 " in title for title in requested))
            self.assertEqual(report["translatedItemCount"], 135)
            self.assertEqual(report["translationStatus"], "ok")
            self.assertEqual(report["translationDiagnostics"]["totalMissingItemCount"], 0)
            status = json.loads((root / "stream-status.json").read_text())
            self.assertEqual(status["translationStatus"], "ok")
            self.assertFalse((root / "news.json").exists())

    def test_per_run_budget_counts_new_requests_after_cache_and_reports_not_attempted_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.prepare_run(root, 9, {**self.config, "stream_translation_limit": 3})
            requested = []
            with mock.patch.object(MODULE, "resolve_ai_runtime", return_value={"provider": "deepseek", "model": "fixture-model"}), \
                 mock.patch.object(MODULE, "request_structured_json", side_effect=self.provider(requested)):
                self.assertEqual(MODULE.main(args), 0)
                self.assertEqual(MODULE.main(args), 0)
            report = json.loads((root / "stream.json").read_text())
            self.assertEqual(len(requested), 6)
            self.assertEqual(report["translatedItemCount"], 6)
            self.assertEqual(report["translationStatus"], "partial")
            diagnostics = report["translationDiagnostics"]
            self.assertEqual(diagnostics["requestedItemCount"], 3)
            self.assertEqual(diagnostics["completedItemCount"], 3)
            self.assertEqual(diagnostics["totalMissingItemCount"], 3)
            self.assertEqual(diagnostics["notAttemptedItemCount"], 3)
            self.assertEqual(len(diagnostics["notAttemptedItemIds"]), 3)
            self.assertEqual(json.loads((root / "stream-status.json").read_text())["translationStatus"], "partial")


if __name__ == "__main__":
    unittest.main()
