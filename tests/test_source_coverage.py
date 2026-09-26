import importlib.util
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import update_news as news

AUDIT_SPEC = importlib.util.find_spec("audit_sources")
audit = importlib.util.module_from_spec(AUDIT_SPEC) if AUDIT_SPEC else None
if audit is not None:
    AUDIT_SPEC.loader.exec_module(audit)


class SourceCoverageTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 21, 8, tzinfo=timezone.utc)
        self.config = news.load_config(ROOT / "config/news_config.json")
        self.config["rss_feeds"] = [{
            "name": "Fixture Science", "url": "https://science.example/feed",
            "default_category": "前沿技术", "weight": 16,
        }]

    def article(self, slug, title, *, hours=1, estimated=False, description=""):
        return news.Article(
            id=slug, title=title, description=description,
            url=f"https://science.example/{slug}", source="Fixture Science",
            domain="science.example", country="国际",
            published_at=self.now - timedelta(hours=hours), date_estimated=estimated,
        )

    def summarize(self, articles, diagnostics=None):
        self.assertIsNotNone(audit, "the reproducible source audit module is required")
        return audit.summarize_coverage(articles, self.config, self.now, diagnostics or [])

    def test_actual_24h_count_excludes_stale_future_unknown_policy_and_duplicates(self):
        articles = [
            self.article("rocket", "Europa Clipper rocket completes orbital launch"),
            self.article("quantum", "Quantum chip achieves a new error correction threshold"),
            self.article("rocket", "Europa Clipper rocket completes orbital launch"),
            self.article("old", "AI model released last week", hours=25),
            self.article("future", "New robotics platform released tomorrow", hours=-1),
            self.article("unknown", "New semiconductor announced", estimated=True),
            self.article("excluded", "China launches new satellite"),
            self.article("unrelated", "The football club announces its training schedule"),
            self.article("sponsored", "[Sponsored] New AI model vendor launch"),
        ]
        result = self.summarize(articles)
        self.assertEqual(result["collectedCount"], 9)
        self.assertEqual(result["freshCount"], 6)
        self.assertEqual(result["unknownDateCount"], 1)
        self.assertEqual(result["outsideWindowCount"], 1)
        self.assertEqual(result["futureDateCount"], 1)
        self.assertEqual(result["policyExcludedCount"], 1)
        self.assertEqual(result["editorialExcludedCount"], 1)
        self.assertEqual(result["topicExcludedCount"], 1)
        self.assertEqual(result["qualifiedBeforeDedupCount"], 3)
        self.assertEqual(result["duplicateCount"], 1)
        self.assertEqual(result["qualifiedCandidateCount"], 2)
        self.assertEqual(sum(result["categoryCounts"].values()), 2)
        self.assertEqual(result["activeSourceCount"], 1)
        self.assertEqual(result["targetGap"], 98)
        self.assertFalse(result["targetReached"])

    def test_acquisition_errors_and_empty_sources_remain_distinct(self):
        self.assertIsNotNone(audit, "the reproducible source audit module is required")
        self.config["rss_feeds"] = [
            {"name": name, "url": f"https://{name}.example/feed", "default_category": "AI"}
            for name in ["good", "empty", "malformed", "offline", "disabled"]
        ]
        self.config["rss_feeds"][-1]["enabled"] = False
        good = b'''<rss><channel>
            <item><title>AI model passes a reasoning benchmark</title>
            <link>https://good.example/ai</link><pubDate>Mon, 21 Sep 2026 06:00:00 GMT</pubDate></item>
            <item><title>Satellite enters Europa orbit</title>
            <link>https://good.example/space</link><pubDate>Mon, 21 Sep 2026 05:00:00 GMT</pubDate></item>
            </channel></rss>'''
        payloads = {"good": good, "empty": b"<rss><channel/></rss>", "malformed": b"<rss>"}

        def fetch(url, **kwargs):
            source = url.split("//", 1)[1].split(".", 1)[0]
            if source == "offline":
                raise RuntimeError("HTTP 503 fixture unavailable")
            if source == "disabled":
                self.fail("disabled sources must not be requested")
            return payloads[source]

        with mock.patch.object(audit.news, "http_get", side_effect=fetch):
            result = audit.run_audit(self.config, self.now)
        sources = {row["source"]: row for row in result["sources"]}
        self.assertEqual(result["qualifiedCandidateCount"], 2)
        self.assertEqual(result["activeSourceCount"], 1)
        self.assertEqual(result["reachableSourceCount"], 2)
        self.assertEqual(result["failedSourceCount"], 2)
        self.assertEqual(sources["good"]["state"], "ok")
        self.assertEqual(sources["empty"]["state"], "empty")
        self.assertEqual(sources["malformed"]["state"], "error")
        self.assertEqual(sources["offline"]["state"], "error")
        self.assertIn("503", sources["offline"]["error"])
        self.assertEqual(sources["disabled"]["state"], "disabled")
        self.assertEqual(sources["good"]["qualifiedCount"], 2)
        self.assertEqual(result["rawEntryCount"], 2)
        self.assertEqual(result["truncatedCount"], 0)

    def test_atom_and_rdf_dates_count_without_estimation(self):
        self.assertIsNotNone(audit, "the reproducible source audit module is required")
        self.config["rss_feeds"] = [
            {"name": name, "url": f"https://{name}.example/feed", "default_category": "航空航天"}
            for name in ["atom", "rdf"]
        ]
        payloads = {
            "atom": b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
                <title>Rocket arrives at launch pad</title><link href="https://atom.example/one"/>
                <published>2026-09-21T01:00:00Z</published></entry></feed>''',
            "rdf": b'''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">
                <item rdf:about="https://rdf.example/two"><title>Satellite captures an asteroid image</title>
                <link>https://rdf.example/two</link><dc:date>2026-09-21T02:00:00Z</dc:date></item></rdf:RDF>''',
        }
        with mock.patch.object(audit.news, "http_get", side_effect=lambda url, **kw: payloads[url.split("//")[1].split(".")[0]]):
            result = audit.run_audit(self.config, self.now)
        self.assertEqual(result["qualifiedCandidateCount"], 2)
        self.assertEqual(result["unknownDateCount"], 0)

    def test_qualified_source_counts_do_not_double_count_shared_story(self):
        self.config["rss_feeds"].append({"name": "Second Source", "url": "https://second.example/feed"})
        first = self.article("rocket", "Europa Clipper rocket completes orbital launch")
        second = self.article("rocket", first.title)
        second.source = "Second Source"
        result = self.summarize([first, second])
        sources = {row["source"]: row for row in result["sources"]}
        self.assertEqual(result["qualifiedCandidateCount"], 1)
        self.assertEqual(result["activeSourceCount"], 2)
        self.assertEqual(sources["Fixture Science"]["qualifiedCount"], 1)
        self.assertEqual(sources["Second Source"]["qualifiedCount"], 1)
        self.assertEqual(sum(row["uniqueContributionCount"] for row in sources.values()), 1)

    def test_audit_payload_contains_counts_not_source_article_text(self):
        private_source_text = "This long source body should never be published by an audit."
        result = self.summarize([self.article("quantum", "Quantum experiment", description=private_source_text)])
        self.assertNotIn(private_source_text, json.dumps(result))
        self.assertNotIn("Quantum experiment", json.dumps(result))

    def test_repeated_audit_does_not_mutate_collected_articles(self):
        articles = [
            self.article("rocket", "Europa Clipper rocket completes orbital launch"),
            self.article("rocket", "Europa Clipper rocket completes orbital launch"),
        ]
        before = [dict(vars(article)) for article in articles]
        first = self.summarize(articles)
        second = self.summarize(articles)
        self.assertEqual(first, second)
        self.assertEqual([vars(article) for article in articles], before)

    def test_updated_timestamp_cannot_turn_an_old_or_undated_entry_into_fresh_news(self):
        payload = b'''<feed xmlns="http://www.w3.org/2005/Atom">
            <entry><title>AI model from last month</title><link href="https://science.example/old"/>
            <updated>2026-09-21T07:00:00Z</updated><published>2026-08-21T07:00:00Z</published></entry>
            <entry><title>Quantum chip with no publication date</title><link href="https://science.example/unknown"/>
            <updated>2026-09-21T07:00:00Z</updated></entry>
            </feed>'''
        with mock.patch.object(audit.news, "http_get", return_value=payload):
            result = audit.run_audit(self.config, self.now)
        self.assertEqual(result["collectedCount"], 2)
        self.assertEqual(result["outsideWindowCount"], 1)
        self.assertEqual(result["unknownDateCount"], 1)
        self.assertEqual(result["qualifiedCandidateCount"], 0)


if __name__ == "__main__":
    unittest.main()
