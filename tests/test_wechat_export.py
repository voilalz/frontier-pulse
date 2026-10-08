"""WeChat draft layout: inline styles, references at the end, no links or images."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from wechat_export import AI_NOTICE, DIGEST_LIMIT, build_wechat_draft, preview_page


class WeChatDraftTests(unittest.TestCase):
    def setUp(self):
        self.article = json.loads((ROOT / 'public/data/deepread/2026-10-08.json').read_text())
        self.draft = build_wechat_draft(self.article)

    def test_body_has_no_links_images_scripts_or_classes(self):
        body = self.draft['html']
        self.assertNotRegex(body, r'<(?:a|img|script|style|link)\b')
        self.assertNotIn('class=', body)

    def test_every_citation_has_a_numbered_reference_with_its_url(self):
        body = self.draft['html']
        cited = {int(n) for n in re.findall(r'\[(\d+)\]</span>', body)}
        self.assertEqual(cited, set(range(1, self.draft['referenceCount'] + 1)))
        for event in self.article['events']:
            if any(set(b['evidenceIds']) & {r['evidenceId'] for r in event['evidenceRecords']}
                   for c in self.article['chapters'] for b in c['blocks']):
                self.assertIn(event['sources'][0]['url'], body)

    def test_analysis_is_labelled_and_the_ai_notice_closes_the_draft(self):
        self.assertIn('编辑分析', self.draft['html'])
        self.assertIn(AI_NOTICE, self.draft['html'])
        self.assertLessEqual(len(self.draft['digest']), DIGEST_LIMIT)
        self.assertEqual(self.draft['title'], self.article['chapters'][0]['title'])

    def test_source_text_is_escaped(self):
        article = json.loads(json.dumps(self.article))
        article['chapters'][0]['blocks'][0]['sentences'][0]['text'] = '<script>alert(1)</script>测试。'
        self.assertNotIn('<script>', build_wechat_draft(article)['html'])

    def test_older_translated_editions_still_lay_out(self):
        older = json.loads((ROOT / 'public/data/deepread/2026-10-07.json').read_text())
        draft = build_wechat_draft(older)
        self.assertIn('五角大楼', draft['html'])
        self.assertIn('<!doctype html>', preview_page(draft))

    def test_an_edition_without_chapters_is_refused(self):
        with self.assertRaises(ValueError):
            build_wechat_draft({'chapters': [], 'events': []})


if __name__ == '__main__':
    unittest.main()
