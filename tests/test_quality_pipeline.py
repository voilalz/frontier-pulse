"""Integration contracts for grounded evidence, editorial mix and event storage."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from unittest import mock

from test_update_news import MODULE as news, ROOT


class QualityPipelineTests(unittest.TestCase):
    def setUp(self):
        self.config = news.load_config(ROOT / "config/news_config.json")
        self.now = news.parse_datetime("2026-09-21T08:00:00Z", news.utc_now())

    def article(self, key, category="AI", score=80):
        return news.Article(
            id=key, title="OpenAI releases a new reasoning model", description="OpenAI released a reasoning model with tool support.",
            url=f"https://{key}.example/story", source=key, domain=f"{key}.example",
            country="国际", published_at=self.now, category=category, raw_score=score,
        )

    def test_unrelated_feed_evidence_is_filtered_even_without_page_fetching(self):
        article = self.article("mission", "航空航天")
        article.title = "NASA launches Europa Clipper spacecraft"
        article.description = "The local football club signed a new goalkeeper. " * 50
        with mock.patch.object(news, "http_get") as fetch:
            news.enrich_article_descriptions([article], {**self.config, "article_text_enabled": False})
        fetch.assert_not_called()
        self.assertEqual(article.description, "")
        self.assertEqual(article.evidence_quality["status"], "title-only")

    def test_specialist_sources_can_supply_articles_without_generic_topic_words(self):
        article = self.article("specific")
        article.title, article.description = "Introducing GPT-7 Preview", "Available from Tuesday."
        article.source_specialist = True
        article.source_topics = ["AI"]
        self.assertEqual([a.id for a in news.score_articles([article], self.config, self.now)], ["specific"])
        article.source_specialist = False
        self.assertEqual(news.score_articles([article], self.config, self.now), [])

    def test_atom_publication_precedes_updated_time_regardless_of_xml_order(self):
        feed = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>OpenAI releases AI model</title><link href="https://ai.example/old"/><updated>2026-09-21T07:00:00Z</updated><published>2026-09-10T07:00:00Z</published></entry><entry><title>NASA launches satellite</title><link href="https://space.example/unknown"/><updated>2026-09-21T07:00:00Z</updated></entry></feed>'
        config = {**self.config, "rss_feeds": [{"name": "Atom", "url": "https://ai.example/feed"}]}
        with mock.patch.object(news, "http_get", return_value=feed):
            articles = news.collect_rss(config, self.now)
        self.assertEqual(articles[0].published_at.date().isoformat(), "2026-09-10")
        self.assertFalse(articles[0].date_estimated)
        self.assertTrue(articles[1].date_estimated)

    def test_ambiguous_general_news_words_are_not_effective_topic_coverage(self):
        for title in ("Fashion brand announces perfume launch", "Teachers announce nationwide strike over pay",
                      "Bakery unveils new chocolate chip cookie", "Russia wins the football championship",
                      "Navy blue dresses are back in fashion", "Hospital treats patients after a heart attack"):
            with self.subTest(title=title):
                article = self.article("general")
                article.title, article.description, article.source = title, "", "BBC World"
                self.assertEqual(news.score_articles([article], self.config, self.now), [])
        for title in ("NASA prepares Europa launch", "Russia conducts a missile strike on Kyiv",
                      "New chip processor uses quantum error correction", "US navy orders an unmanned vessel"):
            with self.subTest(title=title):
                article = self.article("qualified")
                article.title, article.description = title, ""
                self.assertEqual(len(news.score_articles([article], self.config, self.now)), 1)

    def test_balanced_shortlist_preserves_lower_scoring_technology_topics(self):
        conflicts = [self.article(f"conflict{i}", "局部冲突", 95) for i in range(45)]
        tech = [self.article(f"tech{i}", category, 60) for i, category in enumerate(("AI", "航空航天", "无人系统", "前沿技术"))]
        selected = news.balanced_shortlist(conflicts + tech, 20)
        self.assertEqual(len(selected), 20)
        self.assertTrue({a.id for a in tech}.issubset({a.id for a in selected}))

    def test_top_ten_retains_technology_presence_and_combined_security_cap(self):
        candidates = [self.article(f"security{i}", "军事动态" if i % 2 else "局部冲突", 95) for i in range(12)]
        candidates += [self.article(f"tech{i}", ("AI", "航空航天", "无人系统", "前沿技术")[i % 4], 60) for i in range(12)]
        selected = news.choose_diverse(candidates, {**self.config, "security_topic_limit": 4}, 10)
        self.assertEqual(len(selected), 10)
        self.assertLessEqual(sum(a.category in {"军事动态", "局部冲突"} for a in selected), 4)
        self.assertTrue({"AI", "航空航天", "无人系统", "前沿技术"}.issubset({a.category for a in selected}))

    def test_source_text_is_not_published_but_evidence_status_is(self):
        article = self.article("private")
        article.evidence_quality = {"status": "body", "selectedCount": 2, "candidateCount": 4, "reason": "title match"}
        article.description = "Private original evidence used only for model input."
        item = news.item_from_article(article, self.config, {"titleZh": "模型更新", "summary": "模型增加了工具支持。"})
        self.assertEqual(item["summaryEvidence"]["status"], "body")
        self.assertNotIn("evidenceText", item)
        self.assertNotIn("description", item)
        self.assertGreaterEqual(item["summaryRevision"], 4)

    def test_published_model_summary_never_becomes_original_source_evidence(self):
        unsupported = "OpenAI GPT-5 已获得全世界医院认证，能保证治疗所有疾病。"
        cached = news.article_from_public_item({"id": "cached", "title": "OpenAI GPT-5 发布", "originalTitle": "OpenAI releases GPT-5",
            "url": "https://openai.com/index/gpt-5", "publishedAt": self.now.isoformat(),
            "summary": unsupported, "summaryRevision": 3, "translationProvider": "deepseek"}, self.now)
        self.assertIsNotNone(cached)
        with mock.patch.object(news, "http_get", side_effect=RuntimeError("offline")):
            news.enrich_article_descriptions([cached], self.config)
        self.assertEqual(cached.description, "")
        self.assertEqual(cached.evidence_quality["status"], "title-only")

    def test_registry_roundtrip_reuses_event_for_new_publisher_followup(self):
        first = {"id": "original", "originalTitle": "NASA launches Europa Clipper spacecraft to Jupiter",
                 "title": "欧罗巴快船发射", "url": "https://nasa.gov/europa-launch", "publishedAt": "2026-09-20T12:00:00Z",
                 "category": "航空航天", "summary": "NASA launched Europa Clipper to study Jupiter's moon."}
        news.assign_event_ids([first], {}, self.config)
        registry = news.build_event_registry({"editionDate": "2026-09-20", "generatedAt": "2026-09-20T13:00:00Z", "items": [first]}, {}, self.config, self.now)
        self.assertTrue(registry["items"][0]["identityRepresentatives"])
        following = {**first, "id": "followup", "url": "https://space.example/europa-update",
                     "originalTitle": "NASA confirms Europa Clipper spacecraft healthy after Jupiter launch",
                     "publishedAt": "2026-09-21T07:00:00Z"}
        following.pop("eventId")
        news.assign_event_ids([following], registry, self.config)
        self.assertEqual(following["eventId"], first["eventId"])

    def test_featured_cache_cannot_replace_new_evidence_or_added_sources(self):
        current = {"summaryRevision": news.SUMMARY_REVISION, "summaryInputHash": "fresh",
                   "sources": [{"url": "https://nasa.gov/current"}, {"url": "https://esa.int/current"}],
                   "corroboration": {"independentCount": 2}, "category": "航空航天", "score": 82,
                   "eventId": "current-event", "evidenceMatrix": {"current": True},
                   "eventDossier": {"current": True}, "summary": "新的中文摘要", "translationProvider": "deepseek"}
        for cached_hash in ("outdated", "fresh"):
            with self.subTest(cached_hash=cached_hash):
                item = copy.deepcopy(current)
                cached = {**current, "summaryInputHash": cached_hash, "sources": current["sources"][:1],
                          "corroboration": {"independentCount": 1}, "category": "军事动态", "score": 40,
                          "eventId": "old-event", "evidenceMatrix": {"current": False},
                          "eventDossier": {"current": False}}
                news.merge_featured_stream_item(item, cached)
                self.assertEqual(item, current)

    def test_stream_only_run_persists_every_event_and_reuses_ids_next_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = ["--config", str(ROOT / "config/news_config.json"),
                    "--fixture", str(ROOT / "tests/fixtures/articles.json"),
                    "--output", str(root / "news.json"), "--stream-output", str(root / "stream.json"),
                    "--stream-status-output", str(root / "stream-status.json"),
                    "--stream-only", "--skip-research", "--skip-ai", "--now", "2026-07-16T00:00:00Z"]
            self.assertEqual(news.main(args), 0)
            first = json.loads((root / "stream.json").read_text())
            registry = json.loads((root / "events.json").read_text())
            known = {news_id for record in registry["items"] for news_id in record["newsIds"]}
            self.assertTrue({item["id"] for item in first["items"]}.issubset(known))
            self.assertTrue(all(item["eventIdentity"]["version"] == 2 for item in first["items"]))
            self.assertEqual(news.main(args), 0)
            second = json.loads((root / "stream.json").read_text())
            self.assertEqual({item["id"]: item["eventId"] for item in first["items"]},
                             {item["id"]: item["eventId"] for item in second["items"]})
            self.assertFalse((root / "news.json").exists())
            self.assertFalse((root / "deepread.json").exists())

    def test_relevant_article_page_can_supply_its_declared_illustration(self):
        article = self.article("europa", "航空航天")
        article.title = "NASA launches Europa Clipper spacecraft"
        article.description = "NASA launched Europa Clipper on Monday."
        page = '<meta property="og:image" content="https://nasa.gov/europa.jpg"><article><h1>NASA launches Europa Clipper spacecraft</h1><p>NASA launched Europa Clipper on Monday to study the icy moon of Jupiter. The mission carries three science instruments for its orbital observations.</p></article>'
        with mock.patch.object(news, "http_get", return_value=page.encode()):
            news.enrich_article_descriptions([article], self.config)
        self.assertEqual(article.image, "https://nasa.gov/europa.jpg")


if __name__ == "__main__":
    unittest.main()
