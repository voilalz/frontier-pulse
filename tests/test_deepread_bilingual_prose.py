"""English source evidence can support Chinese deepread prose without becoming model proof."""
import json
import unittest

import test_news_reading as reading
from test_update_news import MODULE
from deepread_editorial import build_daily_deepread, _validated_blocks, _validated_observations, COMPARISON_NOTE, _COMPARISON_LABELS
from evidence_trace import make_evidence, validate_deepread_trace, valid_prose_translation


class BilingualDeepreadTests(unittest.TestCase):
    setUp = reading.NewsReadingTests.setUp
    browser_result = reading.NewsReadingTests.browser_result

    def items(self):
        result = []
        self.translations = {}
        for index, (title, title_zh, sentence, sentence_zh) in enumerate([
            ("NASA tests Artemis capsule", "美国航天局测试阿尔忒弥斯飞船",
             "NASA is testing the Artemis capsule in a laboratory before the next flight.",
             "美国航天局正在实验室测试阿尔忒弥斯飞船，为下一次飞行做准备。"),
            ("Anthropic tests Claude model", "Anthropic测试Claude模型",
             "Anthropic is testing the Claude model with researchers before the next release.",
             "Anthropic正与研究人员测试Claude模型，为下一次发布做准备。"),
            ("Skydio tests autonomous drone", "Skydio测试自主无人机",
             "Skydio is testing an autonomous drone in a laboratory before the next flight.",
             "Skydio正在实验室测试自主无人机，为下一次飞行做准备。"),
            ("IBM tests quantum processor", "IBM测试量子处理器",
             "IBM is testing a quantum processor in a laboratory before the next demonstration.",
             "IBM正在实验室测试量子处理器，为下一次演示做准备。"),
        ]):
            detail = "Results remain preliminary and the programme is limited to laboratory tests."
            detail_zh = "测试结果仍属初步结果，项目目前仅限于实验室测试。"
            article = reading.NewsReadingTests.article(self, title, sentence + " " + detail)
            article.id = f"prose-{index}"
            article.url += f"-{index}"
            article.category = ("航空航天", "AI", "无人系统", "前沿技术")[index]
            article.raw_score = 90
            article.source_evidence = make_evidence(article.description, article.url, self.now.isoformat())
            result.append(MODULE.item_from_article(article, self.config, {
                "titleZh": title_zh, "summary": sentence_zh + detail_zh, "_provider": "deepseek"}))
            self.translations[article.id] = (sentence_zh, detail_zh)
        return result

    def provider(self, runtime, **kwargs):
        payload = json.loads(kwargs["input_text"])
        if kwargs["schema_name"] == "deepread_outline_v2":
            ids = [item["newsId"] for item in payload["candidates"][:4]]
            return {"selectedNewsIds": ids, "chapters": [{
                "title": "实验室测试的最新进展", "angle": "追踪本次报道中的具体变化",
                "newsIds": [news_id], "kind": "event", "comparisonKey": ""} for news_id in ids]}
        if kwargs["schema_name"] != "deepread_prose_v2":
            return None
        events = {item["newsId"]: item for item in payload["events"]}
        chapters = {}
        for chapter in payload["outline"]:
            news_id = chapter["newsIds"][0]
            chapters[chapter["id"]] = {"blocks": [{
                "type": "paragraph", "text": self.translations[news_id][index],
                "sourceText": record["text"], "newsIds": [news_id],
                "evidenceIds": [record["evidenceId"]],
            } for index, record in enumerate(events[news_id]["evidenceRecords"][:2])]}
        observations = [{"text": self.translations[news_id][0],
                         "sourceText": item["evidenceRecords"][0]["text"], "newsIds": [news_id],
                         "supports": [{"newsId": news_id, "supportQuote": item["evidenceRecords"][0]["text"]}]}
                        for news_id, item in list(events.items())[:2]]
        return {"headline": "实验室测试的阶段与后续任务节点",
                "lead": "本期分别追踪四项实验室测试，逐项梳理本次公开的动作、当前试验范围以及原文明确披露的后续任务节点。",
                "chapters": chapters, "observations": observations}

    def report(self):
        return build_daily_deepread(self.items(), {**self.config, "deepread_core_events": 4}, self.now,
                                    {"provider": "deepseek"}, self.provider)

    def test_english_sources_generate_complete_chinese_prose_and_observations(self):
        report = self.report()
        self.assertEqual(report["generationStatus"], "ok")
        validate_deepread_trace(report)
        normalized = self.browser_result(f'normalizeEditorialDeepread({json.dumps(report)})')
        self.assertEqual(len(normalized["observations"]), 2)
        for chapter in normalized["chapters"]:
            news_id = chapter["newsIds"][0]
            self.assertEqual([block["text"] for block in chapter["blocks"]], list(self.translations[news_id]))
        for entry in normalized["observations"]:
            self.assertEqual(entry["text"], self.translations[entry["newsIds"][0]][0])
        self.assertTrue(all("Results remain preliminary" in c["blocks"][1]["text"] for c in report["chapters"]))

    def test_invalid_observations_are_retried_without_regenerating_valid_chapters(self):
        items = self.items()
        calls = []
        def provider(runtime, **kwargs):
            calls.append(kwargs["schema_name"])
            if kwargs["schema_name"] == "deepread_observations_v2":
                payload = json.loads(kwargs["input_text"])
                candidates = payload["candidates"]
                for candidate in candidates:
                    self.assertLessEqual(len(candidate["sourceText"]), 220)
                    item = next(item for item in items if item["id"] == candidate["newsId"])
                    self.assertIn(candidate["sourceText"], [r["text"] for r in item["evidenceRecords"]])
                chosen = [next(c for c in candidates if c["newsId"] == item["id"]) for item in items[:2]]
                return {"observations": [{"text": self.translations[c["newsId"]][0],
                    "sourceText": c["sourceText"], "newsIds": [c["newsId"]],
                    "supports": [{"newsId": c["newsId"], "supportQuote": c["sourceText"]}]} for c in chosen]}
            result = self.provider(runtime, **kwargs)
            if kwargs["schema_name"] == "deepread_prose_v2":
                result["observations"] = []
            return result
        report = build_daily_deepread(items, {**self.config, "deepread_core_events": 4}, self.now,
                                     {"provider": "deepseek"}, provider)
        self.assertEqual(calls.count("deepread_prose_v2"), 1)
        self.assertEqual(calls.count("deepread_observations_v2"), 1)
        self.assertEqual(report["generationStatus"], "ok")
        validate_deepread_trace(report)
        normalized = self.browser_result(f'normalizeEditorialDeepread({json.dumps(report)})')
        self.assertEqual(len(normalized["observations"]), 2)
        self.assertEqual(normalized["observations"][0]["text"], self.translations[items[0]["id"]][0])

    def test_failed_observation_retry_preserves_chapters_and_partial_status(self):
        calls = []
        def provider(runtime, **kwargs):
            calls.append(kwargs["schema_name"])
            if kwargs["schema_name"] == "deepread_observations_v2":
                return {"observations": [{"text": "项目已全面获批并成功生产九十九艘飞船。",
                    "sourceText": "This invented quote is not captured source evidence.",
                    "newsIds": ["prose-0"], "supports": [{"newsId": "prose-0", "supportQuote": "Invented evidence."}]}] * 2}
            result = self.provider(runtime, **kwargs)
            if kwargs["schema_name"] == "deepread_prose_v2":
                result["observations"] = []
            return result
        report = build_daily_deepread(self.items(), {**self.config, "deepread_core_events": 4}, self.now,
                                     {"provider": "deepseek"}, provider)
        self.assertEqual(calls.count("deepread_observations_v2"), 1)
        self.assertEqual(report["generationStatus"], "partial")
        self.assertEqual(report["observations"], [])
        self.assertTrue(all(len(c["blocks"]) == 2 for c in report["chapters"]))
        validate_deepread_trace(report)

    def test_publication_and_frontend_refuse_tampered_prose_binding(self):
        report = self.report()
        block = report["chapters"][0]["blocks"][0]
        block.setdefault("displayTranslation", {})["sourceText"] = "An unrelated source."
        with self.assertRaises(ValueError):
            validate_deepread_trace(report)
        normalized = self.browser_result(f'normalizeEditorialDeepread({json.dumps(report)})')
        self.assertEqual(normalized["chapters"][0]["blocks"][0]["text"], '')

    def test_prose_requires_literal_source_and_preserves_numbers_and_negation(self):
        item = self.items()[0]
        chapter = {"kind": "event", "newsIds": [item["id"]]}
        record = item["evidenceRecords"][0]
        block = {"type": "paragraph", "text": self.translations[item["id"]][0],
                 "sourceText": record["text"], "newsIds": [item["id"]], "evidenceIds": [record["evidenceId"]]}
        for mutation in [{"sourceText": "NASA launched a capsule that is not in the source."},
                         {"text": "美国航天局测试了99艘飞船。"}, {"evidenceIds": ["evd-" + "0" * 20]}]:
            with self.subTest(mutation=mutation):
                self.assertIsNone(_validated_blocks(chapter, {"blocks": [{**block, **mutation}]}, set(), set(),
                                                   {item["id"]: item["evidenceRecords"]}, "deepseek"))

    def test_translation_keeps_source_negation_and_trial_scope(self):
        vectors = [
            ("NASA did not launch the capsule.", "美国航天局没有发射飞船。", "美国航天局已经发射飞船。"),
            ("NASA plans to launch the capsule.", "美国航天局计划发射飞船。", "美国航天局完成了飞船发射。"),
            ("Results remain preliminary and testing is limited to the laboratory.",
             "结果仍是初步的，测试仅限于实验室。", "测试已经证明项目全面成功。"),
            ("The NASA capsule has no launch approval.", "美国航天局飞船尚未获得发射批准。", "美国航天局飞船已获得发射批准。"),
            ("The NASA capsule is not approved for launch.", "美国航天局飞船尚未获得发射批准。", "飞船已获批发射，但尚未公布日期。"),
            ("NASA tested one capsule in the laboratory.", "美国航天局在实验室测试了一艘飞船。", "美国航天局在实验室测试了九十九艘飞船。"),
            ("NASA tested ninety-nine capsules in the laboratory.", "美国航天局在实验室测试了九十九艘飞船。", "美国航天局在实验室测试了九十八艘飞船。"),
            ("SM-6 is the only combat-proven weapon for this mission.", "SM-6是执行这项任务唯一经过实战验证的武器。", "SM-6是执行这项任务经过实战验证的武器。"),
            ("SM-6 is the only combat-proven weapon for this mission.", "SM-6是执行这项任务唯一一种经过实战验证的武器。", "SM-6是执行这项任务唯一两种经过实战验证的武器。"),
            ("The programme plans to buy hundreds of aircraft.", "该项目计划采购数百架飞机。", "该项目计划采购数千架飞机。"),
            ("The programme plans to buy hundreds of aircraft.", "该项目计划采购数百架飞机。", "该项目计划采购100架飞机。"),
            ("Raytheon secured a contract valued up to $24.4 billion.", "雷神获得了一份价值最高达244亿美元的合同。", "雷神获得了一份价值最高达245亿美元的合同。"),
            ("The programme plans to buy 20,000 aircraft.", "该项目计划采购2万架飞机。", "该项目计划采购3万架飞机。"),
            ("The programme plans to buy 20,000 aircraft.", "该项目计划采购２ 万架飞机。", "该项目计划采购３ 万架飞机。"),
            ("The programme plans to spend $24.4 trillion.", "该项目计划支出24.4万亿美元。", "该项目计划支出24.5万亿美元。"),
            ("Northrop has seven decades of autonomy experience.", "诺斯罗普拥有七十年的自主系统经验。", "诺斯罗普拥有七年的自主系统经验。"),
            ("The NASA capsule launch failed.", "美国航天局的飞船发射失败。", "美国航天局的飞船发射成功。"),
            ("The Navy is enforcing maritime dominance.", "美国海军正在维护海上主导权。", "美国海军正在 enforcing maritime dominance。"),
            ("The Navy is enforcing maritime dominance.", "美国海军正在维护海上主导权。", "美国海军正在enforcing maritime dominance。"),
            *[("The Navy is enforcing maritime dominance.", "美国海军正在维护海上主导权。",
               "美国海军正在enforcing" + space + "maritime" + space + "dominance。")
              for space in ("\u00a0", "\ufeff", "\u0085")],
        ]
        for source, faithful, invented in vectors:
            with self.subTest(source=source):
                refs = ["evd-" + "a" * 20]
                value = {"version": 1, "language": "zh-CN", "provider": "deepseek", "text": faithful,
                         "sourceText": source, "sourceEvidenceRefs": refs}
                self.assertTrue(valid_prose_translation(value, source, refs))
                self.assertFalse(valid_prose_translation({**value, "text": invented}, source, refs))
                self.assertEqual(self.browser_result(f'proseDisplayText({json.dumps(value)}, {json.dumps(source)}, {json.dumps(refs)})'), faithful)
                self.assertEqual(self.browser_result(f'proseDisplayText({json.dumps({**value, "text": invented})}, {json.dumps(source)}, {json.dumps(refs)})'), "")

    def test_prose_keeps_english_proper_names(self):
        source, text, refs = "USS Gerald Ford is in the port.", "USS Gerald Ford目前正在港口。", ["evd-" + "a" * 20]
        value = {"version": 1, "language": "zh-CN", "provider": "deepseek", "text": text,
                 "sourceText": source, "sourceEvidenceRefs": refs}
        self.assertTrue(valid_prose_translation(value, source, refs))
        self.assertEqual(self.browser_result(f'proseDisplayText({json.dumps(value)}, {json.dumps(source)}, {json.dumps(refs)})'), text)

    def test_outline_prompt_and_example_match_fixed_membership_and_chinese_contract(self):
        calls = []
        def provider(runtime, **kwargs):
            if kwargs["schema_name"] == "deepread_outline_v2":
                payload = json.loads(kwargs["input_text"])
                fixed = payload.get("fixedSelectedNewsIds")
                self.assertEqual(fixed, kwargs["example"]["selectedNewsIds"])
                self.assertEqual(fixed, kwargs["schema"]["properties"]["selectedNewsIds"]["items"]["enum"])
                self.assertTrue(all(any('\u4e00' <= char <= '\u9fff' for char in chapter["title"])
                                    for chapter in kwargs["example"]["chapters"]))
                calls.append(kwargs["schema_name"])
            return self.provider(runtime, **kwargs)
        report = build_daily_deepread(self.items(), {**self.config, "deepread_core_events": 4}, self.now,
                                     {"provider": "deepseek"}, provider)
        self.assertEqual(calls, ["deepread_outline_v2"])
        self.assertEqual(report["generationStatus"], "ok")

    def test_fixed_comparison_text_cannot_be_rewritten_as_a_fact(self):
        items = self.items()[:2]
        ids = [item["id"] for item in items]
        context = {item["id"]: item["evidenceRecords"] for item in items}
        chapter = {"kind": "comparison", "comparisonKey": "ai-agent", "newsIds": ids}
        method = f"本章按{_COMPARISON_LABELS['ai-agent']}并列呈现以上原文证据。{COMPARISON_NOTE}"
        refs = [record["evidenceId"] for item in items for record in item["evidenceRecords"]]
        paragraphs = [{"type": "paragraph", "text": self.translations[item["id"]][0],
                       "sourceText": item["evidenceRecords"][0]["text"], "newsIds": [item["id"]],
                       "evidenceIds": [item["evidenceRecords"][0]["evidenceId"]]} for item in items]
        comparison = {"type": "comparison", "text": method, "sourceText": method, "newsIds": ids, "evidenceIds": refs}
        self.assertIsNotNone(_validated_blocks(chapter, {"blocks": paragraphs + [comparison]}, set(), set(), context, "deepseek"))
        invented = "两家公司联合发布了新模型，并不需要后续测试。"
        self.assertIsNone(_validated_blocks(chapter, {"blocks": paragraphs + [{**comparison, "text": invented}]}, set(), set(), context, "deepseek"))
        value = {"version": 1, "language": "zh-CN", "provider": "deepseek", "text": invented,
                 "sourceText": method, "sourceEvidenceRefs": refs}
        self.assertFalse(valid_prose_translation(value, method, refs))
        self.assertEqual(self.browser_result(f'proseDisplayText({json.dumps(value)}, {json.dumps(method)}, {json.dumps(refs)})'), "")

    def test_one_valid_multi_event_observation_does_not_mark_report_complete(self):
        from test_deepread_editorial import EditorialDeepreadTests
        fixture = EditorialDeepreadTests()
        fixture.setUp()
        items = [fixture.item(0, summary="美国航天局公布实验室测试结果。"),
                 fixture.item(1, summary="欧洲航天局公布实验室测试结果。")]
        supports = [{"newsId": item["id"], "supportQuote": item["evidenceRecords"][0]["text"]} for item in items]
        entry = {"text": " ".join(support["supportQuote"] for support in supports),
                 "newsIds": [item["id"] for item in items], "supports": supports}
        self.assertIsNone(_validated_observations([entry, {"text": "无效", "newsIds": [], "supports": []}], items, set()))

    def test_observation_binding_cannot_use_another_evidence_reference(self):
        report = self.report()
        entry = report["observations"][0]
        entry["displayTranslation"]["sourceEvidenceRefs"] = [report["events"][1]["evidenceRecords"][0]["evidenceId"]]
        with self.assertRaises(ValueError):
            validate_deepread_trace(report)
        normalized = self.browser_result(f'normalizeEditorialDeepread({json.dumps(report)})')
        self.assertEqual(normalized["observations"][0]["text"], '')


if __name__ == "__main__":
    unittest.main()
