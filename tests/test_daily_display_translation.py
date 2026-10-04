"""Chinese display survives daily construction, recovery and deepread selection."""
import json
import unittest
from unittest import mock

import test_news_reading as reading
from test_update_news import MODULE
from evidence_trace import validate_news_trace, validate_deepread_trace
from deepread_editorial import build_daily_deepread


class DailyDisplayTranslationTests(unittest.TestCase):
    setUp = reading.NewsReadingTests.setUp
    def article(self, title, description="A satellite launch is scheduled for Monday."):
        from evidence_trace import make_evidence
        article = reading.NewsReadingTests.article(self, title, description)
        article.source_evidence = make_evidence(description, article.url, self.now.isoformat())
        return article
    browser_result = reading.NewsReadingTests.browser_result

    def daily(self):
        article = self.article("NASA satellite mission")
        item = MODULE.item_from_article(article, self.config, {
            "titleZh": "美国航天局卫星任务", "summary": "卫星计划于周一发射。",
            "_provider": "deepseek"})
        return article, item

    def test_daily_chinese_survives_literal_evidence_validation_and_rendering(self):
        _, item = self.daily()
        validate_news_trace(item)
        result = self.browser_result(f'normalizeItem({json.dumps(item)}, 0)')
        self.assertEqual(result["title"], "美国航天局卫星任务")
        self.assertEqual(result["summary"], "卫星计划于周一发射。")
        self.assertEqual(item["summary"], "A satellite launch is scheduled for Monday.")

    def test_daily_provider_marker_cannot_count_an_english_response(self):
        article = self.article("NASA satellite mission")
        item = MODULE.item_from_article(article, self.config, {
            "titleZh": article.title, "summary": article.description, "_provider": "deepseek"})
        self.assertEqual(item["translationProvider"], "")
        self.assertNotIn("displayTranslation", item)

    def test_recovery_replaces_false_success_with_valid_chinese_source_binding(self):
        article = self.article("NASA satellite mission")
        daily = MODULE.item_from_article(article, self.config)
        daily["translationProvider"] = "deepseek"
        response = {"items":[{"index":1,"titleZh":"美国航天局卫星任务", "summary":"卫星计划于周一发射。", "tags":[]}]}
        with mock.patch.object(MODULE, "request_structured_json", return_value=response):
            translations = MODULE.request_stream_translation_batch([article], self.config, {"provider":"deepseek"})
        stream = MODULE.build_stream_report([article], self.config, self.now, translations=translations)
        report = {"items":[daily],"translationProvider":"deepseek","translationWarnings":[],"warnings":[]}
        MODULE.recover_daily_translations(report, stream)
        result = self.browser_result(f'normalizeItem({json.dumps(daily)},0)')
        self.assertEqual(result["summary"], "卫星计划于周一发射。")
        self.assertEqual(report["translatedItemCount"], 1)

    def test_daily_translation_rejects_english_model_response(self):
        article = self.article("NASA satellite mission")
        response = {"items":[{"index":1,"titleZh":article.title,"summary":article.description,"tags":[]}]}
        with mock.patch.object(MODULE, "request_structured_json", return_value=response):
            with self.assertRaises(MODULE.TranslationContentRejected):
                MODULE.request_daily_translation_batch([article], self.config, {"provider":"deepseek"})

    def test_daily_model_translation_is_bound_to_the_exact_sent_excerpt(self):
        article = self.article("NASA satellite mission")
        response = {"items": [{"index": 1, "titleZh": "美国航天局卫星任务",
                               "summary": "卫星计划于周一发射。", "tags": []}]}
        with mock.patch.object(MODULE, "request_structured_json", return_value=response) as request:
            translations = MODULE.request_daily_translation_batch([article], self.config, {"provider": "deepseek"})
        payload = json.loads(request.call_args.kwargs["input_text"].split("\n", 1)[1])[0]
        item = MODULE.item_from_article(article, self.config, translations[article.id])
        validate_news_trace(item)
        self.assertEqual(item["displayTranslation"]["sourceSummary"], payload["description"])
        self.assertEqual(item["translationProvider"], "deepseek")

    def test_daily_translation_rejects_new_quantities(self):
        article = self.article("NASA satellite mission")
        response = {"items": [{"index": 1, "titleZh": "美国航天局卫星任务",
                               "summary": "卫星将携带99台仪器发射。", "tags": []}]}
        with mock.patch.object(MODULE, "request_structured_json", return_value=response):
            with self.assertRaises(MODULE.TranslationContentRejected):
                MODULE.request_daily_translation_batch([article], self.config, {"provider": "deepseek"})

    def test_compact_history_search_uses_valid_chinese_display(self):
        _, item = self.daily()
        compact = MODULE.compact_search_item(item, "2026-09-20")
        self.assertEqual(compact["title"], "美国航天局卫星任务")
        self.assertEqual(compact["summary"], "卫星计划于周一发射。")
        self.assertEqual(compact["originalTitle"], "NASA satellite mission")

    def deepread(self):
        items = []
        for index, (title, zh, category) in enumerate([
            ("NASA tests Artemis capsule", "美国航天局测试阿尔忒弥斯飞船", "航空航天"),
            ("Anthropic tests Claude model", "Anthropic测试Claude模型", "AI"),
            ("Skydio tests autonomous drone", "Skydio测试自主无人机", "无人系统"),
            ("IBM tests quantum processor", "IBM测试量子处理器", "前沿技术")]):
            article = self.article(title, title + ". The team is conducting laboratory tests before the next demonstration. Results are preliminary and the programme remains at the testing stage.")
            article.id = "sample-" + str(index)
            article.url += "-" + str(index)
            from evidence_trace import make_evidence
            article.source_evidence = make_evidence(article.description, article.url, self.now.isoformat())
            article.category = category
            article.raw_score = 90
            item = MODULE.item_from_article(article, self.config, {
                "titleZh":zh,"summary":"团队正在开展实验室测试。结果仍是初步的，项目处于测试阶段。", "_provider":"deepseek"})
            items.append(item)
        return build_daily_deepread(items, self.config, self.now)

    def test_deepread_fallback_preserves_chinese_event_titles_and_paragraphs(self):
        report = self.deepread()
        self.assertEqual(report["eventCount"], 4)
        validate_deepread_trace(report)
        normalized = self.browser_result(f'normalizeEditorialDeepread({json.dumps(report)})')
        self.assertTrue(all("测试" in event["title"] for event in normalized["events"]))
        for chapter in normalized["chapters"]:
            self.assertEqual(chapter["blocks"][0]["text"], "团队正在开展实验室测试。结果仍是初步的，项目处于测试阶段。")
            self.assertIn("测试", chapter["title"])

    def test_tampered_deepread_translation_binding_is_refused(self):
        report = self.deepread()
        report["events"][0].setdefault("displayTranslation", {})["sourceSummary"] = "An unrelated source."
        with self.assertRaises(ValueError):
            validate_deepread_trace(report)
        normalized = self.browser_result(f'normalizeEditorialDeepread({json.dumps(report)})')
        self.assertEqual(normalized["events"][0]["excerpt"], report["events"][0]["excerpt"])

    def test_deepread_does_not_replace_other_authored_or_unbound_blocks(self):
        report = self.deepread()
        chapter = report["chapters"][0]
        authored = "这段独立撰写的正文应保留。"
        original_excerpt = chapter["blocks"][0]["text"]
        chapter["blocks"].append({**chapter["blocks"][0], "text": authored})
        chapter["blocks"][0]["evidenceIds"] = []
        normalized = self.browser_result(f'normalizeEditorialDeepread({json.dumps(report)})')
        self.assertEqual(normalized["chapters"][0]["blocks"][0]["text"], original_excerpt)
        self.assertEqual(normalized["chapters"][0]["blocks"][1]["text"], authored)
