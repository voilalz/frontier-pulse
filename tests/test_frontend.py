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


if __name__ == "__main__":
    unittest.main()
