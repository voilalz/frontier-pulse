"""Lay out a daily deep read for a WeChat Official Account draft.

WeChat article bodies accept inline styles only, do not allow ordinary
outbound links, and need cleared images. This adapter therefore turns the
editorial JSON into plain styled HTML with numbered references at the end and
no source images. It never publishes anything; a person pastes or uploads the
draft and reviews it before sending.
"""
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

FACT_TYPES = {'paragraph', 'background', 'change'}
ANALYSIS_LABEL = {'analysis': '编辑分析', 'comparison': '比较', 'watch': '接下来看什么'}
AI_NOTICE = '本文由 AI 辅助生成：事实句均标注来源，分析部分为编辑判断，不等同于独立证实；发布前经人工审核。'
DIGEST_LIMIT = 120

STYLE = {
    'body': 'font-size:16px;line-height:1.85;color:#222;letter-spacing:0.02em;',
    'lead': 'margin:0 0 24px;padding:14px 16px;background:#f6f5f1;border-radius:6px;color:#3d3d3d;font-size:15px;',
    'h2': 'margin:32px 0 12px;font-size:19px;font-weight:bold;color:#111;line-height:1.5;',
    'kicker': 'margin:32px 0 4px;font-size:13px;color:#8a6d3b;letter-spacing:0.08em;',
    'p': 'margin:0 0 16px;',
    'analysis': 'margin:0 0 16px;padding-left:12px;border-left:3px solid #b8955a;',
    'label': 'display:block;margin-bottom:2px;font-size:12px;color:#8a6d3b;letter-spacing:0.08em;',
    'ref': 'font-size:11px;color:#8a8a8a;vertical-align:super;margin-left:1px;',
    'refs-title': 'margin:36px 0 8px;font-size:15px;font-weight:bold;color:#555;',
    'refs': 'margin:0;padding:0;list-style:none;font-size:12px;line-height:1.7;color:#777;word-break:break-all;',
    'notice': 'margin:28px 0 0;padding-top:12px;border-top:1px solid #e5e5e5;font-size:12px;color:#999;',
}


def _esc(value):
    return html.escape(str(value or ''), quote=False)


def _block_text(block):
    """Revision 13 keeps Chinese sentences; older editions carry a display translation."""
    if block.get('sentences'):
        return ''.join(s.get('text', '') for s in block['sentences'])
    translated = (block.get('displayTranslation') or {}).get('text')
    return translated or block.get('text', '')


def _block_refs(block):
    refs = [ref for s in block.get('sentences', []) for ref in s.get('evidenceIds', [])]
    return list(dict.fromkeys(refs or block.get('evidenceIds', [])))


def _title_of(event):
    return (event.get('displayTranslation') or {}).get('title') or event.get('title') or event.get('originalTitle', '')


class References:
    """Number sources by first citation; WeChat shows them as plain text at the end."""
    def __init__(self, events):
        self.by_evidence, self.order, self.rows = {}, {}, []
        for event in events:
            sources = {s.get('url'): s.get('name', '') for s in event.get('sources', [])}
            rows = list(event.get('evidenceRecords', []))
            for prior in event.get('history', []):
                prior_sources = {s.get('url'): s.get('name', '') for s in prior.get('sources', [])}
                for row in prior.get('evidenceRecords', []):
                    rows.append({**row, '_name': prior_sources.get(row['url'], prior.get('source', '')),
                                 '_title': prior.get('title', ''), '_date': prior.get('editionDate', '')})
            for row in rows:
                self.by_evidence[row['evidenceId']] = {
                    'url': row['url'], 'name': row.get('_name') or sources.get(row['url'], ''),
                    'title': row.get('_title') or _title_of(event),
                    'date': row.get('_date') or str(event.get('publishedAt', ''))[:10]}

    def numbers(self, refs):
        result = []
        for ref in refs:
            source = self.by_evidence.get(ref)
            if not source:
                continue
            if source['url'] not in self.order:
                self.order[source['url']] = len(self.rows) + 1
                self.rows.append(source)
            result.append(self.order[source['url']])
        return sorted(set(result))


def _marker(numbers):
    return ''.join(f'<span style="{STYLE["ref"]}">[{n}]</span>' for n in numbers)


def _digest(article):
    chapters = article.get('chapters') or []
    text = (chapters[0].get('angle') if chapters else '') or article.get('lead', '')
    text = re.sub(r'\s+', ' ', text).strip()
    return text if len(text) <= DIGEST_LIMIT else text[:DIGEST_LIMIT - 1] + '…'


