import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree as ET


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
        self.papers = MODULE.collect_research_fixture(
            ROOT / "tests" / "fixtures" / "papers.json", self.now, self.config
        )

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
        self.assertTrue(all(item["contentType"] == "news" for item in report["items"]))

    def test_full_stream_preserves_all_qualified_candidates_and_top_flags(self):
        candidates = MODULE.score_articles(MODULE.deduplicate(self.articles), self.config, self.now)
        daily = MODULE.build_report(candidates, self.config, self.now, skip_ai=True)
        daily["items"][0]["title"] = "每日版中文编辑标题"
        top_items = {item["id"]: item for item in daily["items"]}
        stream = MODULE.build_stream_report(candidates, self.config, self.now, top_items)
        MODULE.validate_stream_report(stream)
        self.assertEqual(stream["itemCount"], len(candidates))
        self.assertEqual(sum(bool(item["isTopStory"]) for item in stream["items"]), 10)
        self.assertEqual(next(item for item in stream["items"] if item["id"] == daily["items"][0]["id"])["title"], "每日版中文编辑标题")
        self.assertEqual(sum(stream["categoryCounts"].values()), len(candidates))
        self.assertFalse(stream["truncated"])

    def test_research_radar_uses_separate_schema_and_scoring(self):
        papers = MODULE.score_research_papers(self.papers, self.config, self.now)
        report = MODULE.build_research_report(papers, self.config, self.now, skip_ai=True)
        MODULE.validate_research_report(report, allow_empty=False)
        self.assertEqual(report["itemCount"], 6)
        self.assertGreaterEqual(len(report["areaCounts"]), 3)
        self.assertTrue(all(item["contentType"] == "paper" for item in report["items"]))
        self.assertTrue(all(item["authors"] and item["pdfUrl"] for item in report["items"]))
        self.assertTrue(all("预印本" in item["peerReviewStatus"] for item in report["items"]))
        swarm = next(item for item in report["items"] if item["id"] == "arxiv:2607.14093")
        self.assertIn("蜂群机器人", swarm["collectionKeywords"])
        self.assertEqual(report["schemaVersion"], 2)
        self.assertEqual(len(report["collectionKeywords"]), 3)

    def test_research_selection_prevents_one_area_from_crowding_out_others(self):
        papers = []
        for area_index, area in enumerate(("人工智能", "天文与空间科学", "量子技术")):
            for index in range(10):
                papers.append(MODULE.ResearchPaper(
                    id=f"{area_index}-{index}", title=f"{area} paper {index}", abstract="evidence " * 80,
                    url=f"https://arxiv.org/abs/{area_index}.{index}", pdf_url="", source="arXiv",
                    published_at=self.now, updated_at=self.now, research_area=area,
                    score=100 - area_index - index / 100,
                ))
        papers.sort(key=lambda paper: paper.score, reverse=True)
        config = {**self.config, "research": {**self.config["research"], "limit": 12, "per_area_limit": 4}}
        selected = MODULE.choose_research_diverse(papers, config)
        counts = {area: sum(paper.research_area == area for paper in selected) for area in {paper.research_area for paper in selected}}
        self.assertEqual(counts, {"人工智能": 4, "天文与空间科学": 4, "量子技术": 4})

    def test_arxiv_queries_are_grouped_and_rate_limited(self):
        empty_feed = b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
        with mock.patch.object(MODULE, "http_get", return_value=empty_feed) as get, mock.patch.object(MODULE.time, "sleep") as sleep:
            self.assertEqual(MODULE.collect_arxiv(self.config, self.now), [])
        labels = {definition["label"] for definition in self.config["research"]["arxiv_categories"]}
        keyword_definitions = self.config["research"]["collection_keywords"]
        expected_queries = len(labels) + len(keyword_definitions)
        self.assertEqual(get.call_count, expected_queries)
        self.assertEqual(sleep.call_count, expected_queries - 1)
        self.assertTrue(all(call.kwargs.get("attempts") == 1 for call in get.call_args_list))
        queries = [
            MODULE.urllib.parse.parse_qs(MODULE.urllib.parse.urlsplit(call.args[0]).query)["search_query"][0]
            for call in get.call_args_list
        ]
        space_query = next(query for query in queries if "astro-ph.CO" in query)
        self.assertIn("astro-ph.EP", space_query)
        self.assertIn(" OR ", space_query)
        keyword_queries = [query for query in queries if "ti:" in query]
        self.assertEqual(len(keyword_queries), len(keyword_definitions))
        self.assertTrue(all("abs:" in query for query in keyword_queries))
        self.assertTrue(any('ti:"multimodal agent"' in query for query in keyword_queries))

    def test_deepseek_v4_flash_runtime_and_json_request(self):
        with mock.patch.dict(os.environ, {
            "AI_PROVIDER": "auto",
            "DEEPSEEK_API_KEY": "server-side-secret",
            "DEEPSEEK_MODEL": "deepseek-v4-flash",
            "OPENAI_API_KEY": "openai-fallback",
        }):
            runtime = MODULE.resolve_ai_runtime(self.config)
        self.assertEqual(runtime["provider"], "deepseek")
        self.assertEqual(runtime["model"], "deepseek-v4-flash")
        self.assertEqual(runtime["endpoint"], "https://api.deepseek.com/chat/completions")

        response = {"choices": [{"message": {"content": '{"items": []}'}}]}
        schema = {
            "type": "object",
            "properties": {"items": {"type": "array", "items": {"type": "string"}}},
            "required": ["items"],
            "additionalProperties": False,
        }
        with mock.patch.object(MODULE, "http_post_json", return_value=response) as post:
            result = MODULE.request_structured_json(
                runtime,
                instructions="请返回 JSON。",
                input_text="输入",
                schema_name="test_schema",
                schema=schema,
                example={"items": []},
                max_tokens=500,
            )
        self.assertEqual(result, {"items": []})
        endpoint, body, api_key = post.call_args.args
        self.assertEqual(endpoint, "https://api.deepseek.com/chat/completions")
        self.assertEqual(api_key, "server-side-secret")
        self.assertEqual(body["model"], "deepseek-v4-flash")
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(body["thinking"], {"type": "disabled"})
        self.assertNotIn("server-side-secret", json.dumps(body))

    def test_deepseek_daily_output_is_locally_validated_before_use(self):
        candidates = MODULE.score_articles(MODULE.deduplicate(self.articles), self.config, self.now)
        runtime = {
            "provider": "deepseek", "api_key": "secret", "model": "deepseek-v4-flash",
            "endpoint": "https://api.deepseek.com/chat/completions",
        }
        malformed = {"items": [{"id": candidates[0].id}] * 10}
        with mock.patch.object(MODULE, "request_structured_json", return_value=malformed) as request, mock.patch.object(
            MODULE.time, "sleep"
        ):
            with self.assertRaisesRegex(RuntimeError, "could not be parsed"):
                MODULE.ai_select(candidates[:12], self.config, runtime)
        self.assertEqual(request.call_count, 2)

    def test_stream_translation_keeps_partial_results_and_warning(self):
        candidates = MODULE.score_articles(MODULE.deduplicate(self.articles), self.config, self.now)[:2]
        runtime = {
            "provider": "deepseek", "api_key": "secret", "model": "deepseek-v4-flash",
            "endpoint": "https://api.deepseek.com/chat/completions",
        }
        translated = {
            "items": [{
                "id": candidates[0].id,
                "titleZh": "中文标题",
                "summary": "中文摘要",
                "tags": ["测试"],
            }],
        }
        with mock.patch.object(MODULE, "request_structured_json", return_value=translated):
            translations, warnings = MODULE.ai_translate_articles(candidates, self.config, runtime)
        self.assertEqual(list(translations), [candidates[0].id])
        self.assertTrue(translations[candidates[0].id]["_translationOnly"])
        self.assertEqual(translations[candidates[0].id]["_provider"], "deepseek")
        self.assertEqual(len(warnings), 1)
        stream = MODULE.build_stream_report(
            candidates, self.config, self.now, translations=translations,
            translation_runtime=runtime, translation_warnings=warnings,
        )
        self.assertEqual(stream["translatedItemCount"], 1)
        self.assertEqual(stream["translationProvider"], "deepseek")
        self.assertEqual(stream["items"][0]["scoreBasis"], "AI翻译 · 规则评分")

    def test_stream_translation_stops_after_two_consecutive_batch_failures(self):
        candidates = MODULE.score_articles(MODULE.deduplicate(self.articles), self.config, self.now)[:3]
        runtime = {
            "provider": "deepseek", "api_key": "secret", "model": "deepseek-v4-flash",
            "endpoint": "https://api.deepseek.com/chat/completions",
        }
        config = {**self.config, "stream_translation_batch_size": 1}
        with mock.patch.object(
            MODULE, "request_structured_json", side_effect=RuntimeError("temporary provider outage")
        ) as request:
            translations, warnings = MODULE.ai_translate_articles(candidates, config, runtime)
        self.assertEqual(translations, {})
        self.assertEqual(request.call_count, 2)
        self.assertTrue(any("连续失败 2 个批次" in warning for warning in warnings))

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
            "source": "NASA",
            "domain": "nasa.gov",
            "url": "https://www.nasa.gov/example/same-ai-release",
            "description": "NASA independently reports deployment timing, benchmark scope, customer access and evaluation context.",
        })
        second.evidence_sources = []
        result = MODULE.deduplicate([first, second])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].corroboration, 2)
        self.assertEqual({item["domain"] for item in result[0].evidence_sources}, {
            "technologyreview.com", "nasa.gov",
        })
        self.assertEqual(MODULE.source_weight(result[0], self.config), 20)

    def test_wire_syndication_is_one_independent_evidence_group(self):
        first = MODULE.Article(**{
            **MODULE.asdict(self.articles[0]),
            "source": "Reuters",
            "domain": "reuters.com",
            "url": "https://www.reuters.com/example/wire-copy",
            "description": "Reuters reported that the laboratory released the model after publishing evaluation data, access terms and deployment plans for industrial users.",
        })
        republishers = []
        for index, domain in enumerate(("news-one.example", "news-two.example", "news-three.example"), 1):
            republishers.append(MODULE.Article(**{
                **MODULE.asdict(first),
                "id": f"republisher-{index}",
                "source": f"Republisher {index}",
                "domain": domain,
                "url": f"https://{domain}/same-wire-story",
                "description": first.description + " Reuters",
            }))
            republishers[-1].evidence_sources = []
        first.evidence_sources = []
        result = MODULE.deduplicate([first, *republishers])
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0].evidence_sources), 4)
        self.assertEqual(result[0].corroboration, 1)
        self.assertEqual({source["evidenceGroup"] for source in result[0].evidence_sources}, {"wire:reuters"})

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
            stream_output = root / "stream.json"
            stream_status_output = root / "stream-status.json"
            research_output = root / "research.json"
            feed_output = root / "feed.xml"
            status = MODULE.main([
                "--config", str(ROOT / "config" / "news_config.json"),
                "--fixture", str(ROOT / "tests" / "fixtures" / "articles.json"),
                "--output", str(output),
                "--archive-dir", str(archive),
                "--archive-index", str(archive_index),
                "--search-index", str(search_index),
                "--status-output", str(status_output),
                "--stream-output", str(stream_output),
                "--stream-status-output", str(stream_status_output),
                "--research-output", str(research_output),
                "--research-fixture", str(ROOT / "tests" / "fixtures" / "papers.json"),
                "--feed-output", str(feed_output),
                "--skip-ai",
                "--now", "2026-07-16T00:00:00Z",
            ])
            self.assertEqual(status, 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["schemaVersion"], 4)
            self.assertEqual(payload["editionDate"], "2026-07-16")
            self.assertEqual(payload["timezone"], "Asia/Tokyo")
            self.assertEqual(payload["method"], "rules")
            self.assertEqual(len(payload["items"]), 10)
            self.assertTrue((archive / "2026-07-16.json").exists())
            self.assertEqual(json.loads(archive_index.read_text(encoding="utf-8"))["editions"][0]["editionDate"], "2026-07-16")
            search_payload = json.loads(search_index.read_text(encoding="utf-8"))
            self.assertEqual(search_payload["schemaVersion"], 2)
            self.assertEqual(len(search_payload["shards"]), 1)
            shard = json.loads((archive / "search-2026-07.json").read_text(encoding="utf-8"))
            self.assertEqual(len(shard["items"]), 10)
            self.assertTrue(all(item.get("_compact") for item in shard["items"]))
            self.assertTrue(all("scoreComponents" not in item and "sources" not in item for item in shard["items"]))
            self.assertTrue(all("isSupplemental" in item and "selectionWindowHours" in item for item in shard["items"]))
            atom = ET.parse(feed_output).getroot()
            self.assertEqual(len(atom.findall("{http://www.w3.org/2005/Atom}entry")), 10)
            pipeline_status = json.loads(status_output.read_text(encoding="utf-8"))
            self.assertEqual(pipeline_status["schemaVersion"], 4)
            self.assertEqual(pipeline_status["state"], "ok")
            self.assertEqual(pipeline_status["editorialStatus"], "disabled")
            stream = json.loads(stream_output.read_text(encoding="utf-8"))
            research = json.loads(research_output.read_text(encoding="utf-8"))
            self.assertEqual(stream["schemaVersion"], 2)
            self.assertEqual(research["schemaVersion"], 2)
            self.assertEqual(pipeline_status["streamItemCount"], stream["itemCount"])
            self.assertEqual(pipeline_status["researchItemCount"], 6)
            self.assertGreater(stream["itemCount"], 10)
            self.assertEqual(research["itemCount"], 6)
            stream_status = json.loads(stream_status_output.read_text(encoding="utf-8"))
            self.assertEqual(stream_status["schemaVersion"], 2)
            self.assertEqual(stream_status["state"], "ok")

    def test_irrecoverable_shortfall_writes_status_without_overwriting_latest(self):
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
                "--stream-output", str(root / "stream.json"),
                "--research-output", str(root / "research.json"),
                "--stream-status-output", str(root / "stream-status.json"),
                "--skip-ai",
                "--now", "2026-07-16T00:00:00Z",
            ])
            self.assertEqual(result, 2)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), {"sentinel": True})
            status = json.loads(status_output.read_text(encoding="utf-8"))
            self.assertEqual(status["state"], "failed")
            self.assertIn("分层补采后仍只有", status["message"])

    def test_daily_shortfall_is_backfilled_from_bounded_windows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "low-volume.json"
            items = []
            for index, article in enumerate(self.articles[:12]):
                item = MODULE.asdict(article)
                item["published_at"] = (
                    self.now - timedelta(hours=8 + index)
                    if index < 6 else self.now - timedelta(hours=30 + index - 6)
                ).isoformat()
                items.append(item)
            fixture.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
            output = root / "news.json"
            status_output = root / "status.json"
            stream_output = root / "stream.json"
            result = MODULE.main([
                "--config", str(ROOT / "config" / "news_config.json"),
                "--fixture", str(fixture),
                "--output", str(output),
                "--archive-dir", str(root / "archive"),
                "--archive-index", str(root / "archive" / "index.json"),
                "--search-index", str(root / "archive" / "search-index.json"),
                "--status-output", str(status_output),
                "--stream-output", str(stream_output),
                "--stream-status-output", str(root / "stream-status.json"),
                "--research-output", str(root / "research.json"),
                "--feed-output", str(root / "feed.xml"),
                "--skip-ai", "--skip-research",
                "--now", "2026-07-16T00:00:00Z",
            ])
            self.assertEqual(result, 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            status = json.loads(status_output.read_text(encoding="utf-8"))
            stream = json.loads(stream_output.read_text(encoding="utf-8"))
            self.assertEqual(len(report["items"]), 10)
            self.assertLess(stream["itemCount"], 10)
            self.assertEqual(report["freshItemCount"], stream["itemCount"])
            self.assertEqual(report["supplementalItemCount"], 10 - stream["itemCount"])
            self.assertEqual(report["coverageStatus"], "supplemented")
            self.assertTrue(all(item["selectionNote"] for item in report["items"] if item["isSupplemental"]))
            self.assertEqual(status["state"], "ok")
            self.assertEqual(status["supplementalItemCount"], report["supplementalItemCount"])

    def test_daily_shortfall_reuses_only_fresh_validated_stream_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "partial-live-fetch.json"
            fixture.write_text(
                json.dumps([MODULE.asdict(item) for item in self.articles[:2]], default=str),
                encoding="utf-8",
            )
            scored = MODULE.score_articles(MODULE.deduplicate(self.articles), self.config, self.now)
            cached_items = [MODULE.item_from_article(article, self.config) for article in scored[:12]]
            stream_output = root / "stream.json"
            stream_output.write_text(json.dumps({
                "schemaVersion": 1,
                "generatedAt": self.now.isoformat().replace("+00:00", "Z"),
                "itemCount": len(cached_items),
                "items": cached_items,
            }, ensure_ascii=False), encoding="utf-8")
            output = root / "news.json"
            result = MODULE.main([
                "--config", str(ROOT / "config" / "news_config.json"),
                "--fixture", str(fixture),
                "--output", str(output),
                "--archive-dir", str(root / "archive"),
                "--archive-index", str(root / "archive" / "index.json"),
                "--search-index", str(root / "archive" / "search-index.json"),
                "--status-output", str(root / "status.json"),
                "--stream-output", str(stream_output),
                "--stream-status-output", str(root / "stream-status.json"),
                "--research-output", str(root / "research.json"),
                "--feed-output", str(root / "feed.xml"),
                "--skip-ai", "--skip-research",
                "--now", "2026-07-16T00:00:00Z",
            ])
            self.assertEqual(result, 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(report["items"]), 10)
            self.assertEqual(report["supplementalItemCount"], 0)
            self.assertGreaterEqual(json.loads(stream_output.read_text(encoding="utf-8"))["itemCount"], 10)

    def test_diversity_limits_relax_in_tiers_instead_of_failing(self):
        candidates = []
        for index in range(10):
            article = MODULE.Article(**{
                **MODULE.asdict(self.articles[0]),
                "id": f"same-domain-{index}",
                "url": f"https://same-source.example/story-{index}",
                "domain": "same-source.example",
                "category": "AI",
                "published_at": self.now - timedelta(minutes=index),
                "raw_score": 90 - index,
            })
            candidates.append(article)
        selected = MODULE.choose_diverse(candidates, self.config, 10)
        self.assertEqual(len(selected), 10)
        self.assertEqual(sum(article.diversity_relaxed for article in selected), 8)
        report = MODULE.build_report(candidates, self.config, self.now, skip_ai=True)
        self.assertEqual(len(report["items"]), 10)
        self.assertEqual(report["coverageStatus"], "supplemented")
        self.assertTrue(any("分级放宽配额" in warning for warning in report["warnings"]))

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

    def test_invalid_date_uses_window_edge_and_is_penalized(self):
        fallback = self.now - timedelta(hours=24)
        parsed, estimated = MODULE.parse_datetime_checked("not-a-date", fallback)
        self.assertEqual(parsed, fallback)
        self.assertTrue(estimated)
        article = MODULE.Article(**{
            **MODULE.asdict(self.articles[2]),
            "published_at": parsed,
            "date_estimated": True,
        })
        scored = MODULE.score_articles([article], self.config, self.now)
        self.assertEqual(len(scored), 1)
        self.assertEqual(scored[0].score_components["日期异常降权"], 7)
        self.assertTrue(any("窗口边缘" in reason for reason in scored[0].score_reasons))

    def test_ai_selection_must_pass_category_diversity(self):
        candidates = MODULE.score_articles(MODULE.deduplicate(self.articles), self.config, self.now)[:10]
        editorial = {article.id: {"category": "AI"} for article in candidates}
        with self.assertRaisesRegex(ValueError, "多样性"):
            MODULE.validate_ai_diversity(candidates, editorial, self.config)

    def test_ai_failure_is_exposed_as_pipeline_warning(self):
        candidates = MODULE.score_articles(MODULE.deduplicate(self.articles), self.config, self.now)
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), mock.patch.object(
            MODULE, "ai_select", side_effect=RuntimeError("HTTP 429 temporary limit")
        ):
            report = MODULE.build_report(candidates, self.config, self.now, skip_ai=False)
        self.assertEqual(report["method"], "rules")
        self.assertEqual(report["editorialStatus"], "fallback")
        self.assertIn("429", report["warnings"][0])
        with tempfile.TemporaryDirectory() as directory:
            status_path = Path(directory) / "status.json"
            MODULE.write_pipeline_status(
                status_path,
                state="ok",
                now=self.now,
                message="日报更新成功；" + report["warnings"][0],
                report=report,
            )
            status = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertEqual(status["editorialStatus"], "fallback")
        self.assertIn("429", status["warnings"][0])

    def test_openai_http_post_retries_one_transient_failure(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"ok": true}'

        with mock.patch.object(
            MODULE.urllib.request,
            "urlopen",
            side_effect=[MODULE.urllib.error.URLError("temporary"), Response()],
        ) as urlopen, mock.patch.object(MODULE.time, "sleep") as sleep:
            payload = MODULE.http_post_json("https://api.example.test", {"x": 1}, "secret", attempts=2)
        self.assertEqual(payload, {"ok": True})
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once()


if __name__ == "__main__":
    unittest.main()
