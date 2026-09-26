import copy
import json
import unittest

import test_news_reading as reading_tests
from test_update_news import MODULE, ROOT


class DeepreadFrontendTests(unittest.TestCase):
    browser_result = reading_tests.NewsReadingTests.browser_result

    def setUp(self):
        self.config = MODULE.load_config(ROOT / "config/news_config.json")
        self.payload = {
            "schemaVersion": 1, "editionDate": "2026-09-21", "generatedAt": "2026-09-21T00:00:00Z",
            "headline": "从模型到轨道，今日科技进展", "introduction": "今天的主线。",
            "conclusion": "后续关注实际部署。", "generationStatus": "ok", "warnings": [],
            "sections": [{"id": "space", "title": "空间探索", "overview": "任务进入新阶段。", "events": [{
                "newsId": "nasa", "eventId": "evt-0123456789ab", "title": "NASA 发射任务", "summary": "卫星进入轨道。",
                "analysis": "后续能力取决于在轨测试。", "watchFor": "等待首批观测结果。", "category": "航空航天",
                "publishedAt": "2026-09-20T23:00:00Z", "sources": [{"name": "NASA", "url": "https://nasa.gov/news/mission"}],
                "image": "https://nasa.gov/mission.jpg", "imageSource": "NASA",
            }]}],
        }

    def test_reading_layout_has_contents_images_source_citations_and_analysis(self):
        rendered = self.browser_result(f'renderDeepreadArticle(normalizeDeepread({json.dumps(self.payload)}))')
        for expected in ['deepread-toc', '空间探索', 'NASA 发射任务', 'mission.jpg', '图片来源', 'https://nasa.gov/news/mission', '后续能力取决于在轨测试。']:
            self.assertIn(expected, rendered)
        self.assertNotIn('重要度', rendered)

    def test_bad_urls_and_untrusted_markup_cannot_create_active_elements(self):
        event = self.payload["sections"][0]["events"][0]
        event["title"] = '<script>alert("x")</script>'
        event["image"] = 'javascript:alert(1)'
        event["sources"].append({"name": "bad", "url": 'javascript:alert(2)'})
        rendered = self.browser_result(f'renderDeepreadArticle(normalizeDeepread({json.dumps(self.payload)}))')
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('javascript:', rendered)
        self.assertIn('&lt;script&gt;', rendered)
        self.assertIn('https://nasa.gov/news/mission', rendered)

    def test_policy_filter_removes_event_and_cached_cross_event_prose(self):
        banned = copy.deepcopy(self.payload["sections"][0]["events"][0])
        banned.update(newsId="excluded", eventId="evt-111111111111", title="China launches a new satellite", summary="A new mission.")
        self.payload["sections"][0]["events"].append(banned)
        self.payload["headline"] = "REMOVED_HEADLINE"
        self.payload["introduction"] = "REMOVED_INTRO"
        self.payload["sections"][0]["overview"] = "REMOVED_OVERVIEW"
        self.payload["conclusion"] = "REMOVED_CONCLUSION"
        result = self.browser_result(f'normalizeDeepread({json.dumps(self.payload)})')
        self.assertEqual(result["eventCount"], 1)
        self.assertNotIn("REMOVED_", json.dumps(result))
        self.assertNotIn("China", json.dumps(result))

    def test_archive_fetch_never_displays_another_date_as_requested_edition(self):
        expression = '(async () => { fetchJson = async () => (' + json.dumps(self.payload) + '); await loadDeepread("2026-09-19", true); return {report:state.deepreadReport,error:state.deepreadLoadError}; })()'
        result = self.browser_result(expression)
        self.assertIsNone(result["report"])
        self.assertTrue(result["error"])

    def test_archive_dates_are_specific_to_deepread(self):
        expression = '(() => {state.view="deepread"; state.archiveIndex={editions:[{editionDate:"2026-01-01"}]}; state.deepreadIndex={editions:[{editionDate:"2026-09-21"}]}; return availableDates();})()'
        self.assertEqual(self.browser_result(expression), ["2026-09-21"])

    def test_slower_previous_date_response_cannot_replace_newer_selection(self):
        old = {**self.payload, "editionDate": "2026-09-20"}
        expression = '''(async () => {
          let releaseOld;
          fetchJson = (url) => url.endsWith("index.json") ? Promise.resolve({editions:[]})
            : url.includes("2026-09-20") ? new Promise(resolve => { releaseOld=resolve; })
            : Promise.resolve(NEW_PAYLOAD);
          const older = loadDeepread("2026-09-20", true);
          await loadDeepread("2026-09-21", true);
          releaseOld(OLD_PAYLOAD); await older;
          return state.deepreadReport.editionDate;
        })()'''.replace("NEW_PAYLOAD", json.dumps(self.payload)).replace("OLD_PAYLOAD", json.dumps(old))
        self.assertEqual(self.browser_result(expression), "2026-09-21")


if __name__ == "__main__":
    unittest.main()
