"""Reader completeness is independent of generation diagnostics."""
from __future__ import annotations

import copy
import re

from evidence_trace import validate_deepread_trace, valid_display_translation, valid_prose_translation
from reader_quality import assess_admissibility, chinese_reader_text


def display_text(value, refs=None):
    raw = value.get('text', '')
    display = value.get('displayTranslation')
    if valid_prose_translation(display, raw, refs if refs is not None else value.get('evidenceIds')):
        return display['text']
    return raw


def validate_complete(article):
    if not isinstance(article, dict) or article.get('generationStatus') != 'ok':
        raise ValueError('generation-incomplete')
    try:
        validate_deepread_trace(article)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('source-trace-invalid') from exc
    events, chapters = article.get('events', []), article.get('chapters', [])
    if (not 4 <= len(events) <= 6 or len(chapters) < 3
            or article.get('eventCount') != len(events)
            or len({e.get('eventId') for e in events}) != len(events)):
        raise ValueError('event-or-chapter-count')
    by_id = {e['newsId']:e for e in events}
    references = [ref for chapter in chapters for ref in chapter['newsIds']]
    if len(by_id) != len(events) or sorted(references) != sorted(by_id):
        raise ValueError('repeated-or-missing-event')
    if not all(chinese_reader_text(article.get(key)) for key in ['headline', 'lead']):
        raise ValueError('reader-framing-invalid')
    if not all(assess_admissibility(e)['eligible'] for e in events):
        raise ValueError('inadmissible-event')
    seen = set()
    for chapter in chapters:
        heading = chapter.get('title', '')
        if len(chapter['newsIds']) == 1:
            event = by_id[chapter['newsIds'][0]]
            if heading == event['title'] and valid_display_translation({**event, 'summary':event['excerpt']}):
                heading = event['displayTranslation']['title']
        if not chinese_reader_text(heading) or not chinese_reader_text(chapter.get('angle')):
            raise ValueError('reader-heading-invalid')
        paragraphs = [b for b in chapter.get('blocks', []) if b.get('type') == 'paragraph']
        if len(paragraphs) < 2:
            raise ValueError('chapter-needs-two-paragraphs')
        claims = set()
        for block in chapter['blocks']:
            text = display_text(block)
            if not chinese_reader_text(text) or not re.search(r'[。！？.!?][”"’）)]?$', text) or text.endswith(('…', '...')):
                raise ValueError('reader-prose-invalid-or-truncated')
            if block['type'] == 'paragraph':
                normalized = re.sub(r'\W', '', text)
                if len(re.findall(r'[\u3400-\u9fff]', text)) < 30 or normalized in seen:
                    raise ValueError('reader-paragraph-short-or-repeated')
                seen.add(normalized)
                claims.add(re.sub(r'\W', '', block['text']))
        if len(claims) < 2:
            raise ValueError('repeated-source-paragraph')
    observations = article.get('observations', [])
    if not 2 <= len(observations) <= 3 or any(not chinese_reader_text(display_text(o, [s['evidenceId'] for s in o['supports']])) for o in observations):
        raise ValueError('reader-observation-invalid')


def choose_readable_deepread(draft, previous, publication_date):
    try:
        validate_complete(draft)
        if draft.get('editionDate') != publication_date:
            raise ValueError('wrong-edition')
        failures = []
    except (ValueError, TypeError, KeyError) as exc:
        failures = [str(exc)]
    if not failures:
        result = copy.deepcopy(draft)
        result.update(readerStatus='complete', publicationEditionDate=publication_date, qualityFailures=[])
        return result
    for candidate in sorted((p for p in previous if isinstance(p, dict)), key=lambda p:str(p.get('editionDate', '')), reverse=True):
        if not candidate.get('editionDate') or candidate['editionDate'] > publication_date:
            continue
        try:
            validate_complete(candidate)
        except (ValueError, TypeError, KeyError):
            continue
        result = copy.deepcopy(candidate)
        result.pop('releaseId', None)
        result.update(readerStatus='retained', publicationEditionDate=publication_date, qualityFailures=failures)
        return result
    return {'schemaVersion':2, 'generationRevision':12, 'editionDate':publication_date,
        'publicationEditionDate':publication_date, 'generatedAt':draft.get('generatedAt') if isinstance(draft,dict) else None,
        'headline':f'每日深读｜{publication_date}', 'lead':'本期暂无合格的最新事件。',
        'generationStatus':'unavailable', 'readerStatus':'unavailable', 'qualityFailures':failures,
        'events':[], 'chapters':[], 'observations':[], 'eventCount':0, 'candidateCount':0,
        'sourceCount':0, 'warnings':['今日未通过内容校验，暂无可沿用的完整版。']}


def validate_readable(article, publication_date):
    if article.get('publicationEditionDate') != publication_date:
        raise ValueError('Reader publication date differs')
    status = article.get('readerStatus')
    if status == 'unavailable':
        if (article.get('generationStatus') != 'unavailable' or article.get('editionDate') != publication_date
                or any(article.get(key) != [] for key in ['events','chapters','observations'])
                or article.get('eventCount') != 0 or not article.get('qualityFailures')):
            raise ValueError('Unavailable reader contains unqualified content')
        return
    validate_complete(article)
    if status == 'complete' and article.get('editionDate') == publication_date and article.get('qualityFailures') == []:
        return
    if status == 'retained' and article.get('editionDate', '') <= publication_date and article.get('qualityFailures'):
        return
    raise ValueError('Reader status/date differs')
