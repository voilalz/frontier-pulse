"""Revision 13: sentence evidence, editorial analysis, and chapter publication."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import date

from evidence_trace import (validate_evidence, validate_claim_refs, valid_display_translation,
                            _prose_quantities, _translation_negation_valid, _TRANSLATION_SCOPE,
                            _without_calendar_may, safe_title, safe_url)
from reader_quality import chinese_reader_text
from deepread_editorial_signals import is_political_policy

REVISION = 13
FACT_TYPES = {'paragraph', 'background', 'change'}
ANALYSIS_TYPES = {'analysis', 'comparison', 'watch'}
CAUSAL = re.compile(r'导致|造成|促使|使得|因而|因此|从而|归因于|致使|迫使|因为|\b(?:caused?|therefore|because)\b', re.I)
END = re.compile(r'[。！？.!?][”"’）)]?$')


def han_count(text):
    return len(re.findall(r'[\u3400-\u9fff]', text or ''))


def record_index(events):
    records, owners, historical = {}, {}, set()
    for event in events:
        for row in event.get('evidenceRecords', []):
            records[row['evidenceId']] = row
            owners.setdefault(row['evidenceId'], set()).add(event['newsId'])
        for prior in event.get('history', []):
            for row in prior.get('evidenceRecords', []):
                records[row['evidenceId']] = row
                owners.setdefault(row['evidenceId'], set()).add(event['newsId'])
                historical.add(row['evidenceId'])
    return records, owners, historical


def sentence_binding(text, role, refs, records):
    material = '\n'.join(ref+'\t'+records[ref]['text']+'\t'+records[ref]['url'] for ref in refs)
    return hashlib.sha256((role+'\n'+text+'\n'+material).encode()).hexdigest()


def chapter_binding(chapter):
    material=[chapter['title'],chapter['angle'],chapter['newsIds'],
        [[b['type'],b['newsIds'],[[s['text'],s['evidenceIds']] for s in b['sentences']]] for b in chapter['blocks']]]
    return hashlib.sha256(json.dumps(material,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def rule_issue(text, role, refs, records, attribution=False):
    """Cheap guards are diagnostics; they never replace the semantic check."""
    if (not isinstance(text, str) or not 4 <= len(text) <= 700 or text != text.strip()
            or not chinese_reader_text(text)
            or re.search(r'[<>\x00-\x1f]|(?:https?|javascript|data|file)\s*:', text, re.I)):
        return 'language-or-format'
    if not isinstance(refs, list) or not 1 <= len(refs) <= 3 or len(set(refs)) != len(refs) or any(ref not in records for ref in refs):
        return 'evidence-reference'
    source = ' '.join(records[ref]['text'] for ref in refs)
    quantities = _prose_quantities(text) - _prose_quantities(source)
    if quantities:
        return 'quantity:'+','.join(sorted(quantities))[:100]
    if role == 'analysis':
        if CAUSAL.search(text):
            return 'analysis-causal-assertion'
        if re.search(r'[“”「」『』"]', text) and not all(
                quote in source for quote in re.findall(r'[“「『"]([^”」』"]+)[”」』"]', text)):
            return 'analysis-new-quotation'
        return ''
    if not END.search(text) or text.endswith(('…', '...')):
        return 'sentence-truncated'
    if not _translation_negation_valid(text, source):
        return 'negated-action'
    # A Chinese paraphrase can omit unrelated clauses. Only explicit source
    # uncertainty is guarded here; the independent checker judges entailment.
    scoped = _without_calendar_may(source)
    for label, pattern in zip(('planned','limited','simulation','preliminary','partial','negation'), _TRANSLATION_SCOPE):
        if pattern.search(scoped) and not pattern.search(text):
            if (label == 'planned' and re.search(r'\bcould\b', scoped, re.I)
                    and not re.search(r'\b(?:plans?|planned|will|may|might|expected|scheduled)\b', scoped, re.I)
                    and re.search(r'可以|能够', text) and not re.search(r'已|完成|成功', text)):
                continue
            return 'qualifier:'+label
    if attribution and not re.search(r'据|根据|称|表示|报道|披露|介绍|公告|新闻稿', text):
        return 'attribution-missing'
    return ''


def proof_valid(text, role, refs, records, proof):
    return (isinstance(proof, dict) and proof.get('version') == 1
            and proof.get('provider') in {'deepseek','openai'} and proof.get('verdict') == 'supported'
            and proof.get('binding') == sentence_binding(text, role, refs, records))


def validate_topic_chapter(chapter, events):
    by_news = {e['newsId']:e for e in events}
    members = chapter.get('newsIds', [])
    if not 1 <= len(members) <= 3 or len(set(members)) != len(members) or any(ref not in by_news for ref in members):
        raise ValueError('chapter-event-reference')
    records, owners, historical = record_index([by_news[ref] for ref in members])
    for key in ('title','angle'):
        refs = chapter.get('framingEvidenceIds', [])
        issue = rule_issue(chapter.get(key), 'analysis', refs, records)
        if issue or not proof_valid(chapter.get(key), 'analysis', refs, records, chapter.get(key+'Check')):
            raise ValueError('framing-'+(issue or 'semantic-binding'))
    blocks = chapter.get('blocks', [])
    if not 3 <= len(blocks) <= 14:
        raise ValueError('paragraph-count')
    facts, analyses, seen, current_refs = 0, 0, set(), set()
    for block in blocks:
        kind, news_ids = block.get('type'), block.get('newsIds', [])
        if kind not in FACT_TYPES | ANALYSIS_TYPES or not news_ids or not set(news_ids) <= set(members):
            raise ValueError('block-kind-or-event-reference')
        sentences = block.get('sentences', [])
        if not 1 <= len(sentences) <= 8 or block.get('text') != ''.join(s.get('text','') for s in sentences):
            raise ValueError('sentence-text-binding')
        role = 'fact' if kind in FACT_TYPES else 'analysis'
        for sentence in sentences:
            text, refs = sentence.get('text'), sentence.get('evidenceIds')
            attributed = role == 'fact' and any(by_news[n].get('evidenceLevel') == 'primary' for n in news_ids)
            issue = rule_issue(text, role, refs, records, attributed)
            if issue:
                raise ValueError(issue)
            if any(not owners[ref] & set(news_ids) for ref in refs):
                raise ValueError('foreign-evidence-owner')
            if kind == 'paragraph' and any(ref in historical for ref in refs):
                raise ValueError('historical-evidence-as-current')
            if kind == 'change' and (not set(refs) & historical or not set(refs) - historical):
                raise ValueError('change-needs-current-and-history')
            if not proof_valid(text, role, refs, records, sentence.get('semanticCheck')):
                raise ValueError('semantic-binding')
            if role == 'fact':
                normalized = re.sub(r'\W','',text).casefold()
                if normalized in seen:
                    raise ValueError('repeated-fact')
                seen.add(normalized)
                facts += 1
                if kind == 'paragraph':
                    current_refs.update(refs)
            elif kind in {'analysis','comparison'}:
                analyses += 1
    if facts < 2 or len(current_refs) < 2 or not analyses:
        raise ValueError('facts-or-analysis-insufficient')
    if han_count(''.join(b['text'] for b in blocks)) < 300:
        raise ValueError('topic-too-short')
    review=chapter.get('editorialCheck',{})
    if (review.get('version') != 1 or review.get('provider') not in {'deepseek','openai'}
            or review.get('verdict') != 'ready' or review.get('binding') != chapter_binding(chapter)):
        raise ValueError('editorial-depth-binding')


def validate_source_event(event, edition):
    validate_evidence(event.get('evidenceRecords'))
    sources=event.get('sources',[])
    urls={s['url'] for s in sources}
    if (not sources or any(not safe_url(url) for url in urls) or not event.get('originalTitle')
            or event.get('title') != safe_title(event.get('title'),event['originalTitle'],event['evidenceRecords'])
            or is_political_policy(event) or not event['evidenceRecords']
            or any(r['url'] not in urls for r in event['evidenceRecords'])
            or not validate_claim_refs(event.get('excerpt'),event.get('summaryEvidenceRefs'),event['evidenceRecords'])):
        raise ValueError('event-source-binding')
    for prior in event.get('history',[]):
        if date.fromisoformat(prior['editionDate']) >= edition:
            raise ValueError('historical-date')
        validate_evidence(prior['evidenceRecords'])
        prior_urls={s['url'] for s in prior['sources']}
        if (not prior['evidenceRecords'] or any(not safe_url(url) for url in prior_urls)
                or any(r['url'] not in prior_urls for r in prior['evidenceRecords'])):
            raise ValueError('historical-source-binding')


def validate_briefs(article, used):
    events={e['newsId']:e for e in article.get('events',[])}
    seen=set(used)
    for brief in article.get('briefs',[]):
        refs=brief.get('newsIds',[])
        if (len(refs)!=1 or refs[0] not in events or refs[0] in seen
                or brief != safe_brief(events[refs[0]])):
            raise ValueError('brief-source-binding')
        seen.add(refs[0])
    if seen != set(events):
        raise ValueError('brief-catalog-count')


def validate_topic_article(article, complete=False):
    if article.get('schemaVersion') != 2 or article.get('generationRevision') != REVISION:
        raise ValueError('topic-revision')
    edition = date.fromisoformat(article.get('editionDate',''))
    events = article.get('events', [])
    if len(events) > 6 or article.get('eventCount') != len(events) or not 0 <= article.get('candidateCount', 0) <= 12:
        raise ValueError('event-count')
    by_news = {e['newsId']:e for e in events}
    if len(by_news) != len(events) or len({e['eventId'] for e in events}) != len(events):
        raise ValueError('repeated-event')
    for event in events:
        validate_source_event(event,edition)
    chapters = article.get('chapters', [])
    if not 1 <= len(chapters) <= 3:
        raise ValueError('topic-count')
    used = []
    for chapter in chapters:
        validate_topic_chapter(chapter, events)
        used.extend(chapter['newsIds'])
    if len(set(used)) != len(used):
        raise ValueError('event-in-multiple-topics')
    validate_briefs(article,used)
    records, _, _ = record_index(events)
    for key in ('headline','lead'):
        refs = article.get('framingEvidenceIds', [])
        issue = rule_issue(article.get(key), 'analysis', refs, records)
        if issue or not proof_valid(article.get(key), 'analysis', refs, records, article.get(key+'Check')):
            raise ValueError('article-framing-'+(issue or 'semantic-binding'))
    if complete:
        count = han_count(''.join(b['text'] for c in chapters for b in c['blocks']))
        if article.get('briefs') or not 1500 <= count <= 3000 or han_count(''.join(b['text'] for b in chapters[0]['blocks'])) < 800:
            raise ValueError('full-depth-target')


def safe_brief(event):
    item = {**event, 'summary':event.get('excerpt')}
    if valid_display_translation(item):
        title = event['displayTranslation']['title']
    elif chinese_reader_text(event.get('title')):
        title = event['title']
    else:
        return None
    return {'newsIds':[event['newsId']], 'title':title, 'sources':copy.deepcopy(event['sources'])}


def choose_topic_publication(draft, previous, publication_date):
    result = copy.deepcopy(draft)
    failures = list(result.get('contentFailures', []))
    accepted, briefs = [], []
    by_news = {e['newsId']:e for e in result.get('events', [])}
    for chapter in result.get('chapters', []):
        try:
            validate_topic_chapter(chapter, list(by_news.values()))
            accepted.append(chapter)
        except (ValueError, TypeError, KeyError) as exc:
            failures.append({'chapterId':chapter.get('id',''), 'rule':str(exc)})
    accepted_ids = {ref for chapter in accepted for ref in chapter['newsIds']}
    for event in by_news.values():
        if event['newsId'] not in accepted_ids and (brief := safe_brief(event)):
            briefs.append(brief)
    result.update(chapters=accepted, briefs=briefs, observations=[],
                  publicationEditionDate=publication_date, qualityFailures=failures)
    if accepted:
        kept_ids = accepted_ids | {ref for brief in briefs for ref in brief['newsIds']}
        result['events'] = [e for e in by_news.values() if e['newsId'] in kept_ids]
        result['eventCount'] = len(result['events'])
        result['sourceCount'] = len({s['url'] for e in result['events'] for s in e['sources']})
        first = accepted[0]
        result.update(headline=first['title'], lead=first['angle'], framingEvidenceIds=first['framingEvidenceIds'],
                      headlineCheck=first['titleCheck'], leadCheck=first['angleCheck'])
        try:
            validate_topic_article(result)
        except (ValueError, TypeError, KeyError) as exc:
            # Global evidence corruption cannot be excused by chapter survival.
            failures.append({'rule':str(exc)})
            accepted = []
        else:
            try:
                validate_topic_article(result, complete=True)
                result.update(readerStatus='complete', generationStatus='ok')
            except ValueError:
                result.update(readerStatus='partial', generationStatus='partial')
            return result
    # A completed same-day publication also wins over a failed retry.
    from deepread_quality import normalize_legacy_deepread, validate_complete
    for candidate in sorted((p for p in previous if isinstance(p, dict)), key=lambda p:str(p.get('editionDate','')), reverse=True):
        try:
            age = (date.fromisoformat(publication_date) - date.fromisoformat(candidate.get('editionDate',''))).days
            if not 0 <= age <= 1:
                continue
            candidate = normalize_legacy_deepread(candidate)
            if age == 0 and candidate.get('generationRevision') == REVISION and candidate.get('readerStatus') == 'partial':
                validate_topic_article(candidate)
                preserved = copy.deepcopy(candidate)
                preserved.pop('releaseId',None)
                preserved.update(publicationEditionDate=publication_date,
                    qualityFailures=[*preserved.get('qualityFailures',[]), *failures],
                    generationDiagnostics={k:copy.deepcopy(draft[k]) for k in ('recoveryDiagnostics','contentFailures','selectionDiagnostics') if k in draft})
                return preserved
            validate_complete(candidate)
        except (ValueError, KeyError, TypeError):
            continue
        retained = copy.deepcopy(candidate)
        retained.pop('releaseId', None)
        retained.update(readerStatus='retained', publicationEditionDate=publication_date, qualityFailures=failures or ['generation-failed'],
                        generationDiagnostics={k:copy.deepcopy(draft[k]) for k in ('recoveryDiagnostics','contentFailures','selectionDiagnostics') if k in draft})
        return retained
    # Only source-bound Chinese titles survive the all-chapters-failed route.
    good_events = []
    for event in by_news.values():
        try:
            validate_source_event(event,date.fromisoformat(publication_date))
            if safe_brief(event):
                good_events.append(event)
        except (ValueError, KeyError, TypeError):
            continue
    good_ids = {e['newsId'] for e in good_events}
    result.update(editionDate=publication_date, events=good_events, eventCount=len(good_events), chapters=[],
                  headline=f'每日深读｜{publication_date}', lead='今日深读正文尚未完成，先列出有来源的中文简讯。',
                  briefs=[b for b in briefs if set(b['newsIds']) <= good_ids],
                  readerStatus='brief' if good_events else 'unavailable', generationStatus='partial' if good_events else 'unavailable',
                  qualityFailures=failures or ['generation-failed'])
    return result


def validate_topic_publication(article, publication_date):
    if article.get('publicationEditionDate') != publication_date:
        raise ValueError('topic-publication-date')
    status = article.get('readerStatus')
    if status in {'complete','partial'}:
        if article.get('editionDate') != publication_date:
            raise ValueError('topic-content-date')
        validate_topic_article(article, complete=status == 'complete')
        return
    if status == 'retained':
        age = (date.fromisoformat(publication_date) - date.fromisoformat(article.get('editionDate',''))).days
        if not 0 <= age <= 1 or not article.get('qualityFailures'):
            raise ValueError('retained-expired')
        validate_topic_article(article, complete=True)
        return
    if status in {'brief','unavailable'} and article.get('editionDate') == publication_date and article.get('chapters') == []:
        events=article.get('events',[])
        if (article.get('eventCount') != len(events) or len(events)>6 or not article.get('qualityFailures')
                or len({e['newsId'] for e in events}) != len(events)
                or len({e['eventId'] for e in events}) != len(events)):
            raise ValueError('brief-count-or-diagnostics')
        for event in events:
            validate_source_event(event,date.fromisoformat(publication_date))
            if not safe_brief(event):
                raise ValueError('brief-source-binding')
        validate_briefs(article,[])
        if (status=='unavailable' and events) or (status=='brief' and not events):
            raise ValueError('brief-reader-status')
        return
    raise ValueError('topic-reader-status')
