import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("send_digest", ROOT / "scripts" / "send_digest.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SendDigestTests(unittest.TestCase):
    def setUp(self):
        self.report = {
            "editionDate": "2026-07-17",
            "brief": {"headline": "今日 <重点>", "summary": "摘要 & 判断"},
            "items": [
                {
                    "id": f"item-{index}",
                    "title": f"测试新闻 {index}",
                    "summary": "仅依据公开信息生成的摘要。",
                    "keyFacts": ["事实一", "事实二"],
                    "category": "AI",
                    "source": "Example News",
                    "url": f"https://example.com/{index}",
                    "score": 80,
                    "confidence": "中",
                }
                for index in range(10)
            ],
        }

    def test_recipient_parsing_deduplicates_and_accepts_semicolons(self):
        result = MODULE.parse_recipients("Alice <alice@example.com>; bob@example.com, alice@example.com")
        self.assertEqual(result, ["alice@example.com", "bob@example.com"])

    def test_html_digest_escapes_content_and_contains_sources(self):
        rendered = MODULE.render_html(self.report, "https://news.example.com")
        self.assertIn("今日 &lt;重点&gt;", rendered)
        self.assertIn("摘要 &amp; 判断", rendered)
        self.assertIn("https://example.com/0", rendered)
        self.assertNotIn("今日 <重点>", rendered)

    def test_edition_link_uses_history_view(self):
        result = MODULE.edition_url("https://news.example.com/", "2026-07-17")
        self.assertEqual(result, "https://news.example.com/?view=history&date=2026-07-17")

    def test_message_hides_recipient_list(self):
        message = MODULE.build_message(self.report, "digest@example.com", "https://news.example.com")
        self.assertEqual(message["To"], "undisclosed-recipients:;")
        self.assertTrue(message.is_multipart())


if __name__ == "__main__":
    unittest.main()
