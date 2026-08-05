import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendTests(unittest.TestCase):
    def test_production_frontend_has_no_bundled_sample_fallback(self):
        index = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "public" / "assets" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("bundledNews", index + app)
        self.assertNotIn("内置启动数据", index + app)
        self.assertIn("上次成功读取的真实日报", app)

    def test_archive_personal_views_and_status_endpoint_are_wired(self):
        index = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "public" / "assets" / "app.js").read_text(encoding="utf-8")
        for view in ("history", "bookmarks", "watchlist"):
            self.assertIn(f'data-view="{view}"', index)
        self.assertIn("./data/archive/search-index.json", app)
        self.assertIn("./data/status.json", app)
        self.assertIn("payload?.shards", app)
        self.assertIn("hydrateCompactItem", app)

    def test_full_stream_and_research_radar_are_wired(self):
        index = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "public" / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "public" / "assets" / "styles.css").read_text(encoding="utf-8")
        for view in ("stream", "research"):
            self.assertIn(f'data-view="{view}"', index)
            self.assertIn(f'href="./?view={view}" data-view="{view}"', index)
        for endpoint in ("./data/stream.json", "./data/research.json", "./data/stream-status.json"):
            self.assertIn(endpoint, app)
        self.assertIn('id="spotlightStories"', index)
        self.assertIn('id="rangeControls"', index)
        self.assertIn('id="sourceFilter"', index)
        self.assertIn('id="loadMoreBtn"', index)
        self.assertIn("renderPaper", app)
        self.assertIn("researchArea", app)
        self.assertIn("isTopStory", app)
        self.assertIn("isSupplemental", app)
        self.assertIn("本期 Top 10 已使用透明补全", app)
        self.assertIn(".supplemental-badge", styles)
        self.assertIn(".spotlight-grid", styles)
        self.assertIn(".paper-detail", styles)

    def test_view_navigation_survives_stale_scripts_and_assets_revalidate(self):
        index = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "public" / "assets" / "app.js").read_text(encoding="utf-8")
        worker = (ROOT / "public" / "sw.js").read_text(encoding="utf-8")
        headers = (ROOT / "public" / "_headers").read_text(encoding="utf-8")
        self.assertIn("./assets/app.js?v=2.0.3", index)
        self.assertIn("./assets/styles.css?v=2.0.3", index)
        self.assertIn('event.preventDefault();\n      await switchView(viewButton.dataset.view);', app)
        self.assertIn('request.mode === "navigate"', worker)
        self.assertIn("frontier-pulse-", worker)
        self.assertIn("v2.0.3", worker)
        self.assertIn("/assets/*\n  Cache-Control: public, max-age=0, must-revalidate", headers)

    def test_cache_is_bypassed_only_for_manual_refresh(self):
        app = (ROOT / "public" / "assets" / "app.js").read_text(encoding="utf-8")
        self.assertIn("fetchJson(ENDPOINTS.latest, bypassCache)", app)
        self.assertNotIn("fetchJson(ENDPOINTS.latest, true)", app)
        self.assertIn("await loadLatest(true, true)", app)
        self.assertIn("cache: bypassCache ? \"no-store\" : \"default\"", app)

    def test_sharing_images_theme_and_offline_support_are_present(self):
        index = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "public" / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "public" / "assets" / "styles.css").read_text(encoding="utf-8")
        self.assertIn('rel="alternate" type="application/atom+xml"', index)
        self.assertIn('property="og:image"', index)
        self.assertIn('id="themeBtn"', index)
        self.assertIn("data-share", app)
        self.assertIn("loading=\"lazy\"", app)
        self.assertIn("expandedKeys", app)
        self.assertIn("serviceWorker.register", app)
        self.assertIn('html[data-theme="dark"]', styles)
        self.assertTrue((ROOT / "public" / "sw.js").exists())
        self.assertTrue((ROOT / "public" / "og-card.png").exists())

    def test_readability_tokens_contrast_and_image_overlay_are_regression_guarded(self):
        styles = (ROOT / "public" / "assets" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("--text-body: 14px", styles)
        self.assertIn("--text-small: 12px", styles)
        self.assertIn("--text-meta: 11px", styles)
        self.assertIn(":root { --text-small: 13px; --text-meta: 12px; }", styles)
        self.assertIn("--muted: #4f5c63", styles)
        self.assertIn("font-family: system-ui, -apple-system", styles)
        self.assertNotIn("font-family: Inter", styles)
        self.assertEqual(styles.count("font-size: 8px"), 2)
        self.assertNotIn("font-size: 9px", styles)
        self.assertNotIn("font: 8px", styles)
        self.assertIn(".summary { margin: 0; color: #4f5d64; font-size: var(--text-body)", styles)
        self.assertIn(".alert p { margin: 3px 0 0; font-size: var(--text-body)", styles)
        self.assertIn(".spotlight-card p { margin: 0; color: var(--muted); font-size: var(--text-body)", styles)
        self.assertIn("linear-gradient(rgba(4,15,22,.5), rgba(4,15,22,.5))", styles)
        self.assertNotIn("letter-spacing: -.05em", styles)

    def test_china_timezone_is_consistent_and_legacy_editions_keep_their_label(self):
        index = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "public" / "assets" / "app.js").read_text(encoding="utf-8")
        config = (ROOT / "config" / "news_config.json").read_text(encoding="utf-8")
        daily = (ROOT / ".github" / "workflows" / "daily-news.yml").read_text(encoding="utf-8")
        stream = (ROOT / ".github" / "workflows" / "stream-update.yml").read_text(encoding="utf-8")
        self.assertIn('"timezone": "Asia/Shanghai"', config)
        self.assertIn('timezone: "Asia/Shanghai"', daily)
        self.assertIn('timezone: "Asia/Shanghai"', stream)
        self.assertIn('cron: "7 7 * * *"', daily)
        self.assertIn('cron: "37 8 * * *"', daily)
        self.assertIn('paths:\n      - ".github/workflows/daily-news.yml"', daily)
        self.assertIn("python scripts/check_daily_refresh.py", daily)
        self.assertIn("steps.refresh_gate.outputs.should_run", daily)
        self.assertIn('id="editionTimezone">版本日期 · 中国标准时间（UTC+8）', index)
        self.assertIn('if (zone === "Asia/Shanghai") return "版本日期 · 中国标准时间（UTC+8）"', app)
        self.assertIn('if (zone === "Asia/Tokyo") return "版本日期 · 东京时间（UTC+9）"', app)
        self.assertIn('function chinaEditionClock(value = new Date())', app)
        self.assertIn('chinaNow.minutes >= 8 * 60 + 15', app)
        self.assertIn('"今日日报尚未生成"', app)

    def test_public_metadata_and_generation_config_use_custom_domain(self):
        index = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        config = (ROOT / "config" / "news_config.json").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        official_url = "https://newsfrontier.top/"
        self.assertIn(f'property="og:url" content="{official_url}"', index)
        self.assertIn(f'property="og:image" content="{official_url}og-card.png"', index)
        self.assertIn(f'name="twitter:image" content="{official_url}og-card.png"', index)
        self.assertIn(f'rel="canonical" href="{official_url}"', index)
        self.assertIn(f'"site_url": "{official_url}"', config)
        self.assertIn("<https://newsfrontier.top>", readme)
        self.assertNotIn("frontier-pulse.jiumi674.workers.dev", index + config + readme)

    def test_security_headers_include_csp(self):
        headers = (ROOT / "public" / "_headers").read_text(encoding="utf-8")
        self.assertIn("Content-Security-Policy:", headers)
        self.assertIn("object-src 'none'", headers)
        self.assertIn("worker-src 'self'", headers)
        self.assertNotIn("/data/archive/search-index.json\n", headers)
        self.assertIn("/data/stream.json\n  Cache-Control: public, max-age=300", headers)
        self.assertIn("/data/research.json\n  Cache-Control: public, max-age=1800", headers)

    def test_personal_research_keywords_and_deepseek_translation_ui_are_safe(self):
        index = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "public" / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "public" / "assets" / "styles.css").read_text(encoding="utf-8")
        for element_id in (
            "researchKeywordPanel", "researchKeywordForm", "researchKeywordInput",
            "researchKeywordChips", "collectionKeywordChips", "mineResearchCount",
        ):
            self.assertIn(f'id="{element_id}"', index)
        self.assertIn("fp-research-keywords-v1", app)
        self.assertIn("最多保存 20 个论文关键词", app)
        self.assertIn("matchedResearchKeywords", app)
        self.assertIn("data-research-scope", index + app)
        self.assertIn("collectionKeywords", app)
        self.assertIn("DeepSeek 中文", app)
        self.assertIn("translationDiagnostics", app)
        self.assertIn("缺失 ID 与原因已写入公开状态数据", app)
        self.assertIn(".research-keyword-panel", styles)
        self.assertNotIn("DEEPSEEK_API_KEY", index + app + styles)

    def test_daily_selection_and_translation_health_are_independent(self):
        app = (ROOT / "public" / "assets" / "app.js").read_text(encoding="utf-8")
        self.assertIn("selectionMethod", app)
        self.assertIn("selectionStrategy", app)
        self.assertIn("selectionNotices", app)
        self.assertIn("translationStatus", app)
        self.assertIn("translatedItemCount", app)
        self.assertIn("AI 评分不可用，中文翻译已独立完成", app)
        self.assertIn("本期已完成多样性校正", app)
        self.assertIn("日报已更新，但部分中文翻译失败", app)

    def test_compact_homepage_and_historical_context_are_wired(self):
        index = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "public" / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "public" / "assets" / "styles.css").read_text(encoding="utf-8")
        self.assertNotIn("全球前沿情报，先看最重要的", index + app)
        self.assertNotIn("每日十条重点事件，先呈现必读内容", index + app)
        self.assertIn("今日前沿态势", index + app)
        self.assertIn("normalizeHistoryContext", app)
        self.assertIn("renderHistoryContext", app)
        self.assertIn("查看事件脉络与证据", app)
        self.assertIn("spotlight-backdrop", app + styles)
        self.assertIn("history-timeline", app + styles)
        self.assertIn("历史关联", app)

    def test_data_workflows_share_lock_and_retry_conflict_safe_rebase(self):
        workflows = [
            (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
            for name in ("daily-news.yml", "stream-update.yml")
        ]
        for workflow in workflows:
            self.assertIn("group: frontier-data-main", workflow)
            self.assertIn("cancel-in-progress: false", workflow)
            self.assertIn("for attempt in 1 2 3; do", workflow)
            self.assertIn("git rebase -X theirs origin/main", workflow)
            self.assertIn("main changed during push; retrying publication", workflow)


if __name__ == "__main__":
    unittest.main()
