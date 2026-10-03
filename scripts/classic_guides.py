"""Offline structural gates for reviewed classic-paper full-text guides.

Original PDF bytes are checked only with source_root. Structural checks do not
establish scholarly truth or replace independent complete-paper review.
"""
import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from classic_catalog import DOMAINS, _as_date, _invalid_constant, _unique_pairs, _url

SECTIONS = ('problem', 'method', 'contribution', 'applicability', 'limitations', 'readingAdvice')
EVIDENCE_SECTIONS = ('overview',) + SECTIONS
_HAN = re.compile('[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff'
                  '\U00020000-\U0002ebef\U0002f800-\U0002fa1f'
                  '\U00030000-\U000323af]')


def text_counts(text) -> dict:
    """Count Han characters and all non-whitespace Unicode characters."""
    if not isinstance(text, str):
        raise TypeError('text must be a string')
    return {'han': len(_HAN.findall(text)), 'visible': sum(not char.isspace() for char in text)}


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-fA-F]{64}', value) is not None


def _timestamp(value, as_of, errors, name):
    try:
        if not isinstance(value, str):
            raise ValueError('timestamp must be a string')
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if _as_date(parsed) > as_of:
            raise ValueError('future timestamp')
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        errors.append(name + ': timezone-aware nonfuture timestamp required')
        return None


def _relative(value):
    if not _text(value) or '\\' in value or '\x00' in value:
        raise ValueError('safe relative path required')
    relative = Path(value)
    if relative.is_absolute() or '..' in relative.parts or relative == Path('.'):
        raise ValueError('path must remain under source root')
    return relative


def _read_original(root, value):
    path = (root / _relative(value)).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('file missing or outside source root')
    return path.read_bytes()


def _load_json(raw):
    return json.loads(raw, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant)


def _full_text(record, as_of, root, errors):
    full = record.get('fullText')
    if not isinstance(full, dict):
        errors.append('fullText: object required')
        return None, None, False, None
    try:
        _url(full.get('url'))
    except ValueError as exc:
        errors.append('fullText.url: ' + str(exc))
    if full.get('format') != 'pdf':
        errors.append('fullText.format: must be pdf')
    if not _text(full.get('edition')):
        errors.append('fullText.edition: description required')
    page_count = full.get('pageCount')
    if type(page_count) is not int or page_count < 1:
        errors.append('fullText.pageCount: positive integer required')
        page_count = None
    for field in ('sha256', 'textSha256'):
        if not _sha(full.get(field)):
            errors.append('fullText.' + field + ': SHA-256 required')
    checked_at = _timestamp(full.get('checkedAt'), as_of, errors, 'fullText.checkedAt')
    for field in ('sourceFile', 'textFile'):
        try:
            _relative(full.get(field))
        except ValueError as exc:
            errors.append('fullText.' + field + ': ' + str(exc))
    if root is None:
        return page_count, None, False, checked_at
    rechecked = False
    try:
        raw = _read_original(root, full.get('sourceFile'))
        if not raw.startswith(b'%PDF-'):
            raise ValueError('PDF header missing')
        if not _sha(full.get('sha256')) or hashlib.sha256(raw).hexdigest() != full['sha256'].lower():
            raise ValueError('PDF SHA-256 mismatch')
        rechecked = True
    except (OSError, ValueError, RuntimeError) as exc:
        errors.append('fullText.sourceFile: ' + str(exc))
    pages = None
    try:
        raw = _read_original(root, full.get('textFile'))
        if not _sha(full.get('textSha256')) or hashlib.sha256(raw).hexdigest() != full['textSha256'].lower():
            raise ValueError('extraction SHA-256 mismatch')
        extracted = _load_json(raw.decode('utf-8'))
        if not isinstance(extracted, dict) or type(extracted.get('schemaVersion')) is not int or extracted['schemaVersion'] != 1:
            raise ValueError('extraction schemaVersion must be integer 1')
        if not _sha(extracted.get('pdfSha256')) or not _sha(full.get('sha256')) or extracted['pdfSha256'].lower() != full['sha256'].lower():
            raise ValueError('extraction PDF SHA-256 binding mismatch')
        if not _text(extracted.get('extractionMethod')):
            raise ValueError('extractionMethod required')
        rows = extracted.get('pages')
        if not isinstance(rows, list) or page_count is None or len(rows) != page_count:
            raise ValueError('extraction page count does not match PDF declaration')
        if any(not isinstance(row, dict) or type(row.get('pdfPage')) is not int
               or row['pdfPage'] != index or not isinstance(row.get('text'), str)
               for index, row in enumerate(rows, 1)):
            raise ValueError('all extraction pages must be ordered with exact Unicode text')
        # JSON escapes can decode to lone surrogates even in a valid UTF-8 file.
        # Check every page, including pages not cited by any guide claim.
        for row in rows:
            row['text'].encode('utf-8')
        pages = [row['text'] for row in rows]
    except (OSError, ValueError, UnicodeError, RuntimeError, RecursionError) as exc:
        errors.append('fullText.textFile: ' + str(exc))
    return page_count, pages, rechecked, checked_at


