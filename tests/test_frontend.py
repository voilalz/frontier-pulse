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
        self.assertIn("./assets/app.js?v=1.5.1", index)
        self.assertIn("./assets/styles.css?v=1.5.1", index)
        self.assertIn('event.preventDefault();\n      await switchView(viewButton.dataset.view);', app)
        self.assertIn('request.mode === "navigate"', worker)
        self.assertIn("frontier-pulse-", worker)
        self.assertIn("v1.5.1", worker)
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

    def test_security_headers_include_csp(self):
        headers = (ROOT / "public" / "_headers").read_text(encoding="utf-8")
        self.assertIn("Content-Security-Policy:", headers)
        self.assertIn("object-src 'none'", headers)
        self.assertIn("worker-src 'self'", headers)
        self.assertNotIn("/data/archive/search-index.json\n", headers)
        self.assertIn("/data/stream.json\n  Cache-Control: public, max-age=300", headers)
        self.assertIn("/data/research.json\n  Cache-Control: public, max-age=1800", headers)


if __name__ == "__main__":
    unittest.main()