def build_wechat_draft(article):
    """Return title, digest and inline-styled body HTML for one edition."""
    chapters = [c for c in article.get('chapters', []) if c.get('blocks')]
    if not chapters:
        raise ValueError('edition has no published chapters')
    refs = References(article.get('events', []))
    parts = [f'<section style="{STYLE["body"]}">']
    main = chapters[0]
    if main.get('angle'):
        parts.append(f'<p style="{STYLE["lead"]}">{_esc(main["angle"])}</p>')
    for index, chapter in enumerate(chapters):
        if index:
            parts.append(f'<p style="{STYLE["kicker"]}">短篇</p>')
            parts.append(f'<h2 style="{STYLE["h2"]}">{_esc(chapter.get("title"))}</h2>')
            if chapter.get('angle'):
                parts.append(f'<p style="{STYLE["p"]}color:#555;">{_esc(chapter["angle"])}</p>')
        previous = None
        for block in chapter['blocks']:
            kind = block.get('type', 'paragraph')
            text = _esc(_block_text(block)) + _marker(refs.numbers(_block_refs(block)))
            if kind in FACT_TYPES:
                parts.append(f'<p style="{STYLE["p"]}">{text}</p>')
            else:
                # One label per run of the same analysis type keeps the page calm.
                label = '' if kind == previous else f'<span style="{STYLE["label"]}">{ANALYSIS_LABEL.get(kind, "编辑分析")}</span>'
                parts.append(f'<p style="{STYLE["analysis"]}">{label}{text}</p>')
            previous = kind
    if refs.rows:
        parts.append(f'<p style="{STYLE["refs-title"]}">参考资料</p>')
        parts.append(f'<ol style="{STYLE["refs"]}">')
        for number, row in enumerate(refs.rows, 1):
            line = '，'.join(x for x in (_esc(row['name']), f'《{_esc(row["title"])}》' if row['title'] else '', _esc(row['date'])) if x)
            parts.append(f'<li>[{number}] {line}<br>{_esc(row["url"])}</li>')
        parts.append('</ol>')
    parts.append(f'<p style="{STYLE["notice"]}">{_esc(AI_NOTICE)}</p>')
    parts.append('</section>')
    return {'title': main.get('title') or article.get('headline', ''), 'digest': _digest(article),
            'editionDate': article.get('editionDate', ''), 'html': '\n'.join(parts),
            'referenceCount': len(refs.rows),
            'coverNote': '封面请用自制图或已授权图片（首图 2.35:1，分享图 1:1）；不要直接使用来源网站配图。'}


def preview_page(draft):
    """A phone-width page for reviewing the draft before it goes to WeChat."""
    meta = f'<p>摘要：{_esc(draft["digest"])}</p><p>{_esc(draft["coverNote"])}</p>'
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>公众号预览 {_esc(draft["editionDate"])}</title></head>'
            '<body style="margin:0;background:#ededed;font-family:-apple-system,BlinkMacSystemFont,\'PingFang SC\',\'Noto Sans CJK SC\',sans-serif;">'
            '<main style="max-width:420px;margin:0 auto;background:#fff;padding:24px 18px 40px;">'
            f'<h1 style="font-size:22px;line-height:1.45;margin:0 0 8px;color:#111;">{_esc(draft["title"])}</h1>'
            f'<p style="font-size:13px;color:#8a8a8a;margin:0 0 20px;">智域前沿 · 深读 · {_esc(draft["editionDate"])}</p>'
            f'{draft["html"]}'
            f'<aside style="margin-top:28px;padding:12px;background:#fafafa;font-size:12px;color:#888;">{meta}</aside>'
            '</main></body></html>')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('edition', type=Path, help='a deepread JSON file, e.g. public/data/deepread/2026-10-08.json')
    parser.add_argument('-o', '--output', type=Path, required=True, help='where to write the body HTML')
    parser.add_argument('--preview', type=Path, help='also write a phone-width preview page')
    args = parser.parse_args(argv)
    draft = build_wechat_draft(json.loads(args.edition.read_text()))
    args.output.write_text(draft['html'])
    args.output.with_suffix('.json').write_text(json.dumps(
        {k: v for k, v in draft.items() if k != 'html'}, ensure_ascii=False, indent=2))
    if args.preview:
        args.preview.write_text(preview_page(draft))
    print(f'{draft["title"]} · {draft["referenceCount"]} 条参考资料 · {args.output}')


if __name__ == '__main__':
    main()
