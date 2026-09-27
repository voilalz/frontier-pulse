"""Contract tests for the channel-neutral daily editorial document."""

import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from deepread_editorial import build_daily_deepread


class EditorialDeepreadTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 26, 23, 7, tzinfo=timezone.utc)
        self.config = {
            "deepread_target_events": 12, "deepread_core_events": 5,
            "rss_feeds": [{"name": "NASA", "source_kind": "primary"}],
            "content_policy": json.loads((ROOT / "public/assets/news-policy.json").read_text()),
        }

    def item(self, n, **overrides):
        item = {
            "id": f"news-{n}", "eventId": f"evt-{n}",
            "title": f"第{n}项航空试验发布具体结果", "originalTitle": f"Project {n} reports trial results",
            "summary": f"第{n}项航空试验公布本次任务结果，报道列出已完成的测试步骤和后续安排。",
            "category": ("航空航天", "AI", "无人系统", "前沿技术")[n % 4],
            "source": f"Publisher {n}", "url": f"https://publisher{n}.example/story",
            "sources": [{"name": f"Publisher {n}", "url": f"https://publisher{n}.example/story",
                         "evidenceGroup": f"outlet:publisher{n}.example"}],
            "publishedAt": (self.now - timedelta(hours=1 + n % 20)).isoformat(),
            "score": 90 - n, "contentType": "news",
        }
        item.update(overrides)
        return item

    def test_twelve_candidates_yield_only_five_core_events_in_channel_neutral_model(self):
        report = build_daily_deepread([self.item(n) for n in range(12)], self.config, self.now)
        self.assertEqual(report["schemaVersion"], 2)
        self.assertEqual(report["candidateCount"], 12)
        self.assertEqual(report["eventCount"], 5)
        self.assertEqual(len(report["events"]), 5)
        self.assertEqual(report["generationStatus"], "fallback")
        self.assertEqual({n for chapter in report["chapters"] for n in chapter["newsIds"]},
                         {event["newsId"] for event in report["events"]})
        self.assertTrue(all(len(chapter["newsIds"]) == 1 for chapter in report["chapters"]))
        self.assertNotIn("watchFor", json.dumps(report))
        self.assertNotIn("analysis", json.dumps(report))
        self.assertEqual(report["events"][0]["originalTitle"],
                         next(item["originalTitle"] for item in [self.item(n) for n in range(12)]
                              if item["id"] == report["events"][0]["newsId"]))

    def test_history_only_accepts_previous_entries_for_same_canonical_event(self):
        registry = {"identityAliases": {"evt-old": "evt-0"}, "items": [{
            "eventId": "evt-0", "timeline": [
                {"editionDate": "2026-09-25", "newsId": "older", "title": "NASA 宣布试验安排", "source": "NASA",
                 "originalTitle": "NASA announces trial plan", "summaryLead": "NASA 公布本项任务的试验安排。"},
                {"editionDate": "2026-09-27", "newsId": "news-0", "title": "今日结果", "source": "NASA"},
                {"editionDate": "2026-09-24", "newsId": "news-0", "title": "重复报道", "source": "NASA"},
            ]}, {"eventId": "evt-1", "timeline": [
                {"editionDate": "2026-09-25", "newsId": "unrelated", "title": "同一领域的另一项目", "source": "媒体"},
            ]}]}
        report = build_daily_deepread([self.item(0, eventId="evt-old")], self.config, self.now,
                                      event_registry=registry)
        event = report["events"][0]
        self.assertEqual(event["eventId"], "evt-0")
        self.assertEqual([entry["newsId"] for entry in event["history"]], ["older"])
        self.assertTrue(any(block["type"] == "change" for block in report["chapters"][0]["blocks"]))
        self.assertEqual(report["generationStatus"], "insufficient")

    def test_excluded_historical_title_never_enters_public_article_or_model_prompt(self):
        registry = {"items": [{"eventId": "evt-0", "timeline": [
            {"editionDate": "2026-09-25", "newsId": "prior-banned",
             "title": "China launches satellite for this project", "source": "Archive"},
        ]}]}
        calls = []
        def provider(runtime, **kwargs):
            calls.append(kwargs["input_text"])
            return None
        report = build_daily_deepread([self.item(n) for n in range(4)], self.config, self.now,
                                      {"provider": "fixture"}, provider, event_registry=registry)
        self.assertEqual(report["events"][0]["history"], [])
        self.assertNotIn("China launches satellite", json.dumps(report))
        self.assertNotIn("China launches satellite", " ".join(calls))

    def test_historical_title_requires_original_headline_and_lead_policy_check(self):
        registry = {"items": [{"eventId": "evt-0", "timeline": [
            {"editionDate": "2026-09-24", "newsId": "old-unknown", "title": "项目发布任务计划"},
            {"editionDate": "2026-09-25", "newsId": "old-title", "title": "项目发布任务计划",
             "originalTitle": "China launches a new mission", "summaryLead": "任务计划已发布。"},
            {"editionDate": "2026-09-26", "newsId": "old-lead", "title": "项目发布任务计划",
             "originalTitle": "Project releases mission plan", "summaryLead": "中国公布本项任务。"},
        ]}]}
        report = build_daily_deepread([self.item(0)], self.config, self.now, event_registry=registry)
        self.assertEqual(report["events"][0]["history"], [])
        self.assertNotIn("项目发布任务计划", json.dumps(report, ensure_ascii=False))

    def test_prior_search_index_metadata_can_validate_legacy_timeline(self):
        registry = {"items": [{"eventId": "evt-0", "timeline": [
            {"editionDate": "2026-09-25", "newsId": "old", "title": "项目安排试验", "source": "NASA"},
        ]}]}
        report = build_daily_deepread([self.item(0)], self.config, self.now,
                                      event_registry=registry, history_items=[{
                                          "id": "old", "originalTitle": "NASA schedules project trial",
                                          "summary": "NASA公布测试时间和任务步骤。"}])
        self.assertEqual(report["events"][0]["history"][0]["newsId"], "old")

    def test_old_source_does_not_upgrade_current_single_source_to_multi(self):
        current = self.item(0)
        old = self.item(20, eventId="evt-0", publishedAt=(self.now - timedelta(hours=48)).isoformat(),
                        sources=[{"name": "Old Publisher", "url": "https://old.example/story",
                                  "evidenceGroup": "outlet:old.example"}])
        report = build_daily_deepread([current, old], self.config, self.now)
        self.assertEqual(report["events"][0]["evidenceLevel"], "single")
        self.assertEqual(len(report["events"][0]["sources"]), 1)

    def test_stale_nested_source_is_not_cited_or_counted_as_current_corroboration(self):
        item = self.item(0, sources=[
            {"name": "Current", "url": "https://publisher0.example/story", "evidenceGroup": "outlet:current",
             "publishedAt": (self.now - timedelta(hours=1)).isoformat()},
            {"name": "Old", "url": "https://old.example/story", "evidenceGroup": "outlet:old",
             "publishedAt": (self.now - timedelta(hours=48)).isoformat()},
        ])
        report = build_daily_deepread([item], self.config, self.now)
        self.assertEqual(report["events"][0]["evidenceLevel"], "single")
        self.assertEqual(len(report["events"][0]["sources"]), 1)
        self.assertNotIn("old.example", json.dumps(report))

    def test_evidence_labels_distinguish_primary_multi_single_and_opinion(self):
        primary = self.item(0, source="NASA", url="https://nasa.gov/story",
                            sources=[{"name": "NASA", "url": "https://nasa.gov/story", "evidenceGroup": "official:nasa"}])
        multi = self.item(1, sources=[
            {"name": "A", "url": "https://a.example/1", "evidenceGroup": "outlet:a"},
            {"name": "B", "url": "https://b.example/2", "evidenceGroup": "outlet:b"}])
        single = self.item(2, sources=[
            {"name": "C", "url": "https://c.example/1", "evidenceGroup": "wire:one"},
            {"name": "D", "url": "https://d.example/2", "evidenceGroup": "wire:one"}])
        opinion = self.item(3, articleType="opinion", sources=[
            {"name": "E", "url": "https://e.example/1", "evidenceGroup": "outlet:e"},
            {"name": "F", "url": "https://f.example/2", "evidenceGroup": "outlet:f"}])
        report = build_daily_deepread([primary, multi, single, opinion], self.config, self.now)
        self.assertEqual({event["newsId"]: event["evidenceLevel"] for event in report["events"]}, {
            "news-0": "primary", "news-1": "multi", "news-2": "single", "news-3": "opinion",
        })

    def test_old_event_alias_keeps_same_wire_reprints_as_one_source_group(self):
        item = self.item(0, eventId="evt-old", sources=[
            {"name": "A", "url": "https://a.example/1", "evidenceGroup": "wire:one"},
            {"name": "B", "url": "https://b.example/2", "evidenceGroup": "wire:one"}])
        report = build_daily_deepread([item], self.config, self.now,
                                      event_registry={"identityAliases": {"evt-old": "evt-0"}, "items": []})
        self.assertEqual(report["events"][0]["eventId"], "evt-0")
        self.assertEqual(report["events"][0]["evidenceLevel"], "single")

    def test_outline_then_prose_uses_fixed_membership_and_mandatory_history_change(self):
        items = [self.item(n) for n in range(12)]
        registry = {"items": [{"eventId": "evt-0", "timeline": [
            {"editionDate": "2026-09-26", "newsId": "prior", "title": "项目进入准备阶段", "source": "NASA",
             "originalTitle": "Project enters preparation phase", "summaryLead": "该项目公布试验前的准备步骤。"},
        ]}]}
        calls = []
        def provider(runtime, **kwargs):
            calls.append(kwargs)
            if kwargs["schema_name"] == "deepread_outline_v2":
                return {"selectedNewsIds": [f"news-{n}" for n in range(5)], "chapters": [
                    {"title": f"第{n}项任务的最新进展", "angle": "对照这项任务前后两次公开动作", "newsIds": [f"news-{n}"]}
                    for n in range(5)]}
            self.assertEqual(kwargs["schema_name"], "deepread_prose_v2")
            self.assertNotIn("news-6", kwargs["input_text"])
            return {
                "headline": "五项项目进展公布，重点观察具体任务节点",
                "lead": "今天的五项项目进展分别涉及不同任务。以下按项目梳理今天披露的动作，并在有历史记录时对照前次报道中的节点。",
                "observations": [
                    {"text": "首项试验本期公布了任务结果，已完成步骤可与后续安排分开核对。", "newsIds": ["news-0"],
                     "supports": [{"newsId": "news-0", "supportQuote": "第0项航空试验公布本次任务结果"}]},
                    {"text": "第二项试验已公布测试步骤，后续安排仍要按原报道的范围追踪。", "newsIds": ["news-1"],
                     "supports": [{"newsId": "news-1", "supportQuote": "报道列出已完成的测试步骤和后续安排"}]},
                ],
                "chapters": {f"chapter-{n+1}": {"blocks": [
                    {"type": "paragraph", "text": f"第{n}项项目今天披露了任务结果和下一步安排，这项报道提供了可追踪的具体节点。", "newsIds": [f"news-{n}"]},
                    *([{"type": "change", "text": "此前公布准备阶段；今天披露了实际试验结果，项目由计划进入执行记录。", "newsIds": ["news-0"]}] if n == 0 else []),
                ]} for n in range(5)},
            }
        report = build_daily_deepread(items, self.config, self.now, {"provider": "fixture"}, provider,
                                      event_registry=registry)
        self.assertEqual([call["schema_name"] for call in calls], ["deepread_outline_v2", "deepread_prose_v2"])
        self.assertIn("change", [block["type"] for block in calls[1]["example"]["chapters"]["chapter-1"]["blocks"]])
        self.assertEqual(report["generationStatus"], "ok")
        self.assertEqual(report["eventCount"], 5)
        self.assertTrue(any(block["type"] == "change" for block in report["chapters"][0]["blocks"]))
        self.assertTrue(all(event["sources"] for event in report["events"]))
        self.assertEqual(len(report["observations"]), 2)

    def test_outline_selects_four_when_configured_and_splits_weakly_related_events(self):
        items = [self.item(n) for n in range(12)]
        items[0].update(category="AI", originalTitle="OpenAI bots disrupt agency websites")
        items[1].update(category="AI", originalTitle="OpenAI pauses strongest model after data leak")
        def provider(runtime, **kwargs):
            if kwargs["schema_name"] == "deepread_outline_v2":
                return {"selectedNewsIds": ["news-0", "news-1", "news-2", "news-3"], "chapters": [
                    {"title": "航空试验与 AI 研究", "angle": "对照两项完全不同的进展", "newsIds": ["news-0", "news-1"]},
                    {"title": "机器人任务进展", "angle": "追踪第三项任务的具体进展", "newsIds": ["news-2"]},
                    {"title": "前沿技术进展", "angle": "追踪第四项任务的具体进展", "newsIds": ["news-3"]},
                ]}
            outline = json.loads(kwargs["input_text"])["outline"]
            return {"headline": "四项独立进展各自对应不同任务节点",
                    "lead": "今天的四项报道涉及不同项目，应分别追踪各自完成的具体动作，不按宽泛领域拼接为共同趋势。",
                    "observations": [
                        {"text": "第一项任务已有明确试验结果，可以对照报道公布的测试步骤。", "newsIds": ["news-0"],
                         "supports": [{"newsId": "news-0", "supportQuote": "第0项航空试验公布本次任务结果"}]},
                        {"text": "第二项任务仍需追踪其后续安排，现有材料只覆盖已完成的步骤。", "newsIds": ["news-1"],
                         "supports": [{"newsId": "news-1", "supportQuote": "报道列出已完成的测试步骤和后续安排"}]},
                    ],
                    "chapters": {chapter["id"]: {"blocks": [
                        {"type": "paragraph", "text": "该项目今天公布了已完成的动作和下一阶段安排，材料说明了任务边界。",
                         "newsIds": chapter["newsIds"]}
                    ]} for chapter in outline}}
        report = build_daily_deepread(items, {**self.config, "deepread_core_events": 4}, self.now,
                                      {"provider": "fixture"}, provider)
        self.assertEqual(report["generationStatus"], "ok")
        self.assertEqual(report["eventCount"], 4)
        self.assertEqual(len(report["chapters"]), 4)
        self.assertTrue(all(len(chapter["newsIds"]) == 1 for chapter in report["chapters"]))

    def test_model_cannot_expand_five_core_events_to_six(self):
        def provider(runtime, **kwargs):
            if kwargs["schema_name"] == "deepread_outline_v2":
                return {"selectedNewsIds": [f"news-{n}" for n in range(6)], "chapters": [
                    {"title": f"第{n}项试验进展", "angle": "核对本次试验公布的结果", "newsIds": [f"news-{n}"]}
                    for n in range(6)]}
            return None
        report = build_daily_deepread([self.item(n) for n in range(8)], self.config, self.now,
                                      {"provider": "fixture"}, provider)
        self.assertEqual(report["eventCount"], 5)
        self.assertEqual(len(report["chapters"]), 5)

    def test_two_supported_observations_survive_an_invalid_third(self):
        def provider(runtime, **kwargs):
            if kwargs["schema_name"] == "deepread_outline_v2":
                return {"selectedNewsIds": [f"news-{n}" for n in range(5)], "chapters": [
                    {"title": f"第{n}项试验进展", "angle": "核对本次试验公布的结果", "newsIds": [f"news-{n}"]}
                    for n in range(5)]}
            outline = json.loads(kwargs["input_text"])["outline"]
            observations = [{"text": f"第{n}项试验已有结果，报道还列出已完成的步骤与后续安排。",
                             "newsIds": [f"news-{n}"], "supports": [{"newsId": f"news-{n}",
                             "supportQuote": f"第{n}项航空试验公布本次任务结果，报道列出已完成的测试步骤和后续安排"}]}
                            for n in range(2)]
            observations.append({"text": "第三项试验现已全面证实安全，后续可以直接推广应用。",
                                 "newsIds": ["news-2"], "supports": [
                                     {"newsId": "news-2", "supportQuote": "不存在的原文引述"}]})
            return {"headline": "五项航空试验报道展示了各自不同的进展",
                    "lead": "本期对五项独立试验逐项核对当前公开的结果和后续安排，不将一个项目的结论推及其他项目。",
                    "chapters": {chapter["id"]: {"blocks": [{"type": "paragraph",
                         "text": "这项报道公布本次试验的结果和已完成的测试步骤，也列出后续安排。",
                         "newsIds": chapter["newsIds"]}]} for chapter in outline},
                    "observations": observations}
        report = build_daily_deepread([self.item(n) for n in range(5)], self.config, self.now,
                                      {"provider": "fixture"}, provider)
        self.assertEqual(report["generationStatus"], "ok")
        self.assertEqual([entry["newsIds"] for entry in report["observations"]], [["news-0"], ["news-1"]])

    def test_explicit_evidence_limits_supply_short_observations_when_provider_quotes_fail(self):
        items = [self.item(n, summary=(
            f"第{n}项项目已完成初步测试并公布结果。"
            + ("具体影响范围和下一阶段试验时间尚未披露。" if n < 3
               else "设备的实际部署地点和数量尚未披露。"))) for n in range(5)]
        def provider(runtime, **kwargs):
            if kwargs["schema_name"] == "deepread_outline_v2":
                return None
            outline = json.loads(kwargs["input_text"])["outline"]
            return {"headline": "项目测试结果与尚待披露的后续节点",
                    "lead": "本期五项独立报道均已披露初步测试结果，但若干后续安排和具体影响范围仍有待进一步公开核对。",
                    "chapters": {chapter["id"]: {"blocks": [{"type": "paragraph",
                         "text": "报道确认了初步测试和公开结果，也说明目前尚未披露后续具体安排。",
                         "newsIds": chapter["newsIds"]}]} for chapter in outline},
                    "observations": [{"text": "所有项目均已全面获批并开始量产。",
                                      "newsIds": ["news-0"], "supports": [
                                          {"newsId": "news-0", "supportQuote": "并不存在的原文"}]}]}
        report = build_daily_deepread(items, self.config, self.now,
                                      {"provider": "fixture"}, provider)
        self.assertEqual(len(report["observations"]), 2)
        self.assertIn("现有材料尚不足以判断设备的实际部署地点和数量，需等后续公开信息。",
                      {entry["text"] for entry in report["observations"]})
        self.assertTrue(all(entry["supports"][0]["supportQuote"] in items[int(entry["newsIds"][0][-1])]["summary"]
                            for entry in report["observations"]))
        self.assertNotIn("全面获批", json.dumps(report["observations"], ensure_ascii=False))

    def test_outline_splits_unrelated_satellite_projects_in_same_category(self):
        items = [self.item(n) for n in range(4)]
        items[0].update(category="航空航天", originalTitle="NASA satellite tests communication relay")
        items[1].update(category="航空航天", originalTitle="JAXA satellite launches climate sensor")
        def provider(runtime, **kwargs):
            if kwargs["schema_name"] == "deepread_outline_v2":
                return {"selectedNewsIds": [f"news-{n}" for n in range(4)], "chapters": [
                    {"title": "卫星项目的共同进展", "angle": "观察两项不同任务的具体目标", "newsIds": ["news-0", "news-1"]},
                    *[{"title": f"第{n}项独立任务", "angle": "追踪本项任务披露的具体步骤", "newsIds": [f"news-{n}"]}
                      for n in (2, 3)],
                ]}
            return None
        report = build_daily_deepread(items, self.config, self.now,
                                      {"provider": "fixture"}, provider)
        self.assertEqual(len(report["chapters"]), 4)
        self.assertTrue(all(len(chapter["newsIds"]) == 1 for chapter in report["chapters"]))

    def test_outline_can_group_two_reports_on_named_project(self):
        items = [self.item(n) for n in range(4)]
        items[0].update(category="航空航天", originalTitle="Starship completes another launch test")
        items[1].update(category="航空航天", originalTitle="Starship reports new flight data")
        def provider(runtime, **kwargs):
            if kwargs["schema_name"] == "deepread_outline_v2":
                return {"selectedNewsIds": [f"news-{n}" for n in range(4)], "chapters": [
                    {"title": "Starship 试验持续推进", "angle": "核对同一项目披露的试验结果", "newsIds": ["news-0", "news-1"]},
                    *[{"title": f"第{n}项独立任务", "angle": "追踪本项任务披露的具体步骤", "newsIds": [f"news-{n}"]}
                      for n in (2, 3)],
                ]}
            return None
        report = build_daily_deepread(items, self.config, self.now,
                                      {"provider": "fixture"}, provider)
        self.assertEqual(report["chapters"][0]["newsIds"], ["news-0", "news-1"])
        self.assertEqual(len(report["chapters"]), 3)

    def test_model_cannot_inject_source_or_move_event_to_another_chapter(self):
        def provider(runtime, **kwargs):
            if kwargs["schema_name"] == "deepread_outline_v2":
                return {"selectedNewsIds": [f"news-{n}" for n in range(4)], "chapters": [
                    {"title": "任务独立报道", "angle": "只写这项任务", "newsIds": [f"news-{n}"]} for n in range(4)]}
            return {"headline": "虚构标题", "lead": "虚构导语", "chapters": {"chapter-1": {
                "blocks": [{"type": "paragraph", "text": "报道中出现了新的虚构来源，不能进入生产数据。" * 3,
                            "newsIds": ["news-5"], "sources": ["https://forged.example"]}]}}}
        report = build_daily_deepread([self.item(n) for n in range(8)],
                                      {**self.config, "deepread_core_events": 4}, self.now,
                                      {"provider": "fixture"}, provider)
        self.assertNotEqual(report["generationStatus"], "ok")
        self.assertNotIn("forged.example", json.dumps(report))
        self.assertEqual(report["eventCount"], 4)

    def test_failed_full_prose_request_recovers_valid_chapter_independently(self):
        prose_attempts = []
        def provider(runtime, **kwargs):
            if kwargs["schema_name"] == "deepread_outline_v2":
                return {"selectedNewsIds": [f"news-{n}" for n in range(4)], "chapters": [
                    {"title": f"第{n}项任务的进展", "angle": "核对这项任务的新结果", "newsIds": [f"news-{n}"]}
                    for n in range(4)]}
            if kwargs["schema_name"] == "deepread_prose_v2":
                prose_attempts.append(kwargs)
                return {"headline": "坏", "lead": "坏", "chapters": {}}
            if kwargs["schema_name"] == "deepread_chapter_v2" and kwargs["input_text"].find('"chapter-1"') >= 0:
                return {"blocks": [{"type": "paragraph", "text": "第一项任务今天完成了关键试验，并公布下一次测试所需的数据范围。",
                                    "newsIds": ["news-0"]}]}
            return {"blocks": [{"type": "paragraph", "text": "未证实的占位文本", "newsIds": ["not-a-real-id"]}]}
        report = build_daily_deepread([self.item(n) for n in range(4)], self.config, self.now,
                                      {"provider": "fixture"}, provider)
        self.assertEqual(len(prose_attempts), 2)
        self.assertEqual(report["generationStatus"], "partial")
        self.assertIn("第一项任务今天完成了关键试验", report["chapters"][0]["blocks"][0]["text"])
        self.assertEqual(report["chapters"][1]["blocks"][0]["text"], report["events"][1]["excerpt"])
        self.assertNotIn("not-a-real-id", json.dumps(report))

    def test_format_example_copied_as_article_is_rejected(self):
        def provider(runtime, **kwargs):
            if kwargs["schema_name"] == "deepread_outline_v2":
                return {"selectedNewsIds": [f"news-{n}" for n in range(4)], "chapters": [
                    {"title": f"第{n}项项目进展", "angle": "追踪这一项目的具体进展", "newsIds": [f"news-{n}"]}
                    for n in range(4)]}
            return {**kwargs["example"], "lead": "今天这几件公开事件分别披露了新的任务进展，报道按明确的项目边界组织，不暗示事件之间存在已证实的因果关系。"}
        report = build_daily_deepread([self.item(n) for n in range(8)],
                                      {**self.config, "deepread_core_events": 4}, self.now,
                                      {"provider": "fixture"}, provider)
        self.assertNotEqual(report["generationStatus"], "ok")
        self.assertNotIn("根据本条报道交代今天的具体行动", json.dumps(report, ensure_ascii=False))

    def test_under_four_eligible_events_stays_short_without_model_request(self):
        def unexpected(*args, **kwargs):
            self.fail("The writer should not invent missing core events")
        report = build_daily_deepread([self.item(0), self.item(1), self.item(2)], self.config, self.now,
                                      {"provider": "fixture"}, unexpected)
        self.assertEqual(report["eventCount"], 3)
        self.assertEqual(report["generationStatus"], "insufficient")

    def test_deepread_filters_political_media_access_even_if_misclassified(self):
        political = self.item(99, category="军事动态", score=100,
                              originalTitle="White House bars CNN from travelling with Trump on Air Force One",
                              title="白宫拒绝 CNN 记者随行采访",
                              summary="白宫公布总统出行安排并调整媒体准入，拒绝CNN记者随行采访，其他媒体就白宫决定发表意见。")
        technical = self.item(1, category="军事动态",
                              originalTitle="Dutch ministry briefs parliament on ASWF frigate trials",
                              title="荷兰国防部向议会通报 ASWF 护卫舰试验",
                              summary="荷兰国防部向议会通报护卫舰项目试验进展及时间安排。")
        inputs = []
        def provider(runtime, **kwargs):
            inputs.append(kwargs["input_text"])
            return None
        report = build_daily_deepread([self.item(n) for n in (0, 2, 3, 4)] + [technical, political],
                                      self.config, self.now, {"provider": "fixture"}, provider)
        self.assertEqual(report["candidateCount"], 5)
        self.assertNotIn("news-99", [x["newsId"] for x in report["events"]])
        self.assertIn("news-1", [x["newsId"] for x in report["events"]])
        self.assertNotIn("White House", " ".join(inputs))

    def test_conflict_reporting_stays_out_of_deepread_while_technical_defense_remains(self):
        conflict = self.item(88, category="局部冲突", score=100,
                             title="两国互施空袭造成多人死亡", originalTitle="Countries exchange deadly strikes",
                             summary="两国在边境地区互施空袭，已有多人死亡，相关冲突仍在持续。")
        technical = self.item(2, category="军事动态", score=95,
                              title="护卫舰试验公布雷达测试结果", originalTitle="Frigate radar trials report results")
        report = build_daily_deepread([conflict, technical] + [self.item(n) for n in (0, 1, 3, 4)],
                                      self.config, self.now)
        self.assertNotIn("news-88", {entry["newsId"] for entry in report["events"]})
        self.assertIn("news-2", {entry["newsId"] for entry in report["events"]})

    def test_misclassified_regulatory_bills_are_excluded(self):
        items = [self.item(n) for n in range(5)]
        items += [self.item(81, score=100, category="前沿技术", title="参议院通过人工智能监管法案",
                            originalTitle="Senate passes new AI safety bill"),
                  self.item(82, score=99, category="AI", title="监管机构通过人工智能安全法",
                            originalTitle="Regulator adopts new AI safety law")]
        report = build_daily_deepread(items, self.config, self.now)
        self.assertEqual(report["candidateCount"], 5)
        self.assertFalse({"news-81", "news-82"} & {entry["newsId"] for entry in report["events"]})

    def test_parliamentary_ai_inquiry_is_excluded_even_when_tagged_ai(self):
        inquiry = self.item(81, score=100, category="AI",
                            title="澳大利亚传唤两家AI公司CEO出席人工智能调查",
                            originalTitle="Australia summons AI CEOs to appear at AI inquiry",
                            summary="澳大利亚要求公司负责人出席参议院人工智能调查，公开听证会将于周四举行。")
        lab = self.item(82, category="AI", score=99,
                        title="研究团队调查AI代理的访问权限",
                        originalTitle="Researchers investigate AI agent access in lab trials",
                        summary="实验团队开展安全测试，测量AI代理访问权限并公布初步结果。")
        report = build_daily_deepread([inquiry, lab] + [self.item(n) for n in range(4)],
                                      self.config, self.now)
        self.assertNotIn("news-81", {entry["newsId"] for entry in report["events"]})
        self.assertIn("news-82", {entry["newsId"] for entry in report["events"]})
        from deepread_editorial_signals import is_political_policy
        self.assertFalse(is_political_policy({
            "category": "AI", "originalTitle": "Researchers investigate AI agent failures",
            "summary": "Researchers traced government website access, and a company inquiry into the software failure continues."}))

    def test_misclassified_diplomatic_meeting_stays_out_of_deepread(self):
        summit = self.item(81, category="AI", score=100,
                           title="习近平与特朗普正式会晤未公开提及台湾",
                           originalTitle="No public mentions of Taiwan at official Xi and Trump meeting",
                           summary="在习近平与特朗普的高调会晤中，双方均未公开提及台湾。")
        lab = self.item(82, category="AI", score=99,
                        title="研究团队召开机器人控制技术会议",
                        originalTitle="Researchers meet for a robotics control workshop",
                        summary="研究团队召开机器人控制技术会议，随后公布本轮实验的测量结果和后续测试安排。")
        report = build_daily_deepread([summit, lab] + [self.item(n) for n in range(4)],
                                      self.config, self.now)
        self.assertNotIn("news-81", {event["newsId"] for event in report["events"]})
        self.assertIn("news-82", {event["newsId"] for event in report["events"]})

    def test_misclassified_calls_for_war_stay_out_of_deepread(self):
        war = self.item(83, category="军事动态", score=100,
                        title="以色列部长呼吁在约旦河西岸开战",
                        originalTitle="Israeli minister urges war in the West Bank",
                        summary="部长呼吁开战，引发对地区战事进一步扩大的担忧。")
        technical = self.item(84, category="军事动态", score=99,
                              title="军方完成反无人机装备测试",
                              originalTitle="Military completes counter drone equipment trial",
                              summary="军方完成本轮反无人机设备测试，并公开雷达探测和拦截性能数据以及后续安排。")
        report = build_daily_deepread([war, technical] + [self.item(n) for n in range(4)],
                                      self.config, self.now)
        from deepread_editorial_signals import is_political_policy
        self.assertTrue(is_political_policy(war))
        self.assertFalse(is_political_policy(technical))
        self.assertNotIn("news-83", {event["newsId"] for event in report["events"]})
        self.assertIn("news-84", {event["newsId"] for event in report["events"]})

    def test_misclassified_policy_actions_in_titles_or_leads_are_excluded(self):
        policy_stories = [
            self.item(81, score=100, category="AI", title="政府发布人工智能使用新政策",
                      originalTitle="Government announces new AI use policy"),
            self.item(82, score=99, category="前沿技术", title="美国实施芯片出口管制",
                      originalTitle="US imposes new chip export controls"),
            self.item(83, score=98, category="AI", title="人工智能产业动态",
                      originalTitle="AI industry update", summary="政府发布新的人工智能使用政策，并规定企业的准入要求。后续实施细则待公布。"),
        ]
        technical = self.item(84, title="NASA完成引擎热试验", originalTitle="NASA tests an engine",
                              summary="NASA完成本次引擎热试验并公布测量结果。报道还提及相关政策背景。")
        algorithm = self.item(85, title="研究团队改进政策梯度算法",
                              originalTitle="Researchers improve policy gradient training",
                              summary="研究团队改进强化学习政策梯度算法，并发布本次性能试验结果。")
        report = build_daily_deepread([self.item(n) for n in range(3)] + policy_stories + [technical, algorithm],
                                      self.config, self.now)
        self.assertEqual(report["candidateCount"], 5)
        self.assertIn("news-84", {event["newsId"] for event in report["events"]})
        self.assertIn("news-85", {event["newsId"] for event in report["events"]})
        self.assertFalse({"news-81", "news-82", "news-83"} &
                         {event["newsId"] for event in report["events"]})
        from deepread_editorial_signals import is_political_policy
        for headline in ("New policy-gradient algorithm improves robotic control",
                         "Policy optimization for reinforcement learning"):
            with self.subTest(headline=headline):
                self.assertFalse(is_political_policy({"category": "AI", "originalTitle": headline,
                                                      "summary": "Researchers evaluate a control algorithm."}))

    def test_cached_caption_is_removed_from_deepread_material_and_prose(self):
        summary = ("卡纳维拉尔角太空军基地将部署反无人机激光，主要用于保护关键发射设施。"
                   "报道配图显示，2026年5月29日猎鹰9号升空，"
                   "照片由格温·库尔岑拍摄。部署时间尚未披露。")
        evidence = ("Cape Canaveral will receive lasers to stop drones.\n\n"
                    "A SpaceX Falcon 9 rocket launches from Cape Canaveral. Space Force photo by Gwen Kurzen.")
        inputs = []
        def provider(runtime, **kwargs):
            inputs.append(kwargs["input_text"])
            return None
        report = build_daily_deepread([self.item(n) for n in (1, 2, 3, 4)]
                                      + [self.item(0, summary=summary, evidenceText=evidence)],
                                      self.config, self.now, {"provider": "fixture"}, provider)
        public = json.dumps(report, ensure_ascii=False)
        self.assertIn("基地将部署反无人机激光", public)
        self.assertNotIn("猎鹰9", public)
        self.assertNotIn("格温", public)
        self.assertNotIn("Falcon 9", " ".join(inputs))

    def test_delta_score_only_marks_verified_same_event_stage_change(self):
        previous = {"editionDate": "2026-09-25", "newsId": "old-trial",
                    "title": "NASA公布本次试验计划", "source": "NASA",
                    "originalTitle": "NASA plans a new trial", "summaryLead": "NASA公布试验安排及准备步骤。"}
        registry = {"items": [{"eventId": "evt-0", "timeline": [previous]}]}
        completed = self.item(0, title="NASA完成本次试验", originalTitle="NASA completes the trial")
        report = build_daily_deepread([completed], self.config, self.now, event_registry=registry)
        self.assertEqual(report["events"][0]["deltaScore"], 2)

        cancelled = self.item(0, title="NASA取消原定计划的试验", originalTitle="NASA cancels the planned trial")
        report = build_daily_deepread([cancelled], self.config, self.now, event_registry=registry)
        self.assertEqual(report["events"][0]["deltaScore"], 3)

        reprint = self.item(0, title="NASA公布本次试验计划", originalTitle="NASA plans a new trial")
        report = build_daily_deepread([reprint], self.config, self.now, event_registry=registry)
        self.assertEqual(report["events"][0]["deltaScore"], 0)

        completed_before = {"items": [{"eventId": "evt-0", "timeline": [{
            **previous, "title": "NASA按计划完成卫星发射任务",
            "originalTitle": "NASA completes satellite launch as planned",
            "summaryLead": "NASA按计划完成了卫星发射任务。"}]}]}
        reprint = self.item(0, title="NASA完成卫星发射任务", originalTitle="NASA completes satellite launch")
        report = build_daily_deepread([reprint], self.config, self.now, event_registry=completed_before)
        self.assertEqual(report["events"][0]["deltaScore"], 0)

        future = self.item(0, title="NASA按计划将于明日发射卫星", originalTitle="NASA to launch tomorrow as planned")
        report = build_daily_deepread([future], self.config, self.now,
                                      event_registry={"items": [{"eventId": "evt-0", "timeline": [
                                          {**previous, "title": "NASA公布卫星发射计划"}]}]})
        self.assertEqual(report["events"][0]["deltaScore"], 0)
        for title in ("NASA将于明日如期发射卫星", "NASA明日按计划发射卫星", "NASA如期发射卫星（明日）"):
            with self.subTest(title=title):
                future = self.item(0, title=title, originalTitle="NASA to launch the satellite tomorrow")
                report = build_daily_deepread([future], self.config, self.now,
                                              event_registry={"items": [{"eventId": "evt-0", "timeline": [
                                                  {**previous, "title": "NASA公布卫星发射计划"}]}]})
                self.assertEqual(report["events"][0]["deltaScore"], 0)

        different = self.item(0, eventId="evt-unrelated", title="NASA完成本次试验")
        report = build_daily_deepread([different], self.config, self.now, event_registry=registry)
        self.assertEqual(report["events"][0]["deltaScore"], 0)

    def test_same_day_completed_story_survives_same_event_deduplication(self):
        planned = self.item(0, score=88, title="NASA计划本次试验", originalTitle="NASA plans the trial",
                            evidenceText="NASA described the preparation and schedule for this trial. " * 5,
                            publishedAt=(self.now - timedelta(hours=3)).isoformat())
        completed = self.item(20, eventId="evt-0", score=88, title="NASA完成本次试验",
                              originalTitle="NASA completes the trial",
                              publishedAt=(self.now - timedelta(hours=1)).isoformat())
        registry = {"items": [{"eventId": "evt-0", "timeline": [{
            "editionDate": "2026-09-25", "newsId": "old-trial", "title": "NASA计划本次试验",
            "originalTitle": "NASA plans the trial", "summaryLead": "NASA公布本项试验准备安排。",
        }]}]}
        report = build_daily_deepread([planned, completed], self.config, self.now,
                                      event_registry=registry)
        self.assertEqual(report["eventCount"], 1)
        self.assertEqual(report["events"][0]["newsId"], "news-20")
        self.assertEqual(report["events"][0]["deltaScore"], 2)

    def test_same_day_plan_source_does_not_upgrade_result_evidence_level(self):
        planned = self.item(0, eventId="evt-same", score=80, title="NASA计划火箭发射",
                            originalTitle="NASA plans rocket launch")
        result = self.item(20, eventId="evt-same", score=90, title="NASA公布火箭发射数据",
                           originalTitle="NASA releases launch data")
        report = build_daily_deepread([planned, result], self.config, self.now)
        event = report["events"][0]
        self.assertEqual(event["newsId"], "news-20")
        self.assertEqual(event["evidenceLevel"], "single")
        self.assertEqual(len(event["sources"]), 1)

    def test_same_event_opposing_reports_are_not_counted_as_corroboration(self):
        success = self.item(0, eventId="evt-same", score=90,
                            title="NASA试验取得成功", originalTitle="NASA trial succeeds")
        failure = self.item(20, eventId="evt-same", score=80,
                            title="NASA试验出现故障", originalTitle="NASA trial fails")
        report = build_daily_deepread([success, failure], self.config, self.now)
        event = report["events"][0]
        self.assertEqual(event["newsId"], "news-0")
        self.assertEqual(event["evidenceLevel"], "single")
        self.assertEqual(len(event["sources"]), 1)

    def test_equally_important_delta_and_better_sources_enter_core_selection(self):
        items = [self.item(n, category="AI", score=80) for n in range(6)]
        items[0]["score"] = 95
        items[3].update(title="NASA完成本次试验", originalTitle="NASA completes the trial")
        items[4]["sources"] = [
            {"name": "A", "url": "https://a.example/1", "evidenceGroup": "outlet:a"},
            {"name": "B", "url": "https://b.example/2", "evidenceGroup": "outlet:b"},
        ]
        items[5].update(source="NASA", url="https://nasa.gov/news/1", sources=[
            {"name": "NASA", "url": "https://nasa.gov/news/1", "evidenceGroup": "official:nasa"}])
        registry = {"items": [{"eventId": "evt-3", "timeline": [{
            "editionDate": "2026-09-25", "newsId": "old-trial", "title": "NASA计划本次试验", "source": "NASA",
            "originalTitle": "NASA plans the trial", "summaryLead": "NASA公布项目下一次试验安排。",
        }]}]}
        report = build_daily_deepread(items, self.config, self.now, event_registry=registry)
        ids = {entry["newsId"] for entry in report["events"]}
        self.assertEqual(report["candidateCount"], 6)
        self.assertTrue({"news-0", "news-3", "news-4", "news-5"} <= ids)
        self.assertEqual(report["eventCount"], 5)

    def test_source_bonus_does_not_replace_a_materially_more_important_story(self):
        scores = (95, 94, 93, 92, 87, 79)
        items = [self.item(n, category="AI", score=score) for n, score in enumerate(scores)]
        items[5].update(source="NASA", url="https://nasa.gov/news/5", sources=[
            {"name": "NASA", "url": "https://nasa.gov/news/5", "evidenceGroup": "official:nasa"}])
        report = build_daily_deepread(items, self.config, self.now)
        ids = {entry["newsId"] for entry in report["events"]}
        self.assertIn("news-4", ids)
        self.assertNotIn("news-5", ids)

    def test_technical_diversity_does_not_displace_higher_impact_core_story_before_pool_cap(self):
        items = [self.item(n, score=95-n, category="其他进展", source="Publisher 0") for n in range(5)]
        items.extend(self.item(n, score=21, category=("AI", "无人系统", "前沿技术")[n % 3])
                     for n in range(5, 13))
        report = build_daily_deepread(items, self.config, self.now)
        self.assertEqual(report["candidateCount"], 12)
        self.assertEqual({event["newsId"] for event in report["events"]},
                         {f"news-{n}" for n in range(5)})

    def test_delta_and_primary_source_can_enter_bounded_pool_from_near_tie(self):
        items = [self.item(n, score=80, category="航空航天") for n in range(12)]
        changed = self.item(12, score=79, category="航空航天", title="NASA取消原定卫星试验",
                            originalTitle="NASA cancels planned satellite trial", source="NASA",
                            url="https://nasa.gov/news/12",
                            sources=[{"name": "NASA", "url": "https://nasa.gov/news/12"}])
        registry = {"items": [{"eventId": "evt-12", "timeline": [{
            "editionDate": "2026-09-25", "newsId": "old-12", "title": "NASA计划卫星试验",
            "originalTitle": "NASA plans a satellite trial", "summaryLead": "NASA公布本项目卫星试验计划。"}]}]}
        report = build_daily_deepread([*items, changed], self.config, self.now, event_registry=registry)
        self.assertEqual(report["candidateCount"], 12)
        self.assertIn("news-12", {event["newsId"] for event in report["events"]})
        self.assertEqual(next(event["deltaScore"] for event in report["events"] if event["newsId"] == "news-12"), 3)

    def test_outline_cannot_swap_out_prioritized_core_story(self):
        items = [self.item(n, category="AI", score=80) for n in range(6)]
        items[5].update(source="NASA", url="https://nasa.gov/news/5", sources=[
            {"name": "NASA", "url": "https://nasa.gov/news/5", "evidenceGroup": "official:nasa"}])
        def provider(runtime, **kwargs):
            if kwargs["schema_name"] == "deepread_outline_v2":
                return {"selectedNewsIds": [f"news-{n}" for n in range(5)], "chapters": [
                    {"title": f"第{n}条试验的结果", "angle": "核对本项试验披露的结果", "newsIds": [f"news-{n}"]}
                    for n in range(5)]}
            return None
        report = build_daily_deepread(items, self.config, self.now,
                                      {"provider": "fixture"}, provider)
        self.assertIn("news-5", {entry["newsId"] for entry in report["events"]})
        self.assertNotIn("news-4", {entry["newsId"] for entry in report["events"]})

    def test_independent_cross_category_ai_agent_reports_form_comparison_chapter(self):
        items = [self.item(n, score=95-n) for n in range(5)]
        items[0].update(title="OpenAI公布AI智能体安全测试", originalTitle="OpenAI tests AI agent safety controls",
                        summary="OpenAI公布AI智能体安全测试，描述了权限控制如何约束自动访问外部网站。")
        items[1].update(title="电商平台测试AI智能体购物", originalTitle="Retailer trials AI agent shopping",
                        category="前沿技术", summary="电商平台测试AI智能体购物，在结算环节加入确认与支付授权。")
        calls = []
        def provider(runtime, **kwargs):
            calls.append(kwargs)
            if kwargs["schema_name"] == "deepread_outline_v2":
                return {"selectedNewsIds": [f"news-{n}" for n in range(5)], "chapters": [
                    {"title": "智能体从能力走向应用时的边界", "angle": "安全权限与支付授权各解决什么问题？",
                     "newsIds": ["news-0", "news-1"], "kind": "comparison", "comparisonKey": "ai-agent"},
                    *[{"title": f"第{n}项任务进展", "angle": "核对任务的具体进展",
                       "newsIds": [f"news-{n}"], "kind": "event", "comparisonKey": ""} for n in (2, 3, 4)],
                ]}
            if kwargs["schema_name"] == "deepread_prose_v2":
                return {"headline": "智能体应用中的具体边界与其他技术进展",
                        "lead": "今天的两项智能体报道分别披露了访问权限与支付确认机制，其余技术报道各自记录具体进展。",
                        "observations": [
                            {"text": "两项智能体实践都明确设置权限边界，但约束分别落在访问与结算环节。",
                             "newsIds": ["news-0", "news-1"], "supports": [
                                 {"newsId": "news-0", "supportQuote": "权限控制如何约束自动访问外部网站"},
                                 {"newsId": "news-1", "supportQuote": "在结算环节加入确认与支付授权"}]},
                            {"text": "结算环节的测试披露了支付授权与确认步骤，重点是支付前的用户确认。",
                             "newsIds": ["news-1"], "supports": [
                                 {"newsId": "news-1", "supportQuote": "在结算环节加入确认与支付授权"}]},
                        ],
                        "chapters": {
                            "chapter-1": {"blocks": [
                                {"type": "paragraph", "text": "OpenAI披露智能体访问外部网站时采用的安全测试及权限控制。",
                                 "newsIds": ["news-0"]},
                                {"type": "paragraph", "text": "电商平台在智能体结算链路引入支付授权与确认步骤，测试范围目前仅限部分用户。",
                                 "newsIds": ["news-1"]},
                                {"type": "comparison", "text": "两项独立报道各自说明智能体进入真实流程时的边界管理，一项侧重网站访问，另一项侧重支付确认。",
                                 "newsIds": ["news-0", "news-1"]},
                            ]},
                            **{f"chapter-{n}": {"blocks": [
                                {"type": "paragraph", "text": f"第{n}项任务公布了已完成的测试步骤，并说明后续安排和实施范围。",
                                 "newsIds": [f"news-{n}"]}]}
                                for n in (2, 3, 4)},
                        }}
            return None
        report = build_daily_deepread(items, self.config, self.now,
                                      {"provider": "fixture"}, provider)
        self.assertEqual(report["generationStatus"], "ok")
        self.assertEqual(len(report["chapters"]), 4)
        self.assertEqual(report["chapters"][0]["kind"], "comparison")
        self.assertEqual(report["chapters"][0]["comparisonKey"], "ai-agent")
        self.assertIn("不代表事件之间存在因果关系", report["chapters"][0]["comparisonNote"])
        self.assertTrue(any(block["type"] == "comparison" for block in report["chapters"][0]["blocks"]))
        self.assertEqual(len(report["observations"]), 2)
        outline_input = next(json.loads(call["input_text"]) for call in calls if call["schema_name"] == "deepread_outline_v2")
        self.assertIn("ai-agent", outline_input["candidates"][0]["comparisonKeys"])

    def test_rejected_outline_keeps_source_grounded_comparison_of_independent_actions(self):
        items = [self.item(n) for n in range(5)]
        items[0].update(title="OpenAI暂停最新模型训练", originalTitle="OpenAI pauses training after agents probed sites",
                        summary="OpenAI因AI代理意外访问网站暂停了最新模型训练，具体影响范围尚未公布。")
        items[1].update(title="电商平台测试AI智能体购物授权", originalTitle="Retailer trials AI agent payment authorization",
                        summary="电商平台测试AI代理支付前的用户授权，并披露了当前的结算测试范围。")
        report = build_daily_deepread(items, self.config, self.now,
                                      {"provider": "fixture"}, lambda *_args, **_kwargs: None)
        chapters = [chapter for chapter in report["chapters"] if chapter["kind"] == "comparison"]
        self.assertEqual(report["eventCount"], 5)
        self.assertEqual(len(report["chapters"]), 4)
        self.assertEqual(len(chapters), 1)
        self.assertEqual(set(chapters[0]["newsIds"]), {"news-0", "news-1"})
        self.assertEqual(chapters[0]["comparisonNote"], "并列比较不代表事件之间存在因果关系。")
        self.assertEqual([block["type"] for block in chapters[0]["blocks"]].count("comparison"), 1)
        self.assertIn("不代表事件之间存在因果关系", chapters[0]["blocks"][-1]["text"])

    def test_valid_single_event_outline_still_groups_supported_independent_topic(self):
        items = [self.item(n) for n in range(5)]
        items[0].update(title="OpenAI暂停AI代理训练", originalTitle="OpenAI pauses AI agent model training",
                        summary="OpenAI因AI代理异常行为暂停模型训练，具体调查结果尚未公布。")
        items[2].update(title="安全团队调查AI代理权限", originalTitle="Security lab investigates AI agent access",
                        summary="安全团队调查另一项AI代理权限事件，公开了当前审查范围。")
        def provider(runtime, **kwargs):
            if kwargs["schema_name"] == "deepread_outline_v2":
                return {"selectedNewsIds": [f"news-{n}" for n in range(5)], "chapters": [
                    {"title": f"第{n}项独立进展", "angle": "核对今天披露的具体动作",
                     "newsIds": [f"news-{n}"], "kind": "event", "comparisonKey": ""}
                    for n in range(5)]}
            outline = json.loads(kwargs["input_text"])["outline"]
            chapters = {}
            for chapter in outline:
                blocks = [{"type": "paragraph", "text": "这项报道披露了当期可核对的具体动作与当前公开的事实范围。",
                           "newsIds": [news_id]} for news_id in chapter["newsIds"]]
                if chapter["kind"] == "comparison":
                    blocks.append({"type": "comparison", "text": (
                        "两项独立报道分别披露代理训练暂停与权限审查，并列比较不代表事件之间存在因果关系。"),
                        "newsIds": chapter["newsIds"]})
                chapters[chapter["id"]] = {"blocks": blocks}
            return {"headline": "AI代理安全的两项进展与其他独立报道",
                    "lead": "今天两项独立事件分别涉及AI代理训练和权限审查，其余新闻对应不同技术项目的公开进展。",
                    "chapters": chapters,
                    "observations": [
                        {"text": "第一项代理报道只确认暂停训练，调查结果仍待后续公开材料。",
                         "newsIds": ["news-0"], "supports": [
                             {"newsId": "news-0", "supportQuote": "具体调查结果尚未公布"}]},
                        {"text": "第二项审查已经公开当前范围，进一步结论仍需核对新的证据。",
                         "newsIds": ["news-2"], "supports": [
                             {"newsId": "news-2", "supportQuote": "公开了当前审查范围"}]},
                    ]}
        report = build_daily_deepread(items, self.config, self.now,
                                      {"provider": "fixture"}, provider)
        self.assertEqual(report["eventCount"], 5)
        self.assertEqual(len(report["chapters"]), 4)
        chapter = next(c for c in report["chapters"] if c["kind"] == "comparison")
        self.assertEqual(set(chapter["newsIds"]), {"news-0", "news-2"})
        self.assertEqual(chapter["comparisonNote"], "并列比较不代表事件之间存在因果关系。")
        self.assertEqual([b["type"] for b in chapter["blocks"]].count("comparison"), 1)

    def test_two_headlines_for_the_same_pause_are_not_forced_into_a_comparison(self):
        items = [self.item(n) for n in range(5)]
        items[0].update(title="OpenAI因AI代理探查网站暂停最新模型训练",
                        originalTitle="OpenAI pauses training of latest models after agents probed sites",
                        summary="OpenAI暂停最新模型训练，原因涉及AI代理意外访问网站。")
        items[1].update(title="OpenAI因AI代理报告暂停最新模型训练",
                        originalTitle="OpenAI halts training of latest models as reports of AI agents mount",
                        summary="OpenAI暂停最新模型训练，正在调查AI代理的异常行为。")
        report = build_daily_deepread(items, self.config, self.now)
        self.assertEqual(report["eventCount"], 5)
        self.assertTrue(all(chapter["kind"] == "event" for chapter in report["chapters"]))

    def test_failed_prose_keeps_sourced_comparison_and_explicit_limit_observations(self):
        items = [self.item(n) for n in range(5)]
        items[0].update(title="OpenAI暂停AI代理训练", originalTitle="OpenAI pauses AI agent training",
                        summary="OpenAI因AI代理异常行为暂停训练，具体调查范围尚未公布。")
        items[1].update(title="平台测试AI代理购物", originalTitle="Retailer trials AI agent shopping",
                        summary="平台测试AI代理购物授权，实际应用范围尚未披露。")
        def provider(runtime, **kwargs):
            if kwargs["schema_name"] == "deepread_outline_v2":
                return {"selectedNewsIds": [f"news-{n}" for n in range(5)], "chapters": [
                    {"title": f"第{n}项独立进展", "angle": "核对本项任务披露的动作",
                     "newsIds": [f"news-{n}"], "kind": "event", "comparisonKey": ""}
                    for n in range(5)]}
            return None
        report = build_daily_deepread(items, self.config, self.now,
                                      {"provider": "fixture"}, provider)
        self.assertEqual(report["eventCount"], 5)
        self.assertEqual(len(report["chapters"]), 4)
        self.assertEqual(len(report["observations"]), 2)
        self.assertTrue(all(o["supports"][0]["supportQuote"] in items[int(o["newsIds"][0][-1])]["summary"]
                            for o in report["observations"]))

    def test_specific_comparison_subjects_extend_beyond_initial_five(self):
        from deepread_editorial_signals import comparison_keys
        topics = [
            ({"title": "自动驾驶出租车公布安全测试", "originalTitle": "Company A robotaxi safety tests"},
             {"title": "另一家企业测试机器人出租车", "originalTitle": "Company B robotaxi trials"}),
            ({"title": "核聚变装置公布实验结果", "originalTitle": "Team A fusion experiment"},
             {"title": "另一项核聚变实验给出测试数据", "originalTitle": "Team B fusion trial"}),
            ({"title": "钙钛矿电池公布效率测试", "originalTitle": "Team A perovskite cell efficiency"},
             {"title": "另一家机构测试钙钛矿器件", "originalTitle": "Team B perovskite device trial"}),
        ]
        for first, second in topics:
            with self.subTest(topic=first["originalTitle"]):
                self.assertTrue(comparison_keys(first) & comparison_keys(second))
        self.assertFalse(comparison_keys({"title": "技术项目测试", "originalTitle": "Company reports technology trial"})
                         & comparison_keys({"title": "另一项技术试验", "originalTitle": "Other company technology test"}))
        self.assertFalse(comparison_keys({"title": "第一个项目", "originalTitle": "Team A reports technical progress"})
                         & comparison_keys({"title": "另一个项目", "originalTitle": "Team B reports technical progress"}))
        generic_headlines = [
            ("Military rocket test completes", "Military hospital device trial begins"),
            ("Hardware sensor reaches orbit", "Hardware chip test concludes"),
            ("Drones targeted by base lasers", "Drones spot sharks in coastal waters"),
        ]
        for first, second in generic_headlines:
            with self.subTest(generic=first):
                self.assertFalse(comparison_keys({"originalTitle": first})
                                 & comparison_keys({"originalTitle": second}))

    def test_generic_subject_does_not_justify_comparison(self):
        items = [self.item(n, category="前沿技术", score=95-n,
                           originalTitle=f"Government Trials project {n} reports technical progress")
                 for n in range(5)]
        def provider(runtime, **kwargs):
            if kwargs["schema_name"] == "deepread_outline_v2":
                return {"selectedNewsIds": [f"news-{n}" for n in range(5)], "chapters": [
                    {"title": "政府科技项目进展对比", "angle": "这些项目为何同步调整？",
                     "newsIds": ["news-0", "news-1"], "kind": "comparison", "comparisonKey": "technology"},
                    *[{"title": f"第{n}项任务进展", "angle": "核对独立任务进展", "newsIds": [f"news-{n}"]}
                      for n in (2, 3, 4)],
                ]}
            return None
        report = build_daily_deepread(items, self.config, self.now,
                                      {"provider": "fixture"}, provider)
        self.assertEqual(len(report["chapters"]), 5)
        self.assertTrue(all(len(chapter["newsIds"]) == 1 for chapter in report["chapters"]))
        self.assertNotIn("为何同步调整", json.dumps(report, ensure_ascii=False))

    def test_comparison_paragraph_cannot_claim_one_event_caused_another(self):
        items = [self.item(n, score=95-n, category="AI") for n in range(5)]
        for n in (0, 1):
            items[n].update(title=f"第{n}家企业发布AI智能体测试结果",
                            originalTitle=f"Company {n} tests AI agent safety controls",
                            summary=f"第{n}家企业公布AI智能体安全测试及权限控制方案。")
        def provider(runtime, **kwargs):
            if kwargs["schema_name"] == "deepread_outline_v2":
                return {"selectedNewsIds": [f"news-{n}" for n in range(5)], "chapters": [
                    {"title": "两家企业的智能体安全控制", "angle": "两家控制方法各解决什么问题？",
                     "newsIds": ["news-0", "news-1"], "kind": "comparison", "comparisonKey": "ai-agent"},
                    *[{"title": f"第{n}项任务进展", "angle": "核对本项任务进展", "newsIds": [f"news-{n}"]}
                      for n in (2, 3, 4)],
                ]}
            if kwargs["schema_name"] == "deepread_prose_v2":
                return {"headline": "智能体安全方案的不同路径",
                        "lead": "两家企业分别公布技术测试，比较仅限公开材料中的控制方式；其他三项任务的公开进展按项目独立记录。",
                        "chapters": {"chapter-1": {"blocks": [
                            {"type": "paragraph", "text": "第一家企业公布了智能体外部网站访问的控制方案及相应测试步骤。", "newsIds": ["news-0"]},
                            {"type": "paragraph", "text": "第二家企业公布了另一项智能体权限控制测试，并描述权限限制方法。", "newsIds": ["news-1"]},
                            {"type": "comparison", "text": "第一家企业的方案导致第二家企业转向权限控制，这两项报道构成直接因果关系。",
                             "newsIds": ["news-0", "news-1"]},
                        ]}, **{f"chapter-{n}": {"blocks": [{"type": "paragraph",
                             "text": f"第{n}项任务公布了已完成的试验步骤，以及后续安排和适用范围。",
                             "newsIds": [f"news-{n}"]}]} for n in (2, 3, 4)}}}
            return None
        report = build_daily_deepread(items, self.config, self.now,
                                      {"provider": "fixture"}, provider)
        self.assertEqual(report["chapters"][0]["kind"], "event")
        self.assertNotEqual(report["generationStatus"], "ok")
        self.assertNotIn("导致第二家", json.dumps(report, ensure_ascii=False))

    def test_comparison_prose_fails_when_any_block_implies_cross_event_causality(self):
        from deepread_editorial import _validated_blocks
        chapter = {"kind": "comparison", "newsIds": ["first", "second"]}
        individual = [
            {"type": "paragraph", "text": "第一家公司公布智能体安全测试的当前结果，以及外部网站的权限控制措施。", "newsIds": ["first"]},
            {"type": "paragraph", "text": "第二家公司公布智能体购物结算环节的支付授权，以及用户确认措施。", "newsIds": ["second"]},
        ]
        neutral = {"type": "comparison", "text": "两项独立报道对同一类智能体应用分别设置了不同的权限边界，需要分别核对。",
                   "newsIds": ["first", "second"]}
        for text, block_index in [
            ("第一家公司披露智能体测试后导致第二家公司改变权限设计方向，两个方案有直接的影响关系。", 0),
            ("第一家公司披露测试，因此第二家公司改变了智能体的权限设计和测试目标。", 2),
            ("第一家公司的发布推动第二家公司改变智能体产品设计，两项试验互相影响。", 2),
            ("第一家公司的发布是第二家公司调整产品设计的直接原因，且影响了后续试验。", 2),
            ("第一家公司的发布带动第二家公司调整产品方向，使其重新选择技术路线。", 2),
        ]:
            with self.subTest(text=text):
                blocks = [dict(block) for block in [*individual, neutral]]
                blocks[block_index]["text"] = text
                self.assertIsNone(_validated_blocks(chapter, {"blocks": blocks}, set(), set()))

    def test_unrecovered_comparison_is_split_into_independent_factual_chapters(self):
        items = [self.item(n) for n in range(5)]
        for n in (0, 1):
            items[n].update(title=f"第{n}家企业发布AI智能体试验", originalTitle=f"Company {n} trials AI agents")
        def provider(runtime, **kwargs):
            if kwargs["schema_name"] == "deepread_outline_v2":
                return {"selectedNewsIds": [f"news-{n}" for n in range(5)], "chapters": [
                    {"title": "智能体试验中的权限问题", "angle": "两家企业如何设置权限边界？",
                     "newsIds": ["news-0", "news-1"], "kind": "comparison", "comparisonKey": "ai-agent"},
                    *[{"title": f"第{n}项任务进展", "angle": "核对本项任务结果", "newsIds": [f"news-{n}"]}
                      for n in (2, 3, 4)],
                ]}
            return None
        report = build_daily_deepread(items, self.config, self.now,
                                      {"provider": "fixture"}, provider)
        self.assertEqual(report["eventCount"], 5)
        self.assertEqual(len(report["chapters"]), 5)
        self.assertTrue(all(chapter["kind"] == "event" and len(chapter["newsIds"]) == 1
                            for chapter in report["chapters"]))
        self.assertNotIn("并列比较", json.dumps(report, ensure_ascii=False))

    def test_unverified_trial_quotes_cannot_ground_global_safety_observations(self):
        from deepread_editorial import _validated_observations
        a, b = self.item(0), self.item(1)
        a.update(summary="该项目仅进行一次未经验证的安全试验，目前未披露正式部署结果。", _evidence="")
        b.update(summary="第二家团队只招募十名用户开展封闭测试，尚未公布其他地区的上线计划。", _evidence="")
        claims = [
            {"text": "所有正式部署均已证实安全，全球用户现在可以放心使用这一技术。", "newsIds": ["news-0"],
             "supports": [{"newsId": "news-0", "supportQuote": "仅进行一次未经验证的安全试验"}]},
            {"text": "全球业务已全面铺开，所有地区的用户已经获得完整商业服务。", "newsIds": ["news-1"],
             "supports": [{"newsId": "news-1", "supportQuote": "只招募十名用户开展封闭测试"}]},
        ]
        self.assertIsNone(_validated_observations(claims, [a, b], set()))
        claims[0]["text"] = "这次试验已经证明设备安全稳定，后续可以直接面向用户开放。"
        claims[1]["text"] = "这次封闭测试只是十名用户参与，还没有其他地区的上线计划。"
        self.assertIsNone(_validated_observations(claims, [a, b], set()))
        claims[0]["text"] = "试验已经获得监管部门批准，一千名患者在医院采用设备，收入达一千万欧元。"
        claims[1]["text"] = "十名用户的测试让医院部署扩大，并取得一千万欧元收入和新增患者。"
        self.assertIsNone(_validated_observations(claims, [a, b], set()))

    def test_cross_event_observation_cannot_claim_internal_review_drove_training_pause(self):
        from deepread_editorial import _validated_observations
        first = self.item(0, summary="OpenAI暂停最新模型训练，AI代理探查政府网站的事件仍在调查中。", _evidence="")
        second = self.item(1, summary="OpenAI内部审查发现Hugging Face事件后的更多安全报告。", _evidence="")
        claims = [
            {"text": "内部审查已牵动OpenAI的模型训练节奏，两项报道说明该联系。",
             "newsIds": ["news-0", "news-1"], "supports": [
                 {"newsId": "news-0", "supportQuote": "OpenAI暂停最新模型训练"},
                 {"newsId": "news-1", "supportQuote": "OpenAI内部审查发现Hugging Face事件后的更多安全报告"}]},
            {"text": "内部审查披露了更多安全报告，具体后续处理仍需进一步核对。",
             "newsIds": ["news-1"], "supports": [
                 {"newsId": "news-1", "supportQuote": "OpenAI内部审查发现Hugging Face事件后的更多安全报告"}]},
        ]
        self.assertIsNone(_validated_observations(claims, [first, second], set()))

    def test_tag_list_is_not_an_action_quote_for_observation(self):
        from deepread_editorial import _validated_observations
        first = self.item(0, summary="基地将部署反无人机激光，具体部署时间尚未公布。", _evidence="")
        second = self.item(1, summary="海军乘员完成培训，目前正准备部署无人机。",
                           _evidence="AKINCI, Royal Saudi Navy, UCAV")
        claims = [
            {"text": "两项无人系统都已经完成培训并进入实际部署准备。",
             "newsIds": ["news-0", "news-1"], "supports": [
                 {"newsId": "news-0", "supportQuote": "基地将部署反无人机激光"},
                 {"newsId": "news-1", "supportQuote": "AKINCI, Royal Saudi Navy, UCAV"}]},
            {"text": "海军乘员已经完成培训，实际部署进度仍待后续材料核对。",
             "newsIds": ["news-1"], "supports": [
                 {"newsId": "news-1", "supportQuote": "海军乘员完成培训，目前正准备部署无人机"}]},
        ]
        self.assertIsNone(_validated_observations(claims, [first, second], set()))

    def test_negated_source_cannot_support_claimed_completed_action(self):
        from deepread_editorial import _validated_observations
        first = self.item(0, summary="项目尚未进行正式发射，目前仍处于准备阶段。", _evidence="")
        second = self.item(1, summary="项目只有有限的模拟测试数据，目前尚未进行正式发射。", _evidence="")
        claims = [
            {"text": "首个项目已经完成正式发射，现在可以按实际任务阶段追踪。", "newsIds": ["news-0"],
             "supports": [{"newsId": "news-0", "supportQuote": "项目尚未进行正式发射"}]},
            {"text": "第二个项目已经完成正式发射，可据此评估其实际任务进展。", "newsIds": ["news-1"],
             "supports": [{"newsId": "news-1", "supportQuote": "项目只有有限的模拟测试数据，目前尚未进行正式发射"}]},
        ]
        self.assertIsNone(_validated_observations(claims, [first, second], set()))
        first["summary"] = "项目尚未进入量产阶段，目前仍在样机验证。"
        second["summary"] = "项目也尚未进入量产阶段，当前只有小规模测试。"
        claims[0]["text"] = "首个项目已经进入量产阶段，后续可以追踪实际产出进度。"
        claims[0]["supports"][0]["supportQuote"] = "项目尚未进入量产阶段"
        claims[1]["text"] = "第二个项目已经进入量产阶段，可以据此观察生产流程。"
        claims[1]["supports"][0]["supportQuote"] = "项目也尚未进入量产阶段"
        self.assertIsNone(_validated_observations(claims, [first, second], set()))

    def test_invalid_observation_quotes_and_ids_do_not_replace_valid_prose(self):
        items = [self.item(n) for n in range(5)]
        for corruption in ("quote", "unknown-id", "all-core", "one-only"):
            with self.subTest(corruption=corruption):
                observations = [
                    {"text": "第一项试验公布了实际结果，后续安排可按公开步骤继续追踪。", "newsIds": ["news-0"],
                     "supports": [{"newsId": "news-0", "supportQuote": "第0项航空试验公布本次任务结果"}]},
                    {"text": "第二项试验已有测试步骤，下一次行动仍待对应项目披露。", "newsIds": ["news-1"],
                     "supports": [{"newsId": "news-1", "supportQuote": "第1项航空试验公布本次任务结果"}]},
                ]
                if corruption == "quote":
                    observations[0]["supports"][0]["supportQuote"] = "不存在的虚构证据摘录"
                elif corruption == "unknown-id":
                    observations[0]["supports"][0]["newsId"] = "made-up"
                elif corruption == "all-core":
                    observations[0]["newsIds"] = [f"news-{n}" for n in range(5)]
                else:
                    observations.pop()

                def provider(runtime, **kwargs):
                    if kwargs["schema_name"] == "deepread_outline_v2":
                        return {"selectedNewsIds": [f"news-{n}" for n in range(5)], "chapters": [
                            {"title": f"第{n}项任务结果", "angle": "追踪本项任务披露的试验进度", "newsIds": [f"news-{n}"]}
                            for n in range(5)]}
                    return {"headline": "五项独立技术进展披露当前任务节点",
                            "lead": "今天五项独立技术报道分别披露已完成的任务步骤，可以按项目逐一核对公开证据与后续安排。",
                            "observations": observations,
                            "chapters": {f"chapter-{n+1}": {"blocks": [{"type": "paragraph",
                                "text": f"第{n}项试验公布了已完成的步骤和任务结果，报道同时列出后续安排。",
                                "newsIds": [f"news-{n}"]}]} for n in range(5)}}
                report = build_daily_deepread(items, self.config, self.now,
                                              {"provider": "fixture"}, provider)
                self.assertEqual(report["generationStatus"], "partial")
                self.assertEqual(report["observations"], [])
                self.assertIn("五项独立技术进展", report["headline"])
                self.assertEqual(report["eventCount"], 5)


if __name__ == "__main__":
    unittest.main()
