import copy
import importlib.util
import json
import unittest
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("daily_deepread", ROOT / "scripts" / "daily_deepread.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class DailyDeepreadTests(unittest.TestCase):
    def setUp(self):
        # The edition is generated at 07:07 in Shanghai, not at calendar midnight.
        self.now = datetime(2026, 9, 20, 23, 7, tzinfo=timezone.utc)
        self.config = {
            "timezone": "Asia/Shanghai",
            "deepread_target_events": 12,
            "content_policy": json.loads((ROOT / "public/assets/news-policy.json").read_text()),
        }
        self.categories = ["AI", "航空航天", "无人系统", "前沿技术", "军事动态", "局部冲突"]
        self.runtime = {"provider": "test", "model": "offline-double"}

    def item(self, number, **changes):
        item = {
            "id": f"news-{number}",
            "eventId": f"evt-{number}",
            "title": f"实验团队发布第{number}项测试的公开结果",
            "originalTitle": f"Research team releases experiment {number} results",
            "summary": f"团队发布第{number}项实验的测试结果，公开材料介绍了测试过程，并说明这些结果仍需后续独立验证。报道没有给出规模化部署的时间表。",
            "category": self.categories[number % len(self.categories)],
            "source": f"机构{number % 5}",
            "url": f"https://publisher{number % 5}.example/news/{number}",
            "sources": [{"name": f"机构{number % 5}", "url": f"https://publisher{number % 5}.example/news/{number}", "domain": "not-public"}],
            "image": f"https://publisher{number % 5}.example/images/{number}.jpg",
            "publishedAt": (self.now - timedelta(hours=number % 20 + 1)).isoformat().replace("+00:00", "Z"),
            "score": 90 - number % 20,
            "historyContext": {"status": "new", "relatedStories": []},
        }
        item.update(changes)
        return item

    def events(self, article):
        return [event for section in article["sections"] for event in section["events"]]

    def model_response(self, selected):
        return {
            "editionDate": "2026-09-21",
            "headline": "每日深读：公开实验结果之后，仍待回答的工程问题",
            "introduction": "本期把近期公开的实验与项目进展放在一起阅读。各条报道提供的是不同场景下的阶段性材料，不能直接合并为一条行业趋势。下文先交代来源中已经记录的内容，再区分仍待验证的判断。" * 2,
            "sections": [{
                "id": "tests-and-evidence",
                "title": "从公开测试到可复核的判断",
                "overview": "这些事件都包含新公开的材料，但各自的测试对象和应用条件不同。将它们放在同一节，目的是比较证据披露的完整程度，并不意味着它们属于同一个事件，也不意味着报道之间存在因果关系。",
                "events": [{
                    "eventId": item["eventId"],
                    "newsId": item["id"],
                    "title": item["title"],
                    "summary": item["summary"],
                    "analysis": "如果后续研究能在独立条件下复现公开材料描述的表现，这条消息的意义才可能从单次测试延伸到更广的应用判断。现有摘要没有给出完整部署安排，因此对推广速度的判断仍应保持条件限制。",
                    "watchFor": "接下来应关注团队是否公开测试条件、完整数据以及独立复现实验的结果。",
                } for item in selected],
            }],
            "conclusion": "读完本期，更有价值的问题是哪些结果已经留下可复核的材料，哪些解释仍依赖后续证据。即使若干事件在时间上接近，也不能由此推断它们互相推动。后续将继续围绕公开测试、独立验证和具体部署条件追踪这些事件。",
        }

    def test_output_contract_has_twelve_distinct_events_and_canonical_citations(self):
        items = [self.item(number) for number in range(18)]
        items.append(self.item(50, eventId="evt-0", score=99))
        before = copy.deepcopy(items)
        article = MODULE.build_daily_deepread(items, self.config, self.now)
        self.assertEqual(set(article), {
            "schemaVersion", "generationRevision", "editionDate", "generatedAt", "headline", "introduction", "sections",
            "conclusion", "eventCount", "sourceCount", "generationStatus", "warnings",
        })
        self.assertEqual(article["schemaVersion"], 1)
        self.assertEqual(article["editionDate"], "2026-09-21")
        self.assertEqual(article["generatedAt"], "2026-09-20T23:07:00Z")
        self.assertEqual(article["generationStatus"], "fallback")
        events = self.events(article)
        self.assertEqual(article["eventCount"], 12)
        self.assertEqual(len({event["eventId"] for event in events}), 12)
        self.assertEqual(len({event["newsId"] for event in events}), 12)
        self.assertEqual(article["sourceCount"], len({source["url"] for event in events for source in event["sources"]}))
        for event in events:
            self.assertEqual(set(event), {
                "newsId", "eventId", "title", "summary", "analysis", "watchFor", "category",
                "publishedAt", "sources", "image", "imageSource",
            })
            self.assertTrue(event["sources"])
            self.assertIsInstance(event["watchFor"], str)
            self.assertTrue(all(set(source) == {"name", "url"} for source in event["sources"]))
        self.assertEqual(items, before)

    def test_rolling_window_keeps_previous_date_and_rejects_stale_future_and_unknown_dates(self):
        items = [
            self.item(0, publishedAt="2026-09-19T23:07:00Z"),
            self.item(1, publishedAt="2026-09-20T01:00:00Z"),
            self.item(2, publishedAt="2026-09-19T23:06:59Z"),
            self.item(3, publishedAt="2026-09-20T23:07:01Z"),
            self.item(4, publishedAt="not a date"),
            self.item(5, publishedAt="2026-09-20T22:00:00"),
        ]
        article = MODULE.build_daily_deepread(items, self.config, self.now)
        self.assertEqual({event["eventId"] for event in self.events(article)}, {"evt-0", "evt-1"})
        self.assertEqual(article["eventCount"], 2)
        self.assertEqual(article["generationStatus"], "insufficient")

    def test_edition_date_is_shanghai_even_when_config_uses_another_timezone(self):
        article = MODULE.build_daily_deepread([self.item(0)], {**self.config, "timezone": "UTC"}, self.now)
        self.assertEqual(article["editionDate"], "2026-09-21")

    def test_policy_filters_primary_subject_in_original_headline_and_lead_not_publisher_country(self):
        items = [
            self.item(0, title="实验团队发表测试结果", originalTitle="China launches a new satellite"),
            self.item(1, summary="北京团队发布测试结果。相关资料已经公开。"),
            self.item(2, title="美国机构公布卫星任务", originalTitle="NASA publishes mission results", country="China"),
            self.item(3, title="美国研究人员公布实验", originalTitle="Chinese-American researcher releases experiment"),
            self.item(4, contentType="paper"),
            self.item(5, summary="NASA公开测试结果。报道随后提到中国的历史任务。"),
        ]
        article = MODULE.build_daily_deepread(items, self.config, self.now)
        self.assertEqual({event["eventId"] for event in self.events(article)}, {"evt-2", "evt-3", "evt-5"})

    def test_selection_balances_technical_topics_and_sources_despite_conflict_score_skew(self):
        conflicts = [self.item(100 + n, category="局部冲突", source="单一媒体", url=f"https://wire.example/{n}", score=100) for n in range(24)]
        technical = [self.item(n, category=self.categories[n % 4], source=f"技术机构{n}", score=55) for n in range(12)]
        article = MODULE.build_daily_deepread(conflicts + technical, self.config, self.now)
        events = self.events(article)
        counts = Counter(event["category"] for event in events)
        self.assertEqual(len(events), 12)
        self.assertGreaterEqual(sum(counts[category] for category in self.categories[:4]), 8)
        self.assertTrue(all(counts[category] >= 1 for category in self.categories[:4]))
        self.assertGreaterEqual(len({event["imageSource"] for event in events}), 6)

    def test_evidence_priority_beats_score_and_keeps_richer_same_event_representative(self):
        strong = [self.item(n, score=50) for n in range(12)]
        weak = [self.item(50 + n, score=100, summary="仅有标题。") for n in range(12)]
        weak.append(self.item(100, score=100, eventId="evt-0", summary="仅有标题。"))
        article = MODULE.build_daily_deepread(weak + strong, self.config, self.now)
        self.assertEqual({event["newsId"] for event in self.events(article)}, {f"news-{n}" for n in range(12)})

    def test_same_event_sources_merge_without_creating_an_extra_event(self):
        first = self.item(0)
        duplicate = self.item(1, eventId="evt-0")
        article = MODULE.build_daily_deepread([first, duplicate], self.config, self.now)
        self.assertEqual(article["eventCount"], 1)
        self.assertEqual({source["url"] for source in self.events(article)[0]["sources"]}, {first["url"], duplicate["url"]})
        self.assertEqual(article["sourceCount"], 2)

    def test_targets_stay_between_ten_and_fifteen_without_repeating_events(self):
        items = [self.item(n) for n in range(22)]
        for target, count in [(1, 10), (15, 15), (99, 15), ("invalid", 12)]:
            with self.subTest(target=target):
                article = MODULE.build_daily_deepread(items, {**self.config, "deepread_target_events": target}, self.now)
                self.assertEqual(article["eventCount"], count)
                self.assertEqual(len({event["eventId"] for event in self.events(article)}), count)

    def test_sparse_edition_is_explicit_and_uses_only_available_events(self):
        article = MODULE.build_daily_deepread([self.item(n) for n in range(3)], self.config, self.now)
        self.assertEqual(article["eventCount"], 3)
        self.assertEqual(article["generationStatus"], "insufficient")
        self.assertIn("3", article["introduction"])
        self.assertIn("不足", article["introduction"])
        self.assertTrue(article["warnings"])
        self.assertGreater(len(article["conclusion"]), 50)

    def test_empty_edition_has_no_fabricated_sections_or_provider_call(self):
        def forbidden(*args, **kwargs):
            self.fail("An empty edition must not request an article from a provider")
        article = MODULE.build_daily_deepread([], self.config, self.now, self.runtime, forbidden)
        self.assertEqual(article["sections"], [])
        self.assertEqual(article["eventCount"], 0)
        self.assertEqual(article["sourceCount"], 0)
        self.assertEqual(article["generationStatus"], "insufficient")

    def test_unsafe_urls_are_removed_and_images_keep_publisher_attribution(self):
        items = [
            self.item(0, image="javascript:alert(1)", sources=[{"name": "bad", "url": "data:text/html,bad"}]),
            self.item(1, url="javascript:alert(2)", sources=[{"name": "安全来源", "url": "https://safe.example/story"}], image="https://cdn.example/photo.jpg"),
            self.item(2, url="file:///secret", sources=[]),
            self.item(3, url="https://user:password@publisher.example/story", sources=[], image="https://safe.example\n/evil.jpg"),
            self.item(4, image="//untrusted.example/photo.jpg"),
            self.item(5, image="https://publisher.example\\@evil.example/image.jpg"),
        ]
        article = MODULE.build_daily_deepread(items, self.config, self.now)
        events = {event["eventId"]: event for event in self.events(article)}
        self.assertEqual(set(events), {"evt-0", "evt-1", "evt-4", "evt-5"})
        self.assertEqual(events["evt-0"]["image"], "")
        self.assertEqual(events["evt-0"]["imageSource"], "")
        self.assertEqual(events["evt-1"]["image"], "https://cdn.example/photo.jpg")
        self.assertEqual(events["evt-1"]["imageSource"], "机构1")
        self.assertEqual(events["evt-4"]["image"], "")
        self.assertEqual(events["evt-5"]["image"], "")
        self.assertNotIn("javascript:", json.dumps(article))
        self.assertNotIn("password", json.dumps(article))

    def test_valid_model_article_uses_exact_selected_citations_and_metadata(self):
        items = [self.item(n) for n in range(12)]
        response = self.model_response(items)
        calls = []
        def request(runtime, **kwargs):
            calls.append((runtime, kwargs))
            return response
        article = MODULE.build_daily_deepread(items, self.config, self.now, self.runtime, request)
        self.assertEqual(article["generationStatus"], "ok")
        self.assertEqual(article["headline"], response["headline"])
        self.assertEqual(article["sections"][0]["overview"], response["sections"][0]["overview"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], self.runtime)
        self.assertEqual(set(calls[0][1]), {"instructions", "input_text", "schema_name", "schema", "example", "max_tokens"})
        self.assertLessEqual(calls[0][1]["max_tokens"], 16000)
        for event in self.events(article):
            original = next(item for item in items if item["id"] == event["newsId"])
            self.assertEqual(event["sources"], [{"name": original["source"], "url": original["url"]}])
            self.assertEqual(event["image"], original["image"])
            self.assertEqual(event["imageSource"], original["source"])
            self.assertEqual(event["category"], original["category"])
            self.assertEqual(event["publishedAt"], original["publishedAt"])

    def test_malformed_model_output_discards_entire_article(self):
        items = [self.item(n) for n in range(12)]
        valid = self.model_response(items)
        fallback = MODULE.build_daily_deepread(items, self.config, self.now)
        def mutate(path, value):
            response = copy.deepcopy(valid)
            target = response
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            return response
        malformed = [
            None, [], {},
            mutate(["sections"], []),
            mutate(["editionDate"], "2026-09-20"),
            mutate(["sections", 0, "events", 0, "eventId"], "unknown-event"),
            mutate(["sections", 0, "events", 0, "newsId"], "news-11"),
            mutate(["sections", 0, "events"], valid["sections"][0]["events"][:-1]),
            mutate(["sections", 0, "events"], valid["sections"][0]["events"] + [valid["sections"][0]["events"][0]]),
            mutate(["introduction"], 123),
            mutate(["introduction"], "过短"),
            mutate(["conclusion"], "好" * 5000),
            mutate(["sections", 0, "events", 0, "watchFor"], ["下一步"]),
            mutate(["sections", 0, "events", 0, "analysis"], ""),
            mutate(["sections", 0, "events", 0, "title"], "<script>bad()</script>"),
            mutate(["sections", 0, "events", 0, "summary"], "来源为 https://untrusted.example，" * 10),
            mutate(["sections", 0, "events", 0, "image"], "https://fabricated.example/photo.jpg"),
            mutate(["sections", 0, "events", 0, "sources"], [{"name": "假的", "url": "https://fabricated.example"}]),
        ]
        for index, response in enumerate(malformed):
            with self.subTest(case=index):
                article = MODULE.build_daily_deepread(items, self.config, self.now, self.runtime, lambda *args, **kwargs: response)
                self.assertEqual(article["generationStatus"], "fallback")
                self.assertEqual(article["headline"], fallback["headline"])
                self.assertEqual(article["sections"], fallback["sections"])
                self.assertTrue(article["warnings"])

    def test_duplicate_section_ids_are_rejected_even_with_complete_event_coverage(self):
        items = [self.item(n) for n in range(12)]
        response = self.model_response(items)
        second = copy.deepcopy(response["sections"][0])
        response["sections"][0]["events"] = response["sections"][0]["events"][:6]
        second["events"] = second["events"][6:]
        response["sections"].append(second)
        article = MODULE.build_daily_deepread(items, self.config, self.now, self.runtime, lambda *args, **kwargs: response)
        self.assertEqual(article["generationStatus"], "fallback")

    def test_provider_failure_has_one_call_and_no_leaked_error_details(self):
        calls = []
        def broken(*args, **kwargs):
            calls.append(1)
            raise RuntimeError("secret-provider-key: do-not-publish")
        article = MODULE.build_daily_deepread([self.item(n) for n in range(12)], self.config, self.now, self.runtime, broken)
        self.assertEqual(len(calls), 1)
        self.assertEqual(article["generationStatus"], "fallback")
        self.assertNotIn("secret-provider-key", json.dumps(article))
        self.assertTrue(all(event["summary"] and event["analysis"] for event in self.events(article)))

    def test_rejected_model_reports_field_and_length_without_private_text(self):
        items = [self.item(n) for n in range(12)]
        response = self.model_response(items)
        response["sections"][0]["overview"] = "PRIVATE_SENTINEL"
        error = MODULE._model_error(response, items, "2026-09-21")
        self.assertIn("sections[0].overview", error)
        self.assertIn("length 16", error)
        self.assertNotIn("PRIVATE_SENTINEL", error)
        self.assertEqual(MODULE._model_error(self.model_response(items), items, "2026-09-21"), "")

    def test_model_format_example_does_not_seed_fallback_editorial_claims(self):
        items = [self.item(n) for n in range(12)]
        fallback = MODULE.build_daily_deepread(items, self.config, self.now)
        calls = []
        def request(*args, **kwargs):
            calls.append(kwargs)
            return self.model_response(items)
        MODULE.build_daily_deepread(items, self.config, self.now, self.runtime, request)
        example = calls[0]["example"]
        self.assertNotEqual(example["introduction"], fallback["introduction"])
        seeded = {event["analysis"] for section in example["sections"] for event in section["events"]}
        self.assertFalse(seeded.intersection(event["analysis"] for event in self.events(fallback)))

    def test_invalid_structure_gets_one_guided_retry_with_same_original_evidence(self):
        items = [self.item(n) for n in range(12)]
        calls = []
        def request(*args, **kwargs):
            calls.append(kwargs)
            return {"wrong_envelope": "PRIVATE_PROVIDER_OUTPUT"} if len(calls) == 1 else self.model_response(items)
        article = MODULE.build_daily_deepread(items, self.config, self.now, self.runtime, request)
        self.assertEqual(article["generationStatus"], "ok")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["input_text"], calls[1]["input_text"])
        self.assertIn("editionDate", calls[1]["instructions"])
        self.assertIn("article:", calls[1]["instructions"])
        self.assertNotIn("PRIVATE_PROVIDER_OUTPUT", json.dumps(calls[1]))
        self.assertNotIn("wrong_envelope", json.dumps(calls[1]))

    def test_permanently_invalid_structure_has_bounded_retry_and_keeps_fallback(self):
        calls = []
        def request(*args, **kwargs):
            calls.append(kwargs)
            return {}
        article = MODULE.build_daily_deepread([self.item(n) for n in range(12)], self.config, self.now, self.runtime, request)
        self.assertEqual(len(calls), 2)
        self.assertEqual(article["generationStatus"], "fallback")

    def test_malformed_json_can_recover_with_one_format_retry(self):
        items = [self.item(n) for n in range(12)]
        calls = []
        def request(*args, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise json.JSONDecodeError("private malformed content", "PRIVATE_SENTINEL", 0)
            return self.model_response(items)
        article = MODULE.build_daily_deepread(items, self.config, self.now, self.runtime, request)
        self.assertEqual(article["generationStatus"], "ok")
        self.assertEqual(len(calls), 2)
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(calls))

    def test_permanently_malformed_json_stops_after_two_attempts(self):
        calls = []
        def request(*args, **kwargs):
            calls.append(kwargs)
            raise ValueError("private parser details")
        article = MODULE.build_daily_deepread([self.item(n) for n in range(12)], self.config, self.now, self.runtime, request)
        self.assertEqual(article["generationStatus"], "fallback")
        self.assertEqual(len(calls), 2)
        self.assertNotIn("private parser details", json.dumps(article))

    def test_unused_root_metadata_cannot_displace_a_complete_grounded_article(self):
        items = [self.item(n) for n in range(12)]
        response = self.model_response(items)
        response.update({"generationStatus": "invented-status", "sources": ["https://invented.example"],
                         "untrusted": "<script>PRIVATE_SENTINEL</script>"})
        article = MODULE.build_daily_deepread(items, self.config, self.now, self.runtime, lambda *args, **kwargs: response)
        self.assertEqual(article["generationStatus"], "ok")
        self.assertEqual(article["headline"], response["headline"])
        self.assertNotIn("invented.example", json.dumps(article))
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(article))

    def test_private_body_only_reaches_bounded_model_input_and_not_fallback(self):
        marker = "PRIVATE_BODY_SENTINEL"
        items = [self.item(n, evidenceText=marker + " 测试过程的已公开细节。" * 2000) for n in range(12)]
        calls = []
        def request(*args, **kwargs):
            calls.append(kwargs)
            raise ValueError("force factual fallback")
        article = MODULE.build_daily_deepread(items, self.config, self.now, self.runtime, request)
        self.assertIn(marker, calls[0]["input_text"])
        self.assertLess(len(calls[0]["input_text"]), 100000)
        self.assertNotIn(marker, json.dumps(article))
        self.assertNotIn("evidenceText", json.dumps(article))

    def test_sparse_valid_model_keeps_insufficient_status_and_explicit_shortfall(self):
        items = [self.item(n) for n in range(3)]
        response = self.model_response(items)
        article = MODULE.build_daily_deepread(items, self.config, self.now, self.runtime, lambda *args, **kwargs: response)
        self.assertEqual(article["generationStatus"], "insufficient")
        self.assertEqual(article["eventCount"], 3)
        self.assertIn("不足", article["introduction"])
        self.assertTrue(article["warnings"])

    def test_selection_and_fallback_are_deterministic_under_input_reordering(self):
        items = [self.item(n) for n in range(24)]
        first = MODULE.build_daily_deepread(items, self.config, self.now)
        second = MODULE.build_daily_deepread(list(reversed(items)), self.config, self.now)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
