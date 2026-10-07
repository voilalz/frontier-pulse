"""Regression contracts for bounded collection and source-bound daily facts."""
import copy
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest import mock

import test_news_reading as reading
from test_update_news import MODULE, ROOT
from evidence_trace import make_evidence, validate_news_trace


class UpdateStabilityTests(unittest.TestCase):
    setUp = reading.NewsReadingTests.setUp
    def article(self, title, description="A satellite launch is scheduled for Monday."):
        article = reading.NewsReadingTests.article(self, title, description)
        article.source_evidence = make_evidence(description, article.url, self.now.isoformat())
        return article

    def test_deduplication_extracts_evidence_once_per_candidate(self):
        articles = [replace(self.article(f"NASA launches Project{i} payload at Facility{i}"),
                            id=f"story-{i}", url=f"https://example.org/story-{i}")
                    for i in range(24)]
        with mock.patch.object(MODULE, "capture_source_evidence", wraps=MODULE.capture_source_evidence) as capture:
            unique = MODULE.deduplicate(articles)
        self.assertEqual([a.id for a in unique], [a.id for a in articles])
        self.assertLessEqual(capture.call_count, len(articles))

    def test_stream_run_filters_time_window_before_extracting_duplicate_evidence(self):
        fixture = json.loads((ROOT / "tests/fixtures/articles.json").read_text())[3:6]
        fixture[0]["publishedAt"] = self.now.isoformat()
        fixture[1]["publishedAt"] = (self.now - timedelta(hours=25)).isoformat()
        fixture[2]["publishedAt"] = (self.now + timedelta(hours=3)).isoformat()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "fixture.json"
            source.write_text(json.dumps(fixture))
            args = ["--config", str(ROOT / "config/news_config.json"), "--fixture", str(source),
                    "--output", str(root / "news.json"), "--stream-output", str(root / "stream.json"),
                    "--stream-status-output", str(root / "stream-status.json"),
                    "--stream-only", "--skip-ai", "--now", self.now.isoformat()]
            with mock.patch.object(MODULE, "capture_source_evidence", wraps=MODULE.capture_source_evidence) as capture:
                self.assertEqual(MODULE.main(args), 0)
            self.assertEqual({call.args[0].id for call in capture.call_args_list}, {fixture[0]["id"]})
            self.assertEqual(json.loads((root / "stream.json").read_text())["itemCount"], 1)

    def test_summary_fact_comparison_ignores_case_and_terminal_punctuation(self):
        article = self.article("NASA satellite mission")
        item = MODULE.item_from_article(article, self.config, {
            "keyFacts": [article.description.rstrip(".")],
        })
        self.assertEqual(item["keyFacts"], [])
        self.assertEqual(item["keyFactEvidence"], [])
        validate_news_trace(item)

    def test_facts_are_filtered_after_restoring_translation_source_summary(self):
        sentence = "A satellite launch is scheduled for Monday."
        article = self.article("NASA satellite mission", sentence + " The satellite will monitor solar activity.")
        item = MODULE.item_from_article(article, self.config, {
            "titleZh": "美国航天局卫星任务", "summary": "卫星计划于周一发射。",
            "keyFacts": [sentence], "_sourceSummary": sentence, "_provider": "deepseek",
        })
        self.assertEqual(item["summary"], sentence)
        self.assertEqual(item["translationProvider"], "deepseek")
        self.assertEqual(item["keyFacts"], [])
        self.assertEqual(item["keyFactEvidence"], [])
        validate_news_trace(item)

    def test_recovery_filters_repeated_facts_in_same_evidence_legacy_items(self):
        article = self.article("NASA satellite mission")
        translated = MODULE.item_from_article(article, self.config, {
            "titleZh": "美国航天局卫星任务", "summary": "卫星计划于周一发射。", "_provider": "deepseek",
        })
        # Old cached items can have supported facts that repeat their summary.
        translated["keyFacts"] = [article.description.rstrip(".")]
        translated["keyFactEvidence"] = [{"text": translated["keyFacts"][0],
                                           "evidenceIds": translated["summaryEvidenceRefs"]}]
        validate_news_trace(translated)
        daily = MODULE.item_from_article(article, self.config)
        report = {"items": [daily], "translationProvider": "deepseek", "translationWarnings": [], "warnings": []}
        MODULE.recover_daily_translations(report, {"items": [translated]})
        self.assertEqual(daily["translationProvider"], "deepseek")
        self.assertEqual(daily["keyFacts"], [])
        self.assertEqual(daily["keyFactEvidence"], [])
        stream_item = MODULE.item_from_article(article, self.config)
        MODULE.merge_featured_stream_item(stream_item, copy.deepcopy(translated))
        self.assertEqual(stream_item["keyFacts"], [])
        self.assertEqual(stream_item["keyFactEvidence"], [])

    def current_translation(self):
        first = "A satellite launch is scheduled for Monday."
        article = self.article("NASA satellite mission", first + " The satellite will monitor solar activity.")
        daily = MODULE.item_from_article(article, self.config, {
            "titleZh": "美国航天局卫星任务", "summary": "卫星计划于周一发射。",
            "_sourceSummary": first, "_provider": "deepseek",
        })
        return article, daily

    def test_cache_checks_current_evidence_as_well_as_unchanged_title_body_hash(self):
        article, daily = self.current_translation()
        old = copy.deepcopy(article)
        earlier = "An earlier satellite test succeeded."
        old.source_evidence.extend(make_evidence(earlier, article.url, self.now.isoformat()))
        runtime = {"provider": "deepseek", "model": "fixture-model"}
        previous = MODULE.build_stream_report([old], self.config, self.now, translations={old.id: {
            "titleZh": "美国航天局卫星任务", "summary": "此前卫星测试已经成功。",
            "_sourceTitle": old.title, "_sourceSummary": earlier, "_provider": "deepseek",
        }}, translation_runtime=runtime)
        self.assertEqual(previous["translatedItemCount"], 1)
        cache = MODULE.reusable_stream_translations(previous, [article], runtime)
        self.assertEqual(cache, {})
        current = MODULE.build_stream_report([article], self.config, self.now, top_stories={article.id: daily},
                                             translations=cache, translation_runtime=runtime)
        self.assertEqual(current["translatedItemCount"], 1)
        MODULE.validate_stream_report(current)

    def test_featured_budget_reuses_a_shorter_supported_source_excerpt(self):
        article, daily = self.current_translation()
        self.assertEqual(MODULE.current_featured_translation_ids([article], {article.id: daily},
                          {"provider": "deepseek", "model": "fixture-model"}), {article.id})

    def test_final_stream_recovery_refreshes_global_coverage_without_rewriting_request_history(self):
        article, daily = self.current_translation()
        diagnostics = {"requestedItemCount": 0, "completedItemCount": 0, "missingItemCount": 0,
                       "missingItemIds": [], "completionReason": "not_needed", "completionMessage": "无需新增请求"}
        stream = MODULE.build_stream_report([article], self.config, self.now,
            translation_runtime={"provider": "deepseek"}, translation_diagnostics=diagnostics)
        MODULE.merge_featured_stream_item(stream["items"][0], daily)
        MODULE.refresh_stream_translation_coverage(stream)
        self.assertEqual(stream["translatedItemCount"], 1)
        self.assertEqual(stream["translationStatus"], "ok")
        self.assertEqual(stream["translationDiagnostics"]["totalTranslatedItemCount"], 1)
        self.assertEqual(stream["translationDiagnostics"]["totalMissingItemCount"], 0)
        self.assertEqual(stream["translationDiagnostics"]["requestedItemCount"], 0)
        self.assertEqual(stream["translationDiagnostics"]["completedItemCount"], 0)
        self.assertEqual(stream["translationWarnings"], [])
        MODULE.validate_stream_report(stream)


if __name__ == "__main__":
    unittest.main()