def _review(record, page_count, checked_at, as_of, errors):
    review = record.get('review')
    if not isinstance(review, dict):
        errors.append('review: object required')
        return
    if review.get('fullTextRead') is not True:
        errors.append('review.fullTextRead: explicit true required')
    read_pages = review.get('readPages')
    if (not isinstance(read_pages, list) or page_count is None
            or any(type(page) is not int for page in read_pages)
            or len(read_pages) != page_count or set(read_pages) != set(range(1, page_count + 1))):
        errors.append('review.readPages: all PDF pages exactly once required')
    reviewed_at = _timestamp(review.get('reviewedAt'), as_of, errors, 'review.reviewedAt')
    if reviewed_at is not None and checked_at is not None and reviewed_at < checked_at:
        errors.append('review.reviewedAt: cannot precede fullText.checkedAt')


def _evidence(record, bodies, page_count, pages, errors):
    evidence = record.get('claimEvidence')
    if not isinstance(evidence, list):
        errors.append('claimEvidence: array required')
        return
    covered = set()
    for index, item in enumerate(evidence):
        prefix = f'claimEvidence[{index}]'
        start_errors = len(errors)
        if not isinstance(item, dict):
            errors.append(prefix + ': object required')
            continue
        section = item.get('section')
        if not isinstance(section, str) or section not in EVIDENCE_SECTIONS:
            errors.append(prefix + '.section: overview or exact guide section required')
        elif not _text(item.get('claim')) or not isinstance(bodies.get(section), str) or item['claim'] not in bodies[section]:
            errors.append(prefix + '.claim: literal substring of named body required')
        classification = item.get('classification')
        if not isinstance(classification, str) or classification not in ('paperFact', 'readerInference'):
            errors.append(prefix + '.classification: paperFact or readerInference required')
        elif classification == 'readerInference' and (not _text(item.get('claim'))
                or not any(word in item['claim'] for word in ('推断', '工程上', '据此'))):
            errors.append(prefix + '.classification: reader inference must be explicitly labeled in claim')
        source_pages = item.get('sourcePages')
        valid_pages = (isinstance(source_pages, list) and bool(source_pages) and page_count is not None
                       and all(type(page) is int and 1 <= page <= page_count for page in source_pages))
        if not valid_pages or len(set(source_pages)) != len(source_pages):
            errors.append(prefix + '.sourcePages: unique in-range PDF pages required')
        if not _text(item.get('locator')):
            errors.append(prefix + '.locator: named page/section/figure/table locator required')
        context = item.get('context')
        if not isinstance(context, dict):
            errors.append(prefix + '.context: object required')
        else:
            page, start, end = (context.get(key) for key in ('page', 'start', 'end'))
            valid_range = (type(page) is int and page_count is not None and 1 <= page <= page_count
                           and valid_pages and page in source_pages and type(start) is int
                           and type(end) is int and 0 <= start < end)
            if not valid_range:
                errors.append(prefix + '.context: page must be cited and offsets define a nonempty range')
            if not _sha(context.get('sha256')):
                errors.append(prefix + '.context.sha256: SHA-256 required')
            if valid_range and pages is not None:
                text = pages[page - 1]
                if end > len(text) or not text[start:end].strip():
                    errors.append(prefix + '.context: slice outside text or empty')
                elif not _sha(context.get('sha256')) or hashlib.sha256(text[start:end].encode('utf-8')).hexdigest() != context['sha256'].lower():
                    errors.append(prefix + '.context.sha256: exact Unicode slice hash mismatch')
        if len(errors) == start_errors:
            covered.add(section)
    for section in EVIDENCE_SECTIONS:
        if section not in covered:
            errors.append('claimEvidence: missing valid evidence for ' + section)


