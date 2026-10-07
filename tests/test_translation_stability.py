"""Server/client agreement on real quantities, legacy display and completion."""
import copy
import json
import unittest

import test_news_reading as reading
from test_update_news import MODULE
from evidence_trace import make_evidence, translation_text_valid, valid_display_translation, valid_prose_translation


class TranslationStabilityTests(unittest.TestCase):
    setUp = reading.NewsReadingTests.setUp
    browser_result = reading.NewsReadingTests.browser_result

    def item(self, source="NASA plans a satellite launch for Monday.", title="美国航天局计划发射卫星", summary="美国航天局计划于周一发射卫星。"):
        article = reading.NewsReadingTests.article(self, source, source)
        article.source_evidence = make_evidence(source, article.url, self.now.isoformat())
        return MODULE.item_from_article(article, self.config, {"titleZh": title, "summary": summary, "_provider": "deepseek"})

    def test_months_and_currency_abbreviations_agree_in_server_and_browser(self):
        pairs = [
            ("改进型M8步枪将于12月开始列装", "The improved M8 rifle will begin fielding in December"),
            ("Ramp前工程师为Melius平台筹集2000万美元", "Ex-Ramp engineers raise $20M for platform Melius"),
            ("公司筹集15亿美元", "The company raises USD 1.5B"),
            ("公司筹集15亿美元", "The company raises 1.5B USD"),
            ("平台筹集250万欧元", "The platform raises €2.5m"),
            ("平台筹集2000万美元", "The platform raises 20M dollars"),
            ("卫星将于5月发射", "The satellite will launch in May"),
            ("卫星计划于5月发射", "The satellite launch is scheduled for May"),
            ("卫星将于10月3日发射", "The satellite will launch on 3 October"),
            ("军方测试F35战机", "The military tests the F-35 fighter"),
        ]
        for translated, source in pairs:
            with self.subTest(source=source):
                self.assertTrue(translation_text_valid(translated, source))
                item = self.item(source, translated, translated)
                self.assertTrue(valid_display_translation(item))
                normalized = self.browser_result(f'normalizeItem({json.dumps(item)}, 0)')
                self.assertEqual(normalized["title"], translated)
                self.assertEqual(normalized["summary"], translated)

    def test_model_names_meter_units_and_modal_may_cannot_invent_amounts_or_dates(self):
        pairs = [
            ("M8步枪价值800万美元", "The M8 rifle enters service"),
            ("线缆长2000万米", "The cable is 20m long"),
            ("卫星将在5月发射", "The satellite may launch soon"),
            ("该系统于5月发射卫星", "This may launch a satellite soon"),
            ("猎鹰9号于5月发射卫星", "Falcon 9 may launch another satellite soon"),
            ("存储价值2000万美元", "The device has $20MB storage"),
            ("M.2适配器售价2000万美元", "The $20 M.2 adapter was released"),
            ("K-band天线售价2万美元", "The $20 K-band antenna was released"),
            ("M12步枪将开始列装", "The M8 rifle will enter service in December"),
            ("平台筹集200万美元", "The platform raises $20M"),
        ]
        for translated, source in pairs:
            with self.subTest(source=source):
                self.assertFalse(translation_text_valid(translated, source))
                self.assertFalse(self.browser_result(f'validZh({json.dumps(translated)}, {json.dumps(source)})'))

    def test_calendar_may_is_not_a_planned_qualifier_but_modal_may_is_retained(self):
        refs = ["sample"]
        for source, translated, valid in [
            ("NASA launched a satellite in May.", "美国航天局于5月发射了一颗卫星。", True),
            ("NASA launched a satellite on May 3.", "美国航天局于5月3日发射了一颗卫星。", True),
            ("This May the system launched a satellite.", "该系统于5月发射了一颗卫星。", True),
            ("NASA may launch a satellite soon.", "美国航天局已经发射了一颗卫星。", False),
            ("This may launch a satellite soon.", "该系统已经发射了一颗卫星。", False),
            ("Falcon 9 may launch another satellite soon.", "猎鹰9号已经成功发射卫星。", False),
            ("Falcon 9 May Launch Another Satellite Soon.", "猎鹰9号已经成功发射卫星。", False),
            ("This May Launch A New Satellite Mission.", "新卫星任务已经成功启动。", False),
        ]:
            with self.subTest(source=source):
                value = {"version": 1, "language": "zh-CN", "provider": "deepseek", "text": translated,
                         "sourceText": source, "sourceEvidenceRefs": refs}
                self.assertEqual(valid_prose_translation(value, source, refs), valid)
                display = self.browser_result(f'proseDisplayText({json.dumps(value)}, {json.dumps(source)}, {json.dumps(refs)})')
                self.assertEqual(display, translated if valid else '')

    def test_legacy_title_only_placeholder_keeps_bound_chinese_title(self):
        item = self.item()
        placeholder = "未提取到可引用的正文，请查看原始报道。"
        item.update(summary=placeholder, evidenceRecords=[], summaryEvidenceRefs=[])
        item["displayTranslation"].update(summary=placeholder, sourceSummary=placeholder, sourceEvidenceRefs=[])
        normalized = self.browser_result(f'normalizeItem({json.dumps(item)}, 0)')
        self.assertEqual(normalized["title"], "美国航天局计划发射卫星")
        self.assertEqual(normalized["summary"], "")
        self.assertEqual(normalized["contentAvailability"], "title-only")
        self.assertEqual(normalized["translationStatus"], "translated")

    def test_legacy_title_only_missing_records_has_the_same_status_on_repeat_normalization(self):
        item = self.item()
        item.update(summary="", summaryEvidenceRefs=[])
        item.pop("evidenceRecords")
        item["displayTranslation"].update(summary="", sourceSummary="", sourceEvidenceRefs=[])
        for expression in [f'normalizeItem({json.dumps(item)}, 0)',
                           f'normalizeItem(normalizeItem({json.dumps(item)}, 0), 0)']:
            normalized = self.browser_result(expression)
            self.assertEqual(normalized["translationStatus"], "translated")
            self.assertEqual(normalized["contentAvailability"], "title-only")

    def test_legacy_body_translation_discards_only_separate_metadata_filler_sentence(self):
        item = self.item()
        item["displayTranslation"]["summary"] += "现有元数据未说明后续安排。"
        normalized = self.browser_result(f'normalizeItem({json.dumps(item)}, 0)')
        self.assertEqual(normalized["summary"], "美国航天局计划于周一发射卫星。")
        self.assertEqual(normalized["translationStatus"], "translated")
        # Compatibility must retain the exact source binding.
        item["displayTranslation"]["sourceSummary"] = "Unrelated evidence."
        self.assertEqual(self.browser_result(f'normalizeItem({json.dumps(item)}, 0)')["summary"], "")

    def test_missing_body_translation_keeps_valid_title_and_recounts_completion(self):
        good = self.item()
        bad = copy.deepcopy(good)
        bad["id"] = "bad"
        bad["displayTranslation"]["summary"] = "现有元数据未提供摘要。"
        payload = {"items": [good, bad], "translatedItemCount": 2,
                   "translationStatus": "ok", "translationProvider": "deepseek"}
        expression = f'normalizeReport({json.dumps(payload)})'
        daily = self.browser_result(expression)
        self.assertEqual(daily["items"][1]["title"], "美国航天局计划发射卫星")
        self.assertEqual(daily["items"][1]["summary"], "")
        self.assertEqual(daily["items"][1]["translationStatus"], "partial")
        for normalizer in [expression, f'normalizeCollection({json.dumps(payload)}, "news")']:
            report = self.browser_result(normalizer)
            self.assertEqual(report["translatedItemCount"], 1)
            self.assertEqual(report["partialTranslatedItemCount"], 1)
            self.assertEqual(report["translationStatus"], "partial")

    def test_bookmark_normalization_retains_bound_translation_and_pending_body(self):
        for summary, status in [("美国航天局计划于周一发射卫星。", "translated"), ("现有元数据未提供摘要。", "partial")]:
            with self.subTest(status=status):
                item = self.item(summary=summary)
                if status == "partial":
                    item = self.item()
                    item["displayTranslation"]["summary"] = summary
                normalized = self.browser_result(f'normalizeItem(normalizeItem({json.dumps(item)}, 0), 0)')
                self.assertEqual(normalized["title"], "美国航天局计划发射卫星")
                self.assertEqual(normalized["translationStatus"], status)
                self.assertEqual(normalized["summary"], summary if status == "translated" else "")

    def test_client_global_diagnostics_use_current_display_and_global_denominator(self):
        good = self.item()
        bad = copy.deepcopy(good)
        bad["id"] = "bad"
        bad["displayTranslation"]["summary"] = "现有元数据未提供摘要。"
        payload = {"items": [good, bad], "translatedItemCount": 2, "translationProvider": "deepseek",
                   "translationDiagnostics": {"requestedItemCount": 2, "completedItemCount": 2,
                    "missingItemCount": 0, "totalTranslatedItemCount": 2, "totalMissingItemCount": 0,
                    "completionMessage": "全部条目首轮完成"}}
        report = self.browser_result(f'normalizeCollection({json.dumps(payload)}, "news")')
        diagnostics = report["translationDiagnostics"]
        self.assertEqual(diagnostics["totalTranslatedItemCount"], 1)
        self.assertEqual(diagnostics["totalMissingItemCount"], 1)
        self.assertEqual(diagnostics["completedItemCount"], 2)
        self.assertIn("1/2", self.browser_result(f'batchDiagnosticWarning({json.dumps(diagnostics)}, "动态")'))
        batch = {"requestedItemCount": 3, "completedItemCount": 3, "totalTranslatedItemCount": 6,
                 "totalMissingItemCount": 3, "completionMessage": "本轮已完成；还有3条未请求"}
        self.assertIn("6/9", self.browser_result(f'batchDiagnosticWarning({json.dumps(batch)}, "动态")'))


if __name__ == "__main__":
    unittest.main()
