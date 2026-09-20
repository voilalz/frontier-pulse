"""Reader-facing contracts: supported summaries and consistent topic filtering."""
import copy
import json
import subprocess
import unittest
from dataclasses import replace
from unittest import mock

from test_update_news import MODULE, ROOT


class NewsReadingTests(unittest.TestCase):
    def setUp(self):
        self.config = MODULE.load_config(ROOT / "config/news_config.json")
        self.now = MODULE.parse_datetime("2026-09-20T00:00:00Z", MODULE.utc_now())

    def article(self, title, description="A satellite launch is scheduled for Monday."):
        return MODULE.Article(
            id="story", title=title, description=description,
            url="https://example.org/story", source="International desk",
            domain="example.org", country="国际", published_at=self.now,
        )

    def test_china_subjects_are_excluded_before_ranking(self):
        for title, lead in [
            ("China launches a new satellite", "A launch took place today."),
            ("Huawei introduces an AI chip", "Production will start next year."),
            ("New military drone enters service", "The Chinese navy announced its deployment."),
            ("New chip export controls", "The U.S. restricted exports of AI chips to Chinese companies."),
            ("US restricts semiconductor exports to China", "New rules take effect Monday."),
            ("中国发布新型无人机", "测试已经完成。"),
            ("DeepSeek releases new model", "An AI model was announced."),
            ("DJI introduces drone platform", "An autonomous drone was demonstrated."),
        ]:
            with self.subTest(title=title):
                self.assertEqual(MODULE.score_articles([self.article(title, lead)], self.config, self.now), [])

    def test_incidental_mentions_and_publisher_geography_do_not_exclude_story(self):
        for article in [
            self.article("NASA launches a lunar satellite", "NASA launched from Florida. China has a separate lunar programme."),
            replace(self.article("ESA tests a new rocket"), country="China"),
            self.article("Indian scientists improve machining robotics"),
            self.article("Chinese-American scientist wins robotics prize in Germany"),
        ]:
            with self.subTest(title=article.title):
                self.assertEqual(len(MODULE.score_articles([article], self.config, self.now)), 1)

    def test_old_cached_news_cannot_bypass_subject_filter(self):
        item = {"title": "中国无人机试验", "originalTitle": "China tests autonomous aircraft",
                "url": "https://example.org/cache", "summary": "A new drone trial.",
                "publishedAt": "2026-09-19T23:00:00Z"}
        cached = MODULE.article_from_public_item(item, self.now)
        self.assertIsNotNone(cached)
        self.assertEqual(MODULE.score_articles([cached], self.config, self.now, lookback_hours=72), [])

    def test_rss_uses_fuller_content_without_truncating_evidence_to_teaser(self):
        body = "The satellite programme includes ground tests and orbital demonstrations. " * 18
        body += "The final test is scheduled for 28 September with three payloads."
        feed = (f'<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item>'
                f'<title>NASA prepares satellite mission</title><link>https://example.org/story</link>'
                f'<description>Short teaser.</description><content:encoded><![CDATA[<p>{body}</p>]]></content:encoded>'
                f'<pubDate>Sun, 20 Sep 2026 00:00:00 GMT</pubDate></item></channel></rss>').encode()
        config = {**self.config, "rss_feeds": [{"name": "Test", "url": "https://example.org/rss"}]}
        with mock.patch.object(MODULE, "http_get", return_value=feed):
            articles = MODULE.collect_rss(config, self.now)
        self.assertEqual(len(articles), 1)
        self.assertIn("28 September with three payloads", articles[0].description)
        self.assertNotIn("<p>", articles[0].description)

    def test_long_supported_summary_is_not_cut_at_old_220_character_limit(self):
        summary = "欧洲团队公布了新一代卫星测试计划，介绍了试验目标和载荷。" * 8 + "最终发射时间仍待批准。"
        item = MODULE.item_from_article(self.article("ESA satellite tests"), self.config, {"summary": summary})
        self.assertEqual(item["summary"], summary)

    def test_article_text_uses_body_paragraphs_without_navigation_or_promotions(self):
        page = '''<nav><p>Navigation</p></nav><article><h1>Satellite launch</h1>
          <div class="entry-content"><p>The mission <strong>launched</strong> on Monday.</p>
          <aside><p>Related stories</p></aside><div class="newsletter"><p>Subscribe now</p></div>
          <p>Three instruments will measure the atmosphere for five years.</p></div>
          <footer><p>Copyright notice</p></footer></article>'''
        self.assertEqual(MODULE.extract_article_text(page),
            "The mission launched on Monday. Three instruments will measure the atmosphere for five years.")

    def test_article_text_reads_structured_body_but_respects_restricted_pages(self):
        data = {"@type": "NewsArticle", "articleBody": "The mission launched on Monday. " * 12}
        page = '<script type="application/ld+json">' + json.dumps(data) + '</script>'
        self.assertIn("launched on Monday", MODULE.extract_article_text(page))
        restricted = page + '<script type="application/ld+json">{"isAccessibleForFree":false}</script>'
        self.assertEqual(MODULE.extract_article_text(restricted), "")
        self.assertEqual(MODULE.extract_article_text('<main><p>Sign in to read this article.</p></main>'), "")

    def test_short_feed_is_enriched_and_failed_article_fetch_keeps_original(self):
        article = self.article("NASA satellite mission")
        old_description = article.description
        body = '<article><p>' + ('The spacecraft carries three sensors and will operate for five years. ' * 20) + '</p></article>'
        with mock.patch.object(MODULE, "http_get", return_value=body.encode()) as fetch:
            MODULE.enrich_article_descriptions([article], self.config)
        self.assertTrue(article.description.startswith(old_description))
        self.assertIn("three sensors", article.description)
        self.assertLessEqual(len(article.description), MODULE.SOURCE_TEXT_LIMIT)
        self.assertEqual(fetch.call_count, 1)
        unavailable = self.article("ESA mission")
        with mock.patch.object(MODULE, "http_get", side_effect=RuntimeError("unavailable")):
            MODULE.enrich_article_descriptions([unavailable], self.config)
        self.assertEqual(unavailable.description, old_description)

    def test_news_translation_does_not_receive_internal_verification_fields(self):
        article = self.article("NASA satellite mission")
        with mock.patch.object(MODULE, "request_structured_json", return_value={"items": []}) as request:
            MODULE.request_daily_translation_batch([article], self.config, {"provider": "deepseek"})
        evidence = json.loads(request.call_args.kwargs["input_text"].split("\n", 1)[1])
        self.assertNotIn("corroboration", evidence[0])
        self.assertNotIn("score", evidence[0])

    def test_daily_recovers_successful_stream_translation_after_batch_failure(self):
        article = self.article("NASA satellite mission")
        daily_item = MODULE.item_from_article(article, self.config)
        report = {"items": [daily_item], "translationProvider": "deepseek", "translationStatus": "failed",
                  "translatedItemCount": 0, "translationWarnings": ["translation failed"],
                  "warnings": ["selection notice", "translation failed"],
                  "translationDiagnostics": {"requestedItemCount": 1, "completedItemCount": 0,
                      "missingItemCount": 1, "missingItemIds": [article.id]}}
        translated = MODULE.item_from_article(article, self.config, {
            "titleZh": "卫星任务", "summary": "卫星将于周一发射并部署三台观测仪器。", "_provider": "deepseek",
        })
        MODULE.recover_daily_translations(report, {"items": [translated]})
        self.assertEqual(daily_item["summary"], translated["summary"])
        self.assertEqual(report["translationStatus"], "ok")
        self.assertEqual(report["translatedItemCount"], 1)
        self.assertEqual(report["translationWarnings"], [])
        self.assertEqual(report["warnings"], ["selection notice"])
        self.assertEqual(report["translationDiagnostics"]["totalMissingItemCount"], 0)

    def test_daily_recovery_does_not_copy_translation_for_other_evidence(self):
        article = self.article("NASA satellite mission")
        daily = MODULE.item_from_article(article, self.config)
        article.description += " The launch was cancelled."
        translated = MODULE.item_from_article(article, self.config, {
            "titleZh": "发射取消", "summary": "任务已取消。", "_provider": "deepseek",
        })
        report = {"items": [daily], "translationProvider": "deepseek"}
        MODULE.recover_daily_translations(report, {"items": [translated]})
        self.assertEqual(daily["title"], article.title)

    def test_rule_fallback_keeps_complete_sentences_and_does_not_pad(self):
        short = "The satellite launched on Monday."
        self.assertEqual(MODULE.fallback_summary(self.article("Satellite launch", short)), short)
        full = "The satellite launched on Monday. " * 8 + "Its orbit is 500 kilometres above Earth."
        self.assertEqual(MODULE.fallback_summary(self.article("Satellite launch", full)), full)

    def test_old_short_translation_cache_is_invalidated(self):
        article = self.article("NASA satellite mission")
        runtime = {"provider": "deepseek", "model": "test-model"}
        previous = {"translationProvider": "deepseek", "translationModel": "test-model", "items": [{
            "id": article.id, "originalTitle": article.title, "title": "旧标题", "summary": "旧的极短摘要",
            "translationProvider": "deepseek", "tags": [],
        }]}
        self.assertEqual(MODULE.reusable_stream_translations(previous, [article], runtime), {})

    def test_enriched_source_invalidates_cached_translation(self):
        article = self.article("NASA satellite mission")
        runtime = {"provider": "deepseek", "model": "test-model"}
        previous = MODULE.build_stream_report([article], self.config, self.now,
            translations={article.id: {"titleZh": "卫星计划", "summary": "卫星将于周一发射。", "_provider": "deepseek"}},
            translation_runtime=runtime)
        article.description += " The mission will deploy three instruments and run for five years."
        self.assertEqual(MODULE.reusable_stream_translations(previous, [article], runtime), {})

    def test_stale_daily_summary_cannot_overwrite_new_stream_translation(self):
        article = self.article("NASA satellite mission")
        stale = MODULE.item_from_article(article, self.config, {
            "titleZh": "旧标题", "summary": "旧的短摘要", "_provider": "deepseek",
        })
        stale.pop("summaryRevision")
        stale.pop("summaryInputHash")
        stream = MODULE.build_stream_report([article], self.config, self.now,
            top_stories={article.id: stale}, translations={article.id: {
                "titleZh": "新标题", "summary": "新摘要包含更完整的任务信息和发射计划。", "_provider": "deepseek",
            }})
        self.assertEqual(stream["items"][0]["summary"], "新摘要包含更完整的任务信息和发射计划。")

    def test_stale_featured_translation_does_not_skip_stream_translation(self):
        article = self.article("NASA satellite mission")
        runtime = {"provider": "deepseek", "model": "test-model"}
        daily = MODULE.item_from_article(article, self.config, {
            "titleZh": "卫星任务", "summary": "卫星将于周一发射。", "_provider": "deepseek",
        })
        featured = {article.id: daily}
        self.assertEqual(MODULE.current_featured_translation_ids([article], featured, runtime), {article.id})
        daily.pop("summaryRevision")
        self.assertEqual(MODULE.current_featured_translation_ids([article], featured, runtime), set())
        daily["summaryRevision"] = MODULE.SUMMARY_REVISION
        article.description += " The launch is now postponed until October."
        self.assertEqual(MODULE.current_featured_translation_ids([article], featured, runtime), set())

    def test_daily_summary_with_old_evidence_cannot_replace_updated_story(self):
        article = self.article("NASA satellite mission")
        daily = MODULE.item_from_article(article, self.config, {
            "titleZh": "卫星任务", "summary": "旧任务计划。", "_provider": "deepseek",
        })
        article.description += " The launch is now postponed until October."
        stream = MODULE.build_stream_report([article], self.config, self.now,
            top_stories={article.id: daily}, translations={article.id: {
                "titleZh": "卫星任务推迟", "summary": "任务已推迟至十月。", "_provider": "deepseek",
            }})
        self.assertEqual(stream["items"][0]["summary"], "任务已推迟至十月。")

    def browser_result(self, expression):
        # Execute the real normalizers/renderers; avoid network and browser startup.
        script = r'''
const fs = require('fs'), vm = require('vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const source = fs.readFileSync('public/assets/app.js', 'utf8');
const marker = source.indexOf('  document.addEventListener("click"');
if (marker < 0) throw new Error('Cannot locate app event boundary');
const elements = {};
const context = {URL, URLSearchParams, Date, Set, Map, console,
  location: {search:'', hash:''}, localStorage:{getItem:()=>null},
  window:{matchMedia:()=>({matches:false})},
  document:{getElementById:id=>(elements[id] ||= {}), querySelectorAll:()=>[]},
  policy:input.policy, result:null};
const expose = '\nif (typeof newsPolicy !== "undefined") newsPolicy = policy;\nresult = (' + input.expression + ');\n})();';
vm.runInNewContext(source.slice(0,marker) + expose, context);
process.stdout.write(JSON.stringify(context.result));
'''
        result = subprocess.run(["node", "-e", script], cwd=ROOT, input=json.dumps({
            "policy": self.config.get("content_policy", {}), "expression": expression,
        }), text=True, capture_output=True, check=True)
        return json.loads(result.stdout)

    def test_news_card_exposes_summary_and_sources_without_analysis_panels(self):
        item = MODULE.item_from_article(self.article("ESA tests a satellite"), self.config)
        item.update({"why": "NOT_FOR_READER", "score": 87, "summary": "完整摘要，包含任务、时间和关键细节。"})
        rendered = self.browser_result(f'renderStory(normalizeItem({json.dumps(item)}, 0), 0, false)')
        self.assertIn(item["summary"], rendered)
        self.assertIn(item["url"], rendered)
        for label in ["为什么重要", "重要度", "置信度", "事件档案", "争议矩阵", "NOT_FOR_READER"]:
            self.assertNotIn(label, rendered)

    def test_frontend_policy_handles_abbreviations_and_incidental_mentions(self):
        records = [
            {"title": "New chip export controls", "summary": "The U.S. restricted exports to Chinese firms."},
            {"title": "NASA satellite launch", "summary": "NASA launched from Florida. China has a separate programme."},
            {"title": "Chinese-American scientist wins robotics prize in Germany", "summary": "A robotics prize was awarded."},
            {"title": "我国发布新型无人机", "summary": "中国公司宣布完成试验。"},
        ]
        self.assertEqual(self.browser_result(f'{json.dumps(records)}.map(isAllowedNewsItem)'), [False, True, True, False])

    def test_frontend_blocks_old_editions_bookmarks_and_search_hits(self):
        raw = [{"id": "china", "title": "中国测试无人机", "originalTitle": "China tests a drone", "url": "https://example.org/c"},
               {"id": "esa", "title": "ESA satellite launch", "summary": "ESA announced a new launch. China has a separate project.", "url": "https://example.org/e"}]
        expression = ('(() => {state.items=' + json.dumps(raw) + '.map((x,i)=>normalizeItem(x,i));'
                      'return ["latest","stream","history","bookmarks","watchlist"].map(view=>{'
                      'state.view=view;state.watchwords=["satellite","drone"];state.rangeHours=24;'
                      'state.streamReport={generatedAt:new Date().toISOString()};'
                      'return viewFilteredItems().map(x=>x.id);});})()')
        # Stream dates must fall within its active window.
        expression = expression.replace('state.items=', 'state.items=').replace('.map((x,i)=>normalizeItem(x,i))', '.map((x,i)=>normalizeItem({...x,publishedAt:new Date().toISOString()},i))')
        self.assertEqual(self.browser_result(expression), [["esa"]] * 5)


if __name__ == "__main__":
    unittest.main()
