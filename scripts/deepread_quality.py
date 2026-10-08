"""Reader completeness is independent of generation diagnostics."""
from __future__ import annotations

import copy
import re
from datetime import date

from evidence_trace import validate_deepread_trace, valid_display_translation, valid_prose_translation
from reader_quality import assess_admissibility, chinese_reader_text, metadata_filler


def normalize_legacy_deepread(article):
    """Adapt presentation notes without changing captured evidence or the archive."""
    result = copy.deepcopy(article)
    if not isinstance(result, dict):
        return result
    for event in result.get('events', []):
        display = event.get('displayTranslation')
        if not isinstance(display, dict) or not metadata_filler(display.get('summary')):
            continue
        sentences = re.split(r'(?<=[。！？])\s*', display.get('summary', ''))
        note_start = re.compile(r'^(?:现有元数据|元数据未(?:提供|说明)|未提取到可引用的正文|'
                                r'未提供更多(?:摘要|信息|细节)|这条新闻来自|现有(?:信息|报道)(?:仅包含|未提供)|'
                                r'目前披露的信息仅涉及|文章.{0,180}(?:最初发表于|最先发表于))')
        summary = ' '.join(s for s in sentences if not note_start.search(s.strip())).strip()
        repaired = {**event, 'summary':event.get('excerpt', ''),
                    'displayTranslation':{**display, 'summary':summary}}
        # All original title/summary/reference bindings and translation guards
        # still apply. A note embedded in a factual sentence is not repaired.
        if summary and valid_display_translation(repaired):
            event['displayTranslation'] = repaired['displayTranslation']
    return result


def display_text(value, refs=None):
    raw = value.get('text', '')
    display = value.get('displayTranslation')
    if valid_prose_translation(display, raw, refs if refs is not None else value.get('evidenceIds')):
        return display['text']
    return raw


def validate_chapter_prose(chapter, seen=None):
    seen = set() if seen is None else seen
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


def validate_complete(article):
    if isinstance(article, dict) and article.get('generationRevision', 0) >= 13:
        from deepread_topic_quality import validate_topic_article
        return validate_topic_article(article, complete=True)
    if not isinstance(article, dict):
        raise ValueError('invalid-article')
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
        for news_id in chapter['newsIds']:
            event = by_id[news_id]
            if heading == event['title'] and valid_display_translation({**event, 'summary':event['excerpt']}):
                heading = event['displayTranslation']['title']
                break
        if not chinese_reader_text(heading) or not chinese_reader_text(chapter.get('angle')):
            raise ValueError('reader-heading-invalid')
        validate_chapter_prose(chapter, seen)
    observations = article.get('observations', [])
    if not 2 <= len(observations) <= 3 or any(not chinese_reader_text(display_text(o, [s['evidenceId'] for s in o['supports']])) for o in observations):
        raise ValueError('reader-observation-invalid')


def choose_readable_deepread(draft, previous, publication_date):
    if isinstance(draft, dict) and draft.get('generationRevision', 0) >= 13:
        from deepread_topic_quality import choose_topic_publication
        return choose_topic_publication(draft, previous, publication_date)
    draft = normalize_legacy_deepread(draft)
    diagnostics = generation_diagnostics(draft)
    try:
        validate_complete(draft)
        if draft.get('editionDate') != publication_date:
            raise ValueError('wrong-edition')
        failures = []
    except (ValueError, TypeError, KeyError) as exc:
        failures = [str(exc)]
    if not failures:
        result = copy.deepcopy(draft)
        if result.get('generationStatus') != 'ok':
            result['generationAttemptStatus'] = result.get('generationStatus')
        result['generationStatus'] = 'ok'
        result.update(readerStatus='complete', publicationEditionDate=publication_date, qualityFailures=[])
        return result
    for candidate in sorted((p for p in previous if isinstance(p, dict)), key=lambda p:str(p.get('editionDate', '')), reverse=True):
        try:
            age = (date.fromisoformat(publication_date) - date.fromisoformat(candidate.get('editionDate', ''))).days
        except (ValueError, TypeError):
            continue
        if not 0 <= age <= 1:
            continue
        try:
            candidate = normalize_legacy_deepread(candidate)
            validate_complete(candidate)
        except (ValueError, TypeError, KeyError):
            continue
        result = copy.deepcopy(candidate)
        result.pop('releaseId', None)
        if result.get('generationStatus') != 'ok':
            result['generationAttemptStatus'] = result.get('generationStatus')
        result.update(generationStatus='ok', readerStatus='retained', publicationEditionDate=publication_date,
                      qualityFailures=failures, generationDiagnostics=diagnostics)
        return result
    return {'schemaVersion':2, 'generationRevision':12, 'editionDate':publication_date,
        'publicationEditionDate':publication_date, 'generatedAt':draft.get('generatedAt') if isinstance(draft,dict) else None,
        'headline':f'每日深读｜{publication_date}', 'lead':'本期深读生成未通过校验。',
        'generationStatus':'unavailable', 'readerStatus':'unavailable', 'qualityFailures':failures,
        'generationDiagnostics':diagnostics,
        'events':[], 'chapters':[], 'observations':[], 'eventCount':0, 'candidateCount':0,
        'sourceCount':0, 'warnings':diagnostics.get('warnings', []) + ['今日未通过内容校验，暂无可沿用的完整版。']}


def generation_diagnostics(draft):
    if not isinstance(draft, dict):
        return {'generationStatus':'invalid'}
    keys = ('generationStatus', 'generatedAt', 'candidateCount', 'eventCount', 'sourceCount',
            'warnings', 'recoveryDiagnostics', 'contentFailures', 'selectionDiagnostics', 'qualityMetrics')
    return {key:copy.deepcopy(draft[key]) for key in keys if key in draft}


def deepread_status(article, publication_date):
    """Deep read failures are independent of a successfully published daily brief."""
    status = article.get('readerStatus')
    failures = list(article.get('qualityFailures', []))
    try:
        validate_readable(article, publication_date)
    except (ValueError, KeyError, TypeError) as exc:
        status = 'unavailable'
        failures.append(str(exc))
    state = 'ok' if status == 'complete' else 'degraded' if status in {'retained','partial','brief'} else 'failed'
    error = 'deepread-'+status if status in {'retained','partial','brief'} else 'deepread-unavailable'
    partial_message=('合格主题已发布，篇幅尚未达到完整版目标。'
        if article.get('topicPlan') and len(article.get('chapters',[])) == len(article['topicPlan'])
        else '已发表合格主题，其余主题待恢复。')
    return {'state':state, 'errorCode':None if state == 'ok' else error,
            'editionDate':publication_date, 'contentEditionDate':article.get('editionDate'),
            'readerStatus':status, 'qualityFailures':failures,
            'message':'深读已通过正文与证据校验。' if state == 'ok' else '今日深读未更新，沿用一天内的历史完整版。' if status == 'retained' else partial_message if status == 'partial' else '当日简讯已发布，深读正文待恢复。' if status == 'brief' else '深读生成失败，暂无合格内容；日报状态独立记录。',
            'diagnostics':copy.deepcopy(article.get('generationDiagnostics') or generation_diagnostics(article))}


def validate_readable(article, publication_date):
    if article.get('generationRevision', 0) >= 13:
        from deepread_topic_quality import validate_topic_publication
        return validate_topic_publication(article, publication_date)
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
    age = (date.fromisoformat(publication_date) - date.fromisoformat(article.get('editionDate', ''))).days
    if status == 'retained' and 0 <= age <= 1 and article.get('qualityFailures'):
        return
    raise ValueError('Reader status/date differs')