def _record(record, domain, catalog, as_of, root):
    errors = []
    result = {'paperId': None, 'primaryDomain': domain, 'eligible': False,
              'errors': errors, 'fullTextBytesRechecked': False}
    if not isinstance(record, dict):
        errors.append('guide record must be an object')
        return result
    paper_id = record.get('paperId')
    result['paperId'] = paper_id if isinstance(paper_id, str) else None
    if not _text(paper_id):
        errors.append('paperId: catalog ID required')
    if record.get('primaryDomain') != domain:
        errors.append('primaryDomain: must match containing domain')
    status = record.get('status')
    if not isinstance(status, str) or status not in ('ready', 'candidate'):
        errors.append('status: ready or candidate required')
    matches = catalog.get(paper_id, []) if isinstance(paper_id, str) else []
    if len(matches) != 1:
        errors.append('catalog: exactly one matching paper ID required')
    else:
        owner = matches[0]
        if owner.get('primaryDomain') != domain:
            errors.append('catalog.primaryDomain: exact primary owner required')
        if not _text(record.get('title')) or record.get('title') != owner.get('title'):
            errors.append('catalog.title: exact canonical title required')
        if owner.get('status') != 'verified':
            errors.append('catalog.status: verified paper required')
    if status == 'ready' or 'learningOrder' in record:
        order = record.get('learningOrder')
        if type(order) is not int or not 1 <= order <= 6:
            errors.append('learningOrder: integer 1 through 6 required')
    if status != 'ready':
        return result
    bodies = {'overview': record.get('overview')}
    if not _text(bodies['overview']):
        errors.append('overview: nonempty Chinese text required')
    else:
        counts = text_counts(bodies['overview'])
        if counts['han'] < 150 or counts['visible'] > 220:
            errors.append('overview: requires at least 150 Han and at most 220 visible characters')
    guide = record.get('guide')
    if not isinstance(guide, dict) or set(guide) != set(SECTIONS):
        errors.append('guide: exactly the six specified sections required')
    if isinstance(guide, dict):
        bodies.update({key: guide.get(key) for key in SECTIONS})
        if any(not _text(guide.get(key)) for key in SECTIONS):
            errors.append('guide: every section must be nonempty text')
        else:
            counts = text_counts(''.join(guide[key] for key in SECTIONS))
            if counts['han'] < 500 or counts['visible'] > 800:
                errors.append('guide: requires at least 500 Han and at most 800 visible characters')
    page_count, pages, rechecked, checked_at = _full_text(record, as_of, root, errors)
    result['fullTextBytesRechecked'] = rechecked
    _review(record, page_count, checked_at, as_of, errors)
    _evidence(record, bodies, page_count, pages, errors)
    result['eligible'] = not errors
    return result


def validate_guides(datasets, catalog_records, *, as_of, source_root=None,
                    require_complete=False) -> dict:
    """Validate field datasets against frozen catalog rows, optionally originals."""
    as_of = _as_date(as_of)
    report = {'schemaVersion': 1, 'asOf': as_of.isoformat(), 'ok': False, 'complete': False,
              'readyCount': 0, 'candidateCount': 0, 'domainCounts': dict.fromkeys(DOMAINS, 0),
              'errors': [], 'records': [], 'fullTextBytesRechecked': 0}
    errors = report['errors']
    try:
        root = Path(source_root).resolve() if source_root is not None else None
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        errors.append('source_root: ' + str(exc))
        return report
    catalog = {}
    if not isinstance(catalog_records, list):
        errors.append('catalog records must be an array')
    else:
        for index, row in enumerate(catalog_records):
            if not isinstance(row, dict) or not _text(row.get('id')):
                errors.append(f'catalog[{index}]: object with paper ID required')
                continue
            catalog.setdefault(row['id'], []).append(row)
        if any(len(rows) > 1 for rows in catalog.values()):
            errors.append('catalog: duplicate IDs must be resolved')
    if not isinstance(datasets, dict):
        errors.append('datasets must be an object keyed by domain')
        return report
    for domain in datasets:
        if domain not in DOMAINS:
            errors.append('datasets: unknown domain ' + str(domain))
    owners, orders = {}, {}
    for domain in DOMAINS:
        if domain not in datasets:
            continue
        dataset = datasets[domain]
        if not isinstance(dataset, dict):
            errors.append(domain + ': dataset must be an object')
            continue
        dataset_errors = []
        if type(dataset.get('schemaVersion')) is not int or dataset['schemaVersion'] != 1:
            dataset_errors.append('schemaVersion must be integer 1')
        if dataset.get('primaryDomain') != domain:
            dataset_errors.append('dataset primaryDomain must match domain key')
        rows = dataset.get('guides')
        if not isinstance(rows, list):
            errors.append(domain + '.guides: array required')
            errors.extend(domain + ': ' + error for error in dataset_errors)
            continue
        errors.extend(domain + ': ' + error for error in dataset_errors)
        for index, row in enumerate(rows):
            checked = _record(row, domain, catalog, as_of, root)
            checked['index'] = index
            checked['errors'].extend(dataset_errors)
            checked['eligible'] = checked['eligible'] and not dataset_errors
            report['records'].append(checked)
            result_index = len(report['records']) - 1
            if checked['paperId'] is not None:
                owners.setdefault(checked['paperId'], []).append(result_index)
            if isinstance(row, dict):
                if row.get('status') == 'candidate':
                    report['candidateCount'] += 1
                if row.get('status') == 'ready' and type(row.get('learningOrder')) is int:
                    orders.setdefault((domain, row['learningOrder']), []).append(result_index)
    for groups, message in ((owners, 'duplicate paperId'), (orders, 'duplicate learningOrder')):
        for indices in groups.values():
            if len(indices) > 1:
                for index in indices:
                    report['records'][index]['errors'].append(message)
                    report['records'][index]['eligible'] = False
    for checked in report['records']:
        errors.extend(f'{checked["primaryDomain"]}.guides[{checked["index"]}] {checked["paperId"]}: {error}'
                      for error in checked['errors'])
        report['fullTextBytesRechecked'] += int(checked['fullTextBytesRechecked'])
        if checked['eligible']:
            report['readyCount'] += 1
            report['domainCounts'][checked['primaryDomain']] += 1
    report['complete'] = (not errors and report['readyCount'] == 30 and report['candidateCount'] == 0
                          and all(count == 6 for count in report['domainCounts'].values()))
    if require_complete and not report['complete']:
        errors.append('complete guides require exactly 30 ready, six per domain, and no candidates')
    report['ok'] = not errors
    return report


