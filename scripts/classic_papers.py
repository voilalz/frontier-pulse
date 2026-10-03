"""Offline fixed-calendar selection from accepted classic-paper guides."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from classic_catalog import audit_directory
from classic_guides import text_counts, validate_guides

DOMAINS = ('AI', 'SLAM', 'GNC', 'CV', 'UAV')
PAIRS = (('AI', 'SLAM'), ('GNC', 'CV'), ('UAV', 'AI'), ('SLAM', 'GNC'), ('CV', 'UAV'))
BEIJING = ZoneInfo('Asia/Shanghai')
ANCHOR = date(2026, 9, 30)
RULE = 'classic-calendar-v1'
SECTIONS = ('problem', 'method', 'contribution', 'applicability', 'limitations', 'readingAdvice')
PAPER_KEYS = {'id', 'title', 'authors', 'year', 'venue', 'primaryDomain', 'canonicalUrl',
              'identifiers', 'classicRationale', 'classicEvidence', 'learningOrder', 'overview',
              'guide', 'fullText', 'sourceLocators', 'guideInputSha256', 'catalogInputSha256'}
HEADER_KEYS = {'schemaVersion', 'kind', 'timezone', 'anchorDate', 'selectionRuleVersion'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                           allow_nan=False) + '\n').encode('utf-8')
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError('Not finite UTF-8 JSON') from exc


def _unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key: ' + key)
        result[key] = value
    return result


def _json_bytes(raw):
    def invalid(value):
        raise ValueError('Nonfinite JSON number: ' + value)
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique,
                           parse_constant=invalid)
        canonical(value)
        return value
    except (UnicodeError, RecursionError) as exc:
        raise ValueError('Not finite UTF-8 JSON') from exc


def read_json(path: Path):
    try:
        return _json_bytes(Path(path).read_bytes())
    except OSError as exc:
        raise ValueError('Unreadable JSON: ' + Path(path).name) from exc


def beijing_date(value) -> date:
    if isinstance(value, datetime):
        require(value.tzinfo is not None and value.utcoffset() is not None, 'Clock must include timezone')
        return value.astimezone(BEIJING).date()
    if isinstance(value, date):
        return value
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value),
            'Date must be ISO YYYY-MM-DD or an aware datetime')
    return date.fromisoformat(value)


def rotation_domains(value) -> tuple[str, str]:
    return PAIRS[(beijing_date(value) - ANCHOR).days % 5]


def repeat_allowed(target_date, occurrence_dates) -> bool:
    target = beijing_date(target_date)
    require(isinstance(occurrence_dates, (list, tuple, set)), 'Occurrences must be dates')
    return all(abs((target - beijing_date(day)).days) >= 90 for day in occurrence_dates)


def envelope(kind: str, **content) -> dict:
    return dict(schemaVersion=1, kind=kind, timezone='Asia/Shanghai', anchorDate=ANCHOR.isoformat(),
                selectionRuleVersion=RULE, **content)


def _header(value, kind):
    require(isinstance(value, dict), kind + ' must be an object')
    require(type(value.get('schemaVersion')) is int and value['schemaVersion'] == 1,
            'Unsupported classic schema')
    require(value.get('kind') == kind and value.get('timezone') == 'Asia/Shanghai'
            and value.get('anchorDate') == '2026-09-30' and value.get('selectionRuleVersion') == RULE,
            'Wrong classic kind/timezone/anchor/rule')


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _url(value):
    require(_text(value), 'URL required')
    parsed = urlsplit(value)
    require(parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username
            and not parsed.password, 'Public HTTPS URL required')


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def projection(item: dict) -> dict:
    require(isinstance(item, dict), 'Paper must be an object')
    return {k: copy.deepcopy(v) for k, v in item.items()
            if k not in {'classicReread', 'previousRecommendationDate'}}


def _paper(value):
    require(isinstance(value, dict) and PAPER_KEYS <= value.keys()
            and not (value.keys() - PAPER_KEYS - {'publicationDate'}), 'Incomplete paper projection')
    for key in ('id', 'title', 'venue', 'classicRationale'):
        require(_text(value[key]), 'Missing paper ' + key)
    require(value['primaryDomain'] in DOMAINS, 'Unknown primary domain')
    require(type(value['year']) is int and 1 <= value['year'] <= 9999, 'Invalid publication year')
    if 'publicationDate' in value:
        require(beijing_date(value['publicationDate']).year == value['year'], 'Publication date/year differ')
    require(isinstance(value['authors'], list) and value['authors']
            and all(_text(a) for a in value['authors']), 'Complete authors required')
    require(isinstance(value['identifiers'], dict), 'Identifiers must be an object')
    require(type(value['learningOrder']) is int and value['learningOrder'] > 0, 'Invalid learning order')
    _url(value['canonicalUrl'])
    require(isinstance(value['classicEvidence'], list) and len(value['classicEvidence']) >= 2,
            'Classic evidence required')
    for entry in value['classicEvidence']:
        require(isinstance(entry, dict) and isinstance(entry.get('kind'), str)
                and entry['kind'] in {'survey', 'course', 'award', 'benchmark'}
                and _text(entry.get('locator')), 'Invalid classic source')
        _url(entry.get('url'))
    overview = value['overview']
    require(_text(overview), 'Overview required')
    counts = text_counts(overview)
    require(counts['han'] >= 150 and counts['visible'] <= 220, 'Overview budget failed')
    guide = value['guide']
    require(isinstance(guide, dict) and set(guide) == set(SECTIONS)
            and all(_text(guide[k]) for k in SECTIONS), 'Six complete guide sections required')
    counts = text_counts(''.join(guide[k] for k in SECTIONS))
    require(counts['han'] >= 500 and counts['visible'] <= 800, 'Guide budget failed')
    full = value['fullText']
    require(isinstance(full, dict) and full.get('format') == 'pdf' and _text(full.get('edition'))
            and _sha(full.get('sha256')) and type(full.get('pageCount')) is int and full['pageCount'] > 0,
            'Actual full-text edition/hash/pages required')
    _url(full.get('url'))
    for key in ('guideInputSha256', 'catalogInputSha256'):
        require(_sha(value[key]), 'Missing frozen input hash')
    require(isinstance(value['sourceLocators'], list) and value['sourceLocators'], 'Source locators required')
    for e in value['sourceLocators']:
        require(isinstance(e, dict) and e.get('section') in ('overview', *SECTIONS)
                and isinstance(e.get('classification'), str)
                and e['classification'] in {'paperFact', 'readerInference'} and _text(e.get('locator')),
                'Invalid source locator')
    canonical(value)


def _pool_map(pool):
    require(isinstance(pool, list), 'Ready pool must be an array')
    result = {}
    for paper in pool:
        _paper(paper)
        require(paper['id'] not in result, 'Duplicate pool identity')
        result[paper['id']] = paper
    return result


def _items(items, day, pool_map=None, *, published=False):
    require(isinstance(items, list) and len(items) == 2, 'Exactly two papers required')
    require(all(isinstance(p, dict) for p in items), 'Paper objects required')
    for paper in items:
        plain = projection(paper)
        _paper(plain)
        if pool_map is not None:
            require(pool_map.get(plain['id']) == plain, 'Queued paper differs from accepted pool')
        if published:
            require(type(paper.get('classicReread')) is bool and 'previousRecommendationDate' in paper,
                    'Missing reread metadata')
            prior = paper['previousRecommendationDate']
            require(paper['classicReread'] == (prior is not None), 'Reread metadata differs')
            if prior is not None:
                require((beijing_date(day) - beijing_date(prior)).days >= 90, 'Invalid prior recommendation')
        else:
            require(set(paper) == set(plain), 'Reservations are not published history')
    require(len({p['id'] for p in items}) == 2, 'Duplicate edition identity')
    require(tuple(p['primaryDomain'] for p in items) == rotation_domains(day), 'Wrong scheduled domains')


def validate_archive(archive, pool=None):
    _header(archive, 'classicArchive')
    require(set(archive) == HEADER_KEYS | {'editions'} and isinstance(archive['editions'], dict),
            'Invalid archive editions')
    lookup = _pool_map(pool) if pool is not None else None
    for day, edition in archive['editions'].items():
        beijing_date(day)
        _header(edition, 'classicEdition')
        require(set(edition) == HEADER_KEYS | {'recommendationDate', 'publishedAt', 'itemCount', 'items'}
                and edition.get('recommendationDate') == day and type(edition.get('itemCount')) is int
                and edition['itemCount'] == 2, 'Archive edition/date/count mismatch')
        require(isinstance(edition['publishedAt'], str), 'Published timestamp required')
        stamp = datetime.fromisoformat(edition['publishedAt'])
        require(beijing_date(stamp) >= beijing_date(day), 'Publication cannot precede recommendation date')
        _items(edition['items'], day, lookup, published=True)
    _spacing(_occurrences(None, archive))


def _occurrences(queue, archive):
    occurrences = {}
    groups = []
    if queue is not None:
        groups.append(queue['slots'])
    if archive is not None:
        groups.append(archive['editions'])
    for rows in groups:
        for day, row in rows.items():
            for paper in row['items']:
                occurrences.setdefault(paper['id'], set()).add(beijing_date(day))
    return occurrences


def _spacing(occurrences):
    for days in occurrences.values():
        ordered = sorted(days)
        require(all((b - a).days >= 90 for a, b in zip(ordered, ordered[1:])),
                'Repeat/reservation is less than90 calendar days')


def validate_queue(queue, pool=None, archive=None):
    _header(queue, 'classicQueue')
    require(set(queue) == HEADER_KEYS | {'slots'} and isinstance(queue['slots'], dict), 'Invalid queue slots')
    lookup = _pool_map(pool) if pool is not None else None
    for day, slot in queue['slots'].items():
        beijing_date(day)
        require(isinstance(slot, dict) and set(slot) == {'recommendationDate', 'selectionRuleVersion', 'domains', 'items'}
                and slot.get('recommendationDate') == day and slot.get('selectionRuleVersion') == RULE
                and slot.get('domains') == list(rotation_domains(day)), 'Invalid reservation date/rule/domains')
        _items(slot['items'], day, lookup)
    if archive is not None:
        validate_archive(archive, pool)
        for day in queue['slots'].keys() & archive['editions'].keys():
            require(queue['slots'][day]['items'] == [projection(p) for p in archive['editions'][day]['items']],
                    'Published combination conflicts with reservation')
    _spacing(_occurrences(queue, archive))


def inventory(queue, archive, target_date):
    target = beijing_date(target_date)
    validate_queue(queue, archive=archive)
    ready = [day for day in queue['slots'] if beijing_date(day) >= target and day not in archive['editions']]
    complete = 0
    for offset in range(15):
        day = (target + timedelta(days=offset)).isoformat()
        if day not in queue['slots'] and day not in archive['editions']:
            break
        complete += 1
    future = 0
    for offset in range(1, 15):
        day = (target + timedelta(days=offset)).isoformat()
        if day not in queue['slots'] and day not in archive['editions']:
            break
        future += 1
    return dict(targetDate=target.isoformat(), readyPaperCount=2 * len(ready),
                lowStock=2 * len(ready) < 14, completeDays=complete,
                futureCompleteDays=future, futurePaperCount=2 * future,
                firstMissingDate=(target + timedelta(days=complete)).isoformat() if complete < 15 else None)


def prepare_queue(pool, start_date, *, days=15, existing_queue=None, archive=None):
    lookup = _pool_map(pool)
    start = beijing_date(start_date)
    require(type(days) is int and 1 <= days <= 366, 'Horizon must be1..366 dates')
    queue = copy.deepcopy(existing_queue) if existing_queue is not None else envelope('classicQueue', slots={})
    history = copy.deepcopy(archive) if archive is not None else envelope('classicArchive', editions={})
    validate_queue(queue, pool, history)
    occurrences = _occurrences(queue, history)
    actual = _occurrences(None, history)
    for offset in range(days):
        day = start + timedelta(days=offset)
        key = day.isoformat()
        if key in queue['slots']:
            continue
        if key in history['editions']:
            queue['slots'][key] = dict(recommendationDate=key, selectionRuleVersion=RULE,
                                      domains=list(rotation_domains(day)),
                                      items=[projection(p) for p in history['editions'][key]['items']])
            continue
        selected = []
        for domain in rotation_domains(day):
            candidates = [p for p in lookup.values() if p['primaryDomain'] == domain
                          and repeat_allowed(day, occurrences.get(p['id'], set()))]
            def rank(p):
                prior = actual.get(p['id'], set())
                return (bool(prior), p['learningOrder'], max(prior) if prior else date.min, p['id'])
            if not candidates:
                break
            selected.append(min(candidates, key=rank))
        if len(selected) != 2:
            break
        queue['slots'][key] = dict(recommendationDate=key, selectionRuleVersion=RULE,
                                  domains=list(rotation_domains(day)), items=copy.deepcopy(selected))
        for paper in selected:
            occurrences.setdefault(paper['id'], set()).add(day)
    queue['slots'] = dict(sorted(queue['slots'].items()))
    validate_queue(queue, pool, history)
    return queue, inventory(queue, history, start)


def load_ready_pool(project: Path, as_of: date) -> list[dict]:
    project = Path(project)
    as_of = beijing_date(as_of)
    catalog_root = project / 'research/classics'
    binding = read_json(project / 'research/classic-publishing/frozen-catalog.json')
    require(isinstance(binding, dict)
            and set(binding) == {'schemaVersion', 'kind', 'acceptedBaseline', 'catalogBaseline', 'files'}
            and type(binding.get('schemaVersion')) is int and binding['schemaVersion'] == 1
            and binding.get('kind') == 'frozenClassicCatalog'
            and binding.get('acceptedBaseline') == '7f6444f24f05511b8ed7a2347c5e6f4ea5fe75db'
            and binding.get('catalogBaseline') == 'bde52ef5e354925a57046d5df43abf261b068782'
            and isinstance(binding.get('files'), dict)
            and set(binding['files']) == {d + '.json' for d in DOMAINS}
            and all(_sha(value) for value in binding['files'].values()), 'Malformed frozen catalog binding')
    catalog_bytes = {d: (catalog_root / (d + '.json')).read_bytes() for d in DOMAINS}
    for domain, raw in catalog_bytes.items():
        require(hashlib.sha256(raw).hexdigest() == binding['files'][domain + '.json'],
                'Changed frozen catalog: ' + domain)
    report = audit_directory(catalog_root, as_of=date(2026, 10, 1), evidence_root=catalog_root,
                             require_complete=True)
    require(report['ok'], 'Immutable200-paper catalog gate failed')
    catalogs = {d: _json_bytes(catalog_bytes[d]) for d in DOMAINS}
    datasets = {d: read_json(project / 'research/classic-guides' / (d + '.json')) for d in DOMAINS}
    catalog = {p['id']: p for data in catalogs.values() for p in data['papers']}
    report = validate_guides(datasets, list(catalog.values()), as_of=as_of, require_complete=True)
    require(report['ok'] and report['fullTextBytesRechecked'] == 0, 'Accepted30-guide declaration gate failed')
    seal = read_json(project / 'docs/audits/2026-10-02-classic-guides/sealed-inputs.json')
    require(isinstance(seal, dict) and isinstance(seal.get('fieldInputs'), dict)
            and set(seal['fieldInputs']) == set(DOMAINS), 'Malformed independent review seal')
    pool = []
    for domain in DOMAINS:
        guide_path = project / 'research/classic-guides' / (domain + '.json')
        guide_sha = hashlib.sha256(guide_path.read_bytes()).hexdigest()
        catalog_sha = hashlib.sha256(catalog_bytes[domain]).hexdigest()
        reviewed = seal['fieldInputs'][domain]
        require(isinstance(reviewed, dict) and _sha(reviewed.get('datasetSha256'))
                and _sha(reviewed.get('auditSha256')), 'Malformed field review seal')
        require(guide_sha == reviewed['datasetSha256'], 'Guide differs from independent review')
        audit_path = project / 'docs/audits/2026-10-02-classic-guides' / (domain + '.md')
        require(hashlib.sha256(audit_path.read_bytes()).hexdigest() == reviewed['auditSha256'],
                'Field audit differs from independent review')
        for guide in sorted(datasets[domain]['guides'], key=lambda g: g['learningOrder']):
            original = catalog[guide['paperId']]
            item = {key: copy.deepcopy(original[key]) for key in ('id', 'title', 'authors', 'year', 'venue',
                     'primaryDomain', 'canonicalUrl', 'identifiers', 'classicRationale')}
            if original.get('publicationDate') is not None:
                item['publicationDate'] = original['publicationDate']
            item['classicEvidence'] = [{k: e[k] for k in ('kind', 'url', 'locator')} for e in original['classicEvidence']]
            item.update(learningOrder=guide['learningOrder'], overview=guide['overview'], guide=copy.deepcopy(guide['guide']),
                        fullText={k: guide['fullText'][k] for k in ('url', 'format', 'sha256', 'pageCount', 'edition')},
                        guideInputSha256=guide_sha, catalogInputSha256=catalog_sha)
            seen = set()
            item['sourceLocators'] = []
            for e in guide['claimEvidence']:
                key = (e['section'], e['classification'], e['locator'])
                if key not in seen:
                    seen.add(key)
                    item['sourceLocators'].append(dict(section=key[0], classification=key[1], locator=key[2]))
            pool.append(item)
    _pool_map(pool)
    return pool
