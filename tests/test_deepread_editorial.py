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

    def test_outline_may_select_four_and_splits_weakly_related_events(self):
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
                    "chapters": {chapter["id"]: {"blocks": [
                        {"type": "paragraph", "text": "该项目今天公布了已完成的动作和下一阶段安排，材料说明了任务边界。",
                         "newsIds": chapter["newsIds"]}
                    ]} for chapter in outline}}
        report = build_daily_deepread(items, self.config, self.now,
                                      {"provider": "fixture"}, provider)
        self.assertEqual(report["generationStatus"], "ok")
        self.assertEqual(report["eventCount"], 4)
        self.assertEqual(len(report["chapters"]), 4)
        self.assertTrue(all(len(chapter["newsIds"]) == 1 for chapter in report["chapters"]))

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


if __name__ == "__main__":
    unittest.main()