def _directory_inputs(guides_root, catalog_root):
    datasets, catalog, errors = {}, [], []
    for domain in DOMAINS:
        guide_path = guides_root / (domain + '.json')
        if not guide_path.exists():
            datasets[domain] = {'schemaVersion': 1, 'primaryDomain': domain, 'guides': []}
        else:
            try:
                datasets[domain] = _load_json(guide_path.read_text(encoding='utf-8'))
            except (OSError, ValueError, UnicodeError, RecursionError) as exc:
                errors.append(f'guides/{domain}.json: {exc}')
        try:
            payload = _load_json((catalog_root / (domain + '.json')).read_text(encoding='utf-8'))
            if not isinstance(payload, dict) or type(payload.get('schemaVersion')) is not int or payload['schemaVersion'] != 1:
                raise ValueError('catalog schemaVersion must be integer 1')
            if payload.get('primaryDomain') != domain or not isinstance(payload.get('papers'), list):
                raise ValueError('catalog domain and papers array required')
            for index, row in enumerate(payload['papers']):
                if isinstance(row, dict) and row.get('primaryDomain') != domain:
                    errors.append(f'catalog/{domain}.json.papers[{index}]: wrong containing domain')
                catalog.append(row)
        except (OSError, ValueError, UnicodeError, RecursionError) as exc:
            errors.append(f'catalog/{domain}.json: {exc}')
    return datasets, catalog, errors


def _report_inputs(guides_root, catalog_root, datasets, source_root):
    """Identify input files separately from the namespaces containing them."""
    inputs = [root / (domain + '.json')
              for root in (guides_root, catalog_root) for domain in DOMAINS]
    if source_root is not None:
        for dataset in datasets.values():
            if not isinstance(dataset, dict) or not isinstance(dataset.get('guides'), list):
                continue
            for record in dataset['guides']:
                if not isinstance(record, dict) or not isinstance(record.get('fullText'), dict):
                    continue
                for field in ('sourceFile', 'textFile'):
                    try:
                        inputs.append(source_root / _relative(record['fullText'].get(field)))
                    except ValueError:
                        # Unsafe declarations are never opened by the source gate.
                        continue
    return inputs


def _report_destination(destination, roots, inputs):
    path = destination.resolve()
    if any(path.is_relative_to(root.resolve()) for root in roots):
        raise ValueError('report cannot overwrite guides, catalog or original sources')
    for input_file in inputs:
        if path == input_file.resolve() or (path.exists() and input_file.exists() and path.samefile(input_file)):
            raise ValueError('report cannot overwrite an input file or its symlink/hardlink alias')
    return path


def main(argv=None):
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--guides-root', type=Path, default=project / 'research/classic-guides')
    parser.add_argument('--catalog-root', type=Path, default=project / 'research/classics')
    parser.add_argument('--as-of', default='2026-10-02')
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--require-complete', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', args.as_of):
            raise ValueError('ISO date required')
        as_of = date.fromisoformat(args.as_of)
    except ValueError:
        parser.error('--as-of requires a valid ISO date YYYY-MM-DD')
    datasets, catalog, errors = _directory_inputs(args.guides_root, args.catalog_root)
    report = validate_guides(datasets, catalog, as_of=as_of, source_root=args.source_root,
                             require_complete=args.require_complete)
    if errors:
        report['errors'] = errors + report['errors']
        report['ok'] = report['complete'] = False
    if args.report:
        try:
            protected = [args.guides_root, args.catalog_root]
            if args.source_root is not None:
                protected.append(args.source_root)
            inputs = _report_inputs(args.guides_root, args.catalog_root, datasets, args.source_root)
            path = _report_destination(args.report, protected, inputs)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        except (OSError, ValueError, RuntimeError) as exc:
            report['errors'].append('report output: ' + str(exc))
            report['ok'] = report['complete'] = False
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
