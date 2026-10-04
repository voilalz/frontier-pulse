"""Chinese display translations retain an independently traceable source."""
import json
import unittest
from unittest import mock

import test_news_reading as reading
from test_update_news import MODULE


class StreamDisplayTranslationTests(unittest.TestCase):
    setUp = reading.NewsReadingTests.setUp
    article = reading.NewsReadingTests.article
    browser_result = reading.NewsReadingTests.browser_result
    # Reuse the real browser normalizer harness, without inheriting its cases.
    def translation(self, article):
        result = {"items": [{"index": 1, "titleZh": "美国航天局卫星任务",
                             "summary": "卫星计划于周一发射。", "tags": ["卫星"]}]}
        runtime = {"provider": "deepseek", "model": "test-model"}
        with mock.patch.object(MODULE, "request_structured_json", return_value=result):
            return MODULE.request_stream_translation_batch([article], self.config, runtime)

    def stream(self):
        article = self.article("NASA satellite mission")
        from evidence_trace import make_evidence
        article.source_evidence = make_evidence(article.description, article.url, self.now.isoformat())
        return article, MODULE.build_stream_report([article], self.config, self.now,
            translations=self.translation(article),
            translation_runtime={"provider": "deepseek", "model": "test-model"})

    def test_chinese_is_visible_without_replacing_literal_source_evidence(self):
        _, stream = self.stream()
        item = stream["items"][0]
        from evidence_trace import validate_news_trace
        validate_news_trace(item)
        rendered = self.browser_result(f'renderStory(normalizeItem({json.dumps(item)}, 0), 0, false)')
        self.assertIn("美国航天局卫星任务", rendered)
        self.assertIn("卫星计划于周一发射。", rendered)
        self.assertEqual(item["originalTitle"], "NASA satellite mission")
        self.assertEqual(stream["translatedItemCount"], 1)

    def test_old_english_provider_marker_is_not_reused_or_counted(self):
        article = self.article("NASA satellite mission")
        item = MODULE.item_from_article(article, self.config)
        item["translationProvider"] = "deepseek"
        previous = {"items": [item], "translationProvider": "deepseek", "translationModel": "test-model"}
        runtime = {"provider": "deepseek", "model": "test-model"}
        self.assertEqual(MODULE.reusable_stream_translations(previous, [article], runtime), {})
        self.assertEqual(MODULE.current_featured_translation_ids([article], {article.id:item}, runtime), set())
        stream = MODULE.build_stream_report([article], self.config, self.now, top_stories={article.id:item})
        self.assertEqual(stream["translatedItemCount"], 0)

    def test_changed_source_rejects_display_and_its_cache(self):
        article, stream = self.stream()
        item = stream["items"][0]
        self.assertIn("displayTranslation", item)
        item["displayTranslation"]["sourceSummary"] = "A different story."
        rendered = self.browser_result(f'renderStory(normalizeItem({json.dumps(item)}, 0), 0, false)')
        self.assertNotIn("卫星计划于周一发射。", rendered)
        self.assertEqual(MODULE.reusable_stream_translations(stream, [article],
            {"provider":"deepseek", "model":"test-model"}), {})
        with self.assertRaises(ValueError):
            MODULE.validate_stream_report(stream)

    def test_valid_display_cache_preserves_chinese_and_source_binding(self):
        article, stream = self.stream()
        cached = MODULE.reusable_stream_translations(stream, [article],
            {"provider":"deepseek", "model":"test-model"})
        self.assertEqual(cached[article.id]["titleZh"], "美国航天局卫星任务")
        regenerated = MODULE.build_stream_report([article], self.config, self.now, translations=cached)
        rendered = self.browser_result(f'normalizeItem({json.dumps(regenerated["items"][0])}, 0)')
        self.assertEqual(rendered["summary"], "卫星计划于周一发射。")

    def test_featured_shorter_excerpt_cannot_discard_current_stream_translation(self):
        article = self.article("NASA satellite mission",
            "NASA plans a satellite launch for Monday. The satellite will monitor solar activity.")
        from evidence_trace import make_evidence, validate_news_trace
        article.source_evidence = make_evidence(article.description, article.url, self.now.isoformat())
        daily = MODULE.item_from_article(article, self.config, {"summary": "NASA plans a satellite launch for Monday."})
        validate_news_trace(daily)
        stream = MODULE.build_stream_report([article], self.config, self.now,
            top_stories={article.id:daily}, translations=self.translation(article))
        self.assertEqual(stream["translatedItemCount"], 1)
        self.assertEqual(stream["items"][0]["displayTranslation"]["sourceSummary"], article.description)
        daily["translationProvider"] = "deepseek"
        MODULE.merge_featured_stream_item(stream["items"][0], daily)
        MODULE.validate_stream_report(stream)
        validate_news_trace(stream["items"][0])
        self.assertEqual(stream["items"][0]["summary"], article.description)

    def test_malformed_cache_provider_is_ignored(self):
        article, stream = self.stream()
        stream["items"][0]["displayTranslation"]["provider"] = []
        self.assertEqual(MODULE.reusable_stream_translations(stream, [article],
            {"provider":"deepseek", "model":"test-model"}), {})

    def test_browser_rejects_translated_quantity_absent_from_source(self):
        _, stream = self.stream()
        item = stream["items"][0]
        for number in ["2099", "２０９９"]:
            with self.subTest(number=number):
                item["displayTranslation"]["summary"] = f"美国航天局于{number}年发射卫星。"
                normalized = self.browser_result(f'normalizeItem({json.dumps(item)}, 0)')
                self.assertEqual(normalized["summary"], "A satellite launch is scheduled for Monday.")

    def test_current_featured_display_is_reused_without_another_translation(self):
        article, stream = self.stream()
        regenerated = MODULE.build_stream_report([article], self.config, self.now,
            top_stories={article.id:stream["items"][0]})
        self.assertEqual(regenerated["translatedItemCount"], 1)
        self.assertEqual(regenerated["items"][0]["displayTranslation"]["summary"], "卫星计划于周一发射。")

    def test_normal_date_currency_and_word_numbers_remain_valid_translations(self):
        from evidence_trace import translation_text_valid
        for translated, source in [
            ("雷神获244亿美元合同", "Raytheon awarded $24.4 billion contract"),
            ("1942年10月3日V-2发射成功", "Oct. 3, 1942: The V-2 successfully launches"),
            ("平台新增7国", "The platform adds seven countries"),
            ("合同金额为2400万美元", "The contract is worth $24 million"),
            ("雷神获41亿美元合同", "Raytheon awarded $4.1 billion contract"),
            ("模型升级至2.0.1版本", "The model upgrades to version 2.0.1."),
            ("平台新增24国", "The platform adds twenty-four countries"),
        ]:
            with self.subTest(translated=translated):
                self.assertTrue(translation_text_valid(translated, source))
                item = {"title":source, "originalTitle":source, "summary":source, "summaryEvidenceRefs":["sample"],
                        "displayTranslation":{"version":1,"language":"zh-CN","provider":"deepseek",
                            "title":translated,"summary":translated,"sourceTitle":source,"sourceSummary":source,
                            "sourceEvidenceRefs":["sample"]}}
                self.assertEqual(self.browser_result(f'normalizeItem({json.dumps(item)}, 0)')["title"], translated)
        self.assertFalse(translation_text_valid("雷神获244万元合同", "Raytheon awarded $24.4 billion contract"))
        self.assertFalse(translation_text_valid("模型升级至2.0.2版本", "The model upgrades to version 2.0.1."))

    def test_title_only_response_keeps_source_placeholder(self):
        article = self.article("Iran war live: latest news", "")
        translated = self.translation(article)
        stream = MODULE.build_stream_report([article], self.config, self.now, translations=translated)
        self.assertEqual(stream["translatedItemCount"], 1)
        self.assertEqual(stream["items"][0]["displayTranslation"]["summary"], "未提取到可引用的正文，请查看原始报道。")

    def test_rejected_content_does_not_prevent_later_stream_batches(self):
        articles = [self.article("NASA satellite mission") for _ in range(3)]
        for index, article in enumerate(articles):
            article.id = str(index)
        config = {**self.config, "stream_translation_batch_size":1, "stream_translation_retry_rounds":0}
        invalid = {"items":[{"index":1,"titleZh":"2099年卫星任务","summary":"中文摘要","tags":[]}]}
        valid = {"items":[{"index":1,"titleZh":"卫星任务","summary":"中文摘要","tags":[]}]}
        with mock.patch.object(MODULE, "request_structured_json", side_effect=[invalid,invalid,valid]):
            translated, _, diagnostics = MODULE.ai_translate_articles(articles, config, {"provider":"deepseek"})
        self.assertEqual(set(translated), {"2"})
        self.assertEqual(diagnostics["missingItemCount"], 2)
