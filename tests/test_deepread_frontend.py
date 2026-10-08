import copy
import json
import unittest

import test_news_reading as reading_tests
from test_update_news import MODULE, ROOT


class DeepreadFrontendTests(unittest.TestCase):
    browser_result = reading_tests.NewsReadingTests.browser_result

    def test_raw_evidence_can_expand_at_the_paragraph_with_source_and_capture_time(self):
        from evidence_trace import make_evidence
        payload = self.editorial_payload()
        event = payload['events'][0]
        url = event['sources'][0]['url']
        event['evidenceRecords'] = make_evidence('NASA完成无人机导航试验，飞行持续30分钟。', url, '2026-09-21T00:00:00Z')
        payload['chapters'][0]['blocks'][0]['evidenceIds'] = [r['evidenceId'] for r in event['evidenceRecords']]
        rendered = self.browser_result(f'renderEditorialContent(normalizeDeepread({json.dumps(payload)}))')
        self.assertIn('原文依据', rendered)
        self.assertIn('NASA完成无人机导航试验，飞行持续30分钟。', rendered)
        self.assertIn('抓取', rendered)
        self.assertIn('08:00', rendered)
        self.assertIn(event['evidenceRecords'][0]['evidenceId'], rendered)

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

    def topic_payload(self, failed=False):
        from test_deepread_topics import TopicPublicationTests, EditorialProvider
        from deepread_quality import choose_readable_deepread
        draft=TopicPublicationTests().build(EditorialProvider(fail='sensor' if failed else None))
        for event in draft['events']:
            event.update(image='https://example.org/'+event['newsId']+'.jpg',imageSource='Lab Journal')
        return choose_readable_deepread(draft,[],'2026-10-08')

    def test_topic_partial_renders_prose_analysis_and_compact_sentence_footnotes(self):
        payload=self.topic_payload(failed=True)
        result=self.browser_result('(async()=>{const r=await normalizeDeepreadForReader('+json.dumps(payload)+');return {status:r.readerStatus,html:renderDeepreadArticle(r)};})()')
        self.assertEqual(result['status'],'partial')
        for text in ['合格主题已先行发布','编辑分析','deepread-ref','data-evidence-target','原文证据','deepread-hero']:
            self.assertIn(text,result['html'])
        self.assertEqual(result['html'].count('class="deepread-footnotes"'),1)
        self.assertNotIn('本期深读生成失败',result['html'])

    def test_topic_chapter_order_is_bound_to_its_editorial_review(self):
        payload=self.topic_payload()
        payload['chapters'][0]['blocks'].reverse()
        result=self.browser_result('(async()=>{const r=await normalizeDeepreadForReader('+json.dumps(payload)+');return {status:r.readerStatus,html:renderDeepreadArticle(r)};})()')
        self.assertEqual(result['status'],'unavailable')
        self.assertNotIn('封闭仿真中的问题',result['html'])

    def test_topic_layout_has_one_hero_for_multiple_topics(self):
        result=self.browser_result('(async()=>renderDeepreadArticle(await normalizeDeepreadForReader('+json.dumps(self.topic_payload())+')))()')
        self.assertEqual(result.count('class="deepread-figure deepread-hero"'),1)
        self.assertEqual(result.count('class="deepread-source-thumb"'),1)
        self.assertEqual(result.count('class="deepread-footnotes"'),2)

    def test_latest_retained_publication_date_fetches_latest_and_keeps_content_date(self):
        payload=json.loads((ROOT/'public/data/deepread.json').read_text())
        payload.update(readerStatus='retained',publicationEditionDate='2026-10-08')
        result=self.browser_result('''(async()=>{
          const urls=[];state.latestReport={editionDate:'2026-10-08'};
          fetchPublicationJson=async url=>{urls.push(url);return url.endsWith('index.json') ? {editions:[]} : PAYLOAD;};
          await loadDeepread('2026-10-08',true);
          return {urls,date:state.deepreadReport?.editionDate,cached:state.deepreadCache.has('2026-10-08'),html:renderDeepreadArticle(state.deepreadReport)};
        })()'''.replace('PAYLOAD',json.dumps(payload)))
        self.assertIn('./data/deepread.json',result['urls'])
        self.assertEqual(result['date'],'2026-10-07')
        self.assertTrue(result['cached'])
        self.assertIn('今日深读未更新，以下为 2026-10-07 内容',result['html'])

    def test_real_archives_keep_original_format_without_becoming_new_complete_editions(self):
        payloads=[json.loads(path.read_text()) for path in sorted((ROOT/'public/data/deepread').glob('????-??-??.json'))]
        result=self.browser_result('(async()=>{state.historicalSelection=true;return Promise.all('+json.dumps(payloads)+'.map(async p=>{const r=await normalizeDeepreadForReader(p);return {date:p.editionDate,revision:p.generationRevision,status:r.readerStatus,rendered:renderDeepreadArticle(r).includes("deepread-article")};}));})()')
        self.assertTrue(all(r['rendered'] for r in result),result)
        self.assertTrue(all(r.get('status')!='complete' for r in result if r['revision']<12))

    def test_old_revision_with_corrupted_captured_evidence_cannot_use_format_compatibility(self):
        payload=json.loads((ROOT/'public/data/deepread/2026-10-04.json').read_text())
        payload['generationRevision']=10
        payload['events'][0]['evidenceRecords'][0]['text']+=' Uncaptured claim.'
        result=self.browser_result('(async()=>{state.historicalSelection=true;const r=await normalizeDeepreadForReader('+json.dumps(payload)+');return {status:r.readerStatus,html:renderDeepreadArticle(r)};})()')
        self.assertEqual(result['status'],'unavailable')
        self.assertNotIn('deepread-article',result['html'])

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

    def editorial_payload(self):
        return {
            "schemaVersion": 2, "editionDate": "2026-09-27", "generatedAt": "2026-09-26T23:07:00Z",
            "headline": "从试验准备到结果公布", "lead": "今天发布的结果使项目从准备进入测试记录。",
            "candidateCount": 12, "eventCount": 1, "sourceCount": 1, "generationStatus": "ok",
            "events": [{"newsId": "nasa", "eventId": "evt-0123456789ab", "title": "NASA 公布任务测试结果",
                        "category": "航空航天", "publishedAt": "2026-09-26T22:00:00Z",
                        "evidenceLevel": "primary", "sources": [{"name": "NASA", "url": "https://nasa.gov/news/mission"}],
                        "image": "https://nasa.gov/mission.jpg", "imageSource": "NASA",
                        "history": [{"editionDate": "2026-09-25", "newsId": "old", "title": "NASA 宣布准备试验", "source": "NASA"}]}],
            "chapters": [{"id": "chapter-1", "title": "任务进入实际测试", "angle": "从准备到完成",
                          "newsIds": ["nasa"], "blocks": [
                              {"type": "paragraph", "text": "本次公开试验结果。", "newsIds": ["nasa"]},
                              {"type": "change", "text": "前次公布准备安排；今天公布实际测试结果。", "newsIds": ["nasa"]},
                          ]}],
        }

    def test_version_two_renders_prose_changes_and_evidence_without_old_card_template(self):
        payload = self.editorial_payload()
        rendered = self.browser_result(f'renderEditorialContent(normalizeDeepread({json.dumps(payload)}))')
        for expected in ["任务进入实际测试", "今天公布实际测试结果", "一手来源", "2026-09-25",
                         "https://nasa.gov/news/mission", "mission.jpg"]:
            self.assertIn(expected, rendered)
        self.assertNotIn("后续关注", rendered)
        self.assertNotIn("deepread-event", rendered)

    def test_version_two_filter_removes_event_its_prose_and_shared_lead(self):
        payload = self.editorial_payload()
        banned = copy.deepcopy(payload["events"][0])
        banned.update(newsId="banned", eventId="evt-banned", title="某国公布新卫星任务",
                      originalTitle="China launches new satellite")
        payload["events"].append(banned)
        payload["headline"] = "REMOVED_HEADLINE"
        payload["lead"] = "REMOVED_LEAD"
        payload["chapters"].append({"id": "chapter-2", "title": "REMOVED_CHAPTER", "angle": "REMOVED_ANGLE",
                                   "newsIds": ["banned"], "blocks": [
                                       {"type": "paragraph", "text": "REMOVED_PROSE", "newsIds": ["banned"]}]})
        payload["chapters"][0]["blocks"].append({"type": "paragraph", "text": "REMOVED_SHARED",
                                                   "newsIds": ["nasa", "banned"]})
        report = self.browser_result(f'normalizeDeepread({json.dumps(payload)})')
        self.assertEqual(report["eventCount"], 1)
        self.assertEqual(len(report["chapters"]), 1)
        self.assertNotIn("REMOVED_", json.dumps(report))

    def test_version_two_filter_removes_prose_about_excluded_historical_record(self):
        payload = self.editorial_payload()
        payload["events"][0]["history"][0]["title"] = "China launches satellite"
        payload["chapters"][0]["blocks"][1]["text"] = "REMOVED_HISTORY China launches satellite"
        payload["headline"] = "REMOVED_HEADLINE"
        payload["lead"] = "REMOVED_LEAD"
        report = self.browser_result(f'normalizeDeepread({json.dumps(payload)})')
        self.assertTrue(report["contentFiltered"])
        self.assertEqual(report["events"][0]["history"], [])
        self.assertNotIn("REMOVED_", json.dumps(report))
        self.assertNotIn("China launches satellite", json.dumps(report))

    def test_version_two_ignores_untrusted_markup_and_unknown_evidence_levels(self):
        payload = self.editorial_payload()
        payload["events"][0]["sources"].append({"name": "bad", "url": "javascript:alert(1)"})
        payload["events"][0]["sources"].extend([
            {"name": "private", "url": "http://172.16.0.1/report"},
            {"name": "loopback", "url": "http://[::1]/report"},
        ])
        payload["events"][0]["evidenceLevel"] = '<script>alert(2)</script>'
        payload["chapters"][0]["blocks"][0]["text"] = '<img src=x onerror=alert(3)>'
        rendered = self.browser_result(f'renderEditorialContent(normalizeDeepread({json.dumps(payload)}))')
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img src=x", rendered)
        self.assertNotIn("javascript:", rendered)
        self.assertNotIn("172.16.0.1", rendered)
        self.assertNotIn("[::1]", rendered)
        self.assertIn("单源报道", rendered)

    def test_version_two_comparison_and_short_observations_link_to_sources(self):
        payload = self.editorial_payload()
        second = copy.deepcopy(payload["events"][0])
        second.update(newsId="other", eventId="evt-other", title="另一项智能体试验",
                      sources=[{"name": "第二来源", "url": "https://example.org/other"}])
        payload["events"].append(second)
        chapter = payload["chapters"][0]
        chapter.update(kind="comparison", comparisonKey="ai-agent",
                       comparisonNote="并列比较不代表事件之间存在因果关系。", newsIds=["nasa", "other"])
        chapter["blocks"].extend([
            {"type": "paragraph", "text": "第二项试验公布范围。", "newsIds": ["other"]},
            {"type": "comparison", "text": "两项报道分别披露试验范围与各自边界。", "newsIds": ["nasa", "other"]},
        ])
        payload["observations"] = [{"text": "两项试验分别界定了当前的测试范围。", "newsIds": ["nasa", "other"],
                                     "supports": [{"newsId": "nasa", "supportQuote": "NASA 公布任务测试结果"},
                                                  {"newsId": "other", "supportQuote": "另一项智能体试验"}]}]
        rendered = self.browser_result(f'renderEditorialContent(normalizeDeepread({json.dumps(payload)}))')
        for expected in ["并列比较不代表事件之间存在因果关系", "两项报道分别披露", "今日观察",
                         "两项试验分别界定", "https://example.org/other", "deepread-comparison"]:
            self.assertIn(expected, rendered)

    def test_version_two_filter_clears_comparison_note_observations_and_removed_prose(self):
        payload = self.editorial_payload()
        banned = copy.deepcopy(payload["events"][0])
        banned.update(newsId="banned", eventId="evt-banned", title="China launches new satellite",
                      originalTitle="China launches new satellite")
        payload["events"].append(banned)
        payload["chapters"][0].update(kind="comparison", comparisonKey="ai-agent",
                                      comparisonNote="REMOVED_COMPARISON_NOTE", newsIds=["nasa", "banned"])
        payload["chapters"][0]["blocks"].append({"type": "comparison", "text": "REMOVED_COMPARISON_PROSE",
                                                   "newsIds": ["nasa", "banned"]})
        payload["observations"] = [{"text": "REMOVED_OBSERVATION", "newsIds": ["nasa", "banned"],
                                     "supports": [{"newsId": "banned", "supportQuote": "China launches"}]}]
        report = self.browser_result(f'normalizeDeepread({json.dumps(payload)})')
        self.assertTrue(report["contentFiltered"])
        self.assertEqual(report["observations"], [])
        self.assertEqual(report["chapters"][0]["kind"], "event")
        self.assertNotIn("REMOVED_", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
