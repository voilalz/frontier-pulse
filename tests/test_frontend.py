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

    def test_security_headers_include_csp(self):
        headers = (ROOT / "public" / "_headers").read_text(encoding="utf-8")
        self.assertIn("Content-Security-Policy:", headers)
        self.assertIn("object-src 'none'", headers)


if __name__ == "__main__":
    unittest.main()
