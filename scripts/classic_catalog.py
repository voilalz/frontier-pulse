"""Offline gates for reviewed classic-paper catalogs.

Captures and review declarations are checked locally. This module does not
fetch URLs, resolve DOIs, verify authors' identities, or judge scholarly impact.
"""
from datetime import date, datetime, timedelta, timezone
import argparse
import hashlib
import json
import ipaddress
from pathlib import Path
import re
import unicodedata
from urllib.parse import unquote, urlsplit

DOMAINS = ('AI', 'SLAM', 'GNC', 'CV', 'UAV')
CLASSIC_KINDS = {'survey', 'course', 'award', 'benchmark'}
PRIMARY_KINDS = {'publisher', 'author', 'doi_registry'}
BEIJING = timezone(timedelta(hours=8))
# Conservative institutional roots; ownership across domains still needs review.
COMPOUND_SUFFIXES = {'ac.uk', 'co.uk', 'org.uk', 'gov.uk', 'edu.cn', 'com.cn',
                     'org.cn', 'gov.cn', 'ac.jp', 'co.jp', 'edu.au', 'com.au',
                     'ac.nz', 'co.nz', 'edu.sg', 'com.sg', 'ac.in', 'co.in',
                     'com.br', 'edu.br', 'ac.kr', 'co.kr'}


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _normal(value):
    """For bibliographic comparisons, ignore case, spacing and punctuation."""
    if not isinstance(value, str):
        return ''
    return ''.join(c for c in unicodedata.normalize('NFKC', value).casefold() if c.isalnum())


def _title_present(title, excerpt):
    """Ignore punctuation/spacing without matching inside surrounding words."""
    target = _normal(title)
    if not target:
        return False
    content = unicodedata.normalize('NFKC', excerpt).casefold()
    # Separators may vary in a captured title, but its first and last letters
    # must not be part of another word (NIN in learning; U-Net in LeCun et al.).
    pattern = (r'(?<![^\W_])' + r'[\W_]*'.join(re.escape(c) for c in target)
               + r'(?![^\W_])')
    return re.search(pattern, content) is not None


def normalize_doi(value: str) -> str:
    if not _text(value):
        raise ValueError('DOI must be a nonempty string')
    value = value.strip()
    if value.lower().startswith(('http://', 'https://')):
        parsed = urlsplit(value)
        if parsed.hostname not in {'doi.org', 'dx.doi.org'} or parsed.username or parsed.password:
            raise ValueError('DOI URL must use doi.org')
        value = parsed.path.lstrip('/')
    elif value[:4].casefold() == 'doi:':
        value = value[4:].strip()
    value = unquote(value).casefold()
    if not re.fullmatch(r'10\.\d{4,9}/[^\s<>]+', value):
        raise ValueError('invalid DOI syntax')
    return value


def normalize_arxiv(value: str) -> str:
    if not _text(value):
        raise ValueError('arXiv ID must be a nonempty string')
    value = value.strip().casefold()
    if value.startswith(('https://', 'http://')):
        parsed = urlsplit(value)
        if parsed.hostname not in {'arxiv.org', 'www.arxiv.org'} or parsed.username or parsed.password:
            raise ValueError('arXiv URL must use arxiv.org')
        match = re.fullmatch(r'/(?:abs|pdf)/(.+)', parsed.path)
        if not match:
            raise ValueError('invalid arXiv URL')
        value = unquote(match.group(1))
    if value.startswith('arxiv:'):
        value = value[6:].strip()
    value = re.sub(r'\.pdf$', '', value)
    value = re.sub(r'v[1-9]\d*$', '', value)
    if re.fullmatch(r'\d{4}\.\d{4,5}', value):
        month = int(value[2:4])
    elif re.fullmatch(r'[a-z][a-z.-]*/\d{7}', value):
        month = int(value.split('/')[1][2:4])
    else:
        raise ValueError('invalid arXiv ID syntax')
    if not 1 <= month <= 12:
        raise ValueError('invalid arXiv month')
    return value


def _identifier_present(kind, expected, excerpt):
    """Compare whole identifiers; title-style punctuation removal is unsafe here."""
    excerpt = unquote(excerpt)
    normalize = normalize_doi if kind == 'doi' else normalize_arxiv
    tokens = re.findall(r'https?://[^\s<>"\']+', excerpt, re.I)
    if kind == 'doi':
        tokens += re.findall(r'(?<![\w.])10\.\d{4,9}/[^\s<>"\']+', excerpt, re.I)
    else:
        tokens += re.findall(r'(?<![\w.])(?:\d{4}\.\d{4,5}|[a-z][a-z.-]*/\d{7})(?:v[1-9]\d*)?(?![\w.])',
                             excerpt, re.I)
    for token in tokens:
        try:
            if normalize(token) == expected:
                return True
        except ValueError:
            continue
    return False


def identity_keys(record: dict) -> set[str]:
    """Report collisions instead of silently merging or deleting records."""
    if not isinstance(record, dict):
        return set()
    keys = set()
    if _text(record.get('id')):
        keys.add('id:' + record['id'].strip().casefold())
    identifiers = record.get('identifiers')
    if isinstance(identifiers, dict):
        for name, normalize in [('doi', normalize_doi), ('arxiv', normalize_arxiv)]:
            if identifiers.get(name) is not None:
                try:
                    keys.add(name + ':' + normalize(identifiers[name]))
                except ValueError:
                    pass
    authors = record.get('authors')
    first = _normal(authors[0]) if isinstance(authors, list) and authors else ''
    aliases = record.get('titleAliases', [])
    titles = [record.get('title')] + (aliases if isinstance(aliases, list) else [])
    for title in titles:
        if _normal(title):
            keys.add('title:' + _normal(title) + ':' + first)
    return keys


def _as_date(value):
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('as_of datetime must include a timezone')
        return value.astimezone(BEIJING).date()
    if isinstance(value, date):
        return value
    raise ValueError('as_of must be date or timezone-aware datetime')


def _url(value):
    if not _text(value):
        raise ValueError('HTTPS source URL is required')
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
        if parsed.scheme != 'https' or not host or '.' not in host or parsed.username or parsed.password:
            raise ValueError('URL must be public HTTPS without credentials')
        if port not in {None, 443} or any(c.isspace() for c in value):
            raise ValueError('invalid source URL')
        host = host.rstrip('.').encode('idna').decode('ascii').lower()
        if not re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)+', host):
            raise ValueError('invalid source host')
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return parsed, host
        raise ValueError('source URL cannot use an IP address')
    except (TypeError, UnicodeError) as exc:
        raise ValueError('invalid source URL') from exc


def _provider(url):
    _, host = _url(url)
    parts = host.split('.')
    count = 3 if '.'.join(parts[-2:]) in COMPOUND_SUFFIXES else 2
    return '.'.join(parts[-count:])


def _source(source, root, as_of, errors, prefix):
    start = len(errors)
    if not isinstance(source, dict):
        errors.append(prefix + ': source must be an object')
        return None
    provider = ''
    try:
        provider = _provider(source.get('originUrl') or source.get('url'))
        _url(source.get('url'))
    except ValueError as exc:
        errors.append(f'{prefix}.url: {exc}')
    if source.get('reviewed') is not True:
        errors.append(prefix + '.reviewed: explicit review is required')
    for name in ('locator', 'excerpt'):
        if not _text(source.get(name)):
            errors.append(prefix + '.' + name + ': required')
    try:
        checked = datetime.fromisoformat(source.get('checkedAt', '').replace('Z', '+00:00'))
        if checked.tzinfo is None or checked.utcoffset() is None or checked.astimezone(BEIJING).date() > as_of:
            raise ValueError('timestamp must have timezone and not be future')
    except (ValueError, TypeError, AttributeError, OverflowError):
        errors.append(prefix + '.checkedAt: invalid or future review timestamp')
    capture = source.get('capture')
    content = ''
    digest = ''
    try:
        if not isinstance(capture, dict) or not _text(capture.get('path')):
            raise ValueError('capture path and SHA-256 are required')
        relative = Path(capture['path'])
        if relative.is_absolute() or '..' in relative.parts or '\\' in capture['path']:
            raise ValueError('capture must remain under evidence root')
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('capture missing or outside evidence root')
        if path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('capture exceeds 8 MiB text limit')
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        declared = capture.get('sha256')
        if not isinstance(declared, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', declared) or digest != declared.lower():
            raise ValueError('capture SHA-256 mismatch')
        content = raw.decode('utf-8')
        excerpt = source.get('excerpt')
        if not _text(excerpt) or ' '.join(excerpt.split()) not in ' '.join(content.split()):
            raise ValueError('excerpt is absent from capture')
    except (OSError, ValueError, UnicodeError, RuntimeError) as exc:
        errors.append(f'{prefix}.capture: {exc}')
    group = source.get('providerGroup')
    if group is not None and not _text(group):
        errors.append(prefix + '.providerGroup: must be nonempty string')
    if len(errors) != start:
        return None
    return {'provider': provider, 'group': group.strip().casefold() if group else '',
            'sha256': digest, 'excerpt': source['excerpt']}


def _bibliography(record, root, as_of, errors, identifiers):
    evidence = record.get('bibliographicEvidence')
    if not isinstance(evidence, list) or not evidence:
        errors.append('bibliographicEvidence: primary reviewed source is required')
        return
    required = {'title', 'authors', 'year', 'venue'} | set(identifiers)
    if record.get('publicationDate') is not None:
        required.add('publicationDate')
    verified = set()
    canonical_backed = False
    for i, source in enumerate(evidence):
        prefix = f'bibliographicEvidence[{i}]'
        accepted = _source(source, root, as_of, errors, prefix)
        if not accepted:
            continue
        if not isinstance(source.get('kind'), str) or source['kind'] not in PRIMARY_KINDS:
            errors.append(prefix + '.kind: must be publisher, author or doi_registry')
            continue
        observed = source.get('observed')
        if not isinstance(observed, dict):
            errors.append(prefix + '.observed: source metadata is required')
            continue
        for field, value in observed.items():
            expected = identifiers.get(field) if field in {'doi', 'arxiv'} else record.get(field)
            match = False
            tokens = []
            if field in {'doi', 'arxiv'}:
                normalize = normalize_doi if field == 'doi' else normalize_arxiv
                try:
                    match = expected is not None and normalize(value) == expected
                    tokens = [normalize(value)]
                except ValueError:
                    pass
            elif field == 'authors':
                match = (isinstance(value, list) and isinstance(expected, list) and bool(value)
                         and all(_text(v) for v in value)
                         and [_normal(v) for v in value] == [_normal(v) for v in expected])
                tokens = value if match else []
            elif field == 'year':
                match = type(value) is int and type(expected) is int and value == expected
                tokens = [str(value)] if match else []
            elif field in {'title', 'venue', 'publicationDate'}:
                match = _text(value) and _text(expected) and _normal(value) == _normal(expected)
                tokens = [value] if match else []
            located = (_identifier_present(field, expected, accepted['excerpt'])
                       if field in {'doi', 'arxiv'} and match
                       else all(_normal(v) in _normal(accepted['excerpt']) for v in tokens))
            if not match or not located:
                errors.append(prefix + '.observed.' + field + ': does not match located source metadata')
            else:
                verified.add(field)
        if source.get('url') == record.get('canonicalUrl'):
            canonical_backed = True
    for field in sorted(required - verified):
        errors.append('bibliographicEvidence: missing verified ' + field)
    canonical = record.get('canonicalUrl')
    try:
        parsed, host = _url(canonical)
        if host in {'doi.org', 'dx.doi.org'}:
            canonical_backed = normalize_doi(canonical) == identifiers.get('doi') and 'doi' in verified
    except ValueError:
        pass
    if not canonical_backed:
        errors.append('canonicalUrl: must match a reviewed source URL or verified DOI')


def _classics(record, root, as_of, errors, identifiers):
    sources = record.get('classicEvidence')
    if not isinstance(sources, list):
        errors.append('classicEvidence: two independent reviewed bases are required')
        return
    accepted = []
    titles = [record.get('title')]
    if isinstance(record.get('titleAliases'), list):
        titles += record['titleAliases']
    targets = [v for v in titles if _normal(v)]
    for i, source in enumerate(sources):
        prefix = f'classicEvidence[{i}]'
        validated = _source(source, root, as_of, errors, prefix)
        if not validated:
            continue
        if not isinstance(source.get('kind'), str) or source['kind'] not in CLASSIC_KINDS:
            errors.append(prefix + '.kind: citation counts alone are not a classic basis')
            continue
        located = (any(_title_present(v, validated['excerpt']) for v in targets)
                   or any(_identifier_present(kind, value, validated['excerpt'])
                          for kind, value in identifiers.items()))
        if source.get('supportsPaperId') != record.get('id') or not located:
            errors.append(prefix + ': excerpt must locate this paper and support its ID')
            continue
        accepted.append(validated)
    # Declared ownership is transitive: a grouped source also links ungrouped
    # sources on the same domain to every other domain in that provider group.
    parents = {}

    def find(key):
        parents.setdefault(key, key)
        while parents[key] != key:
            parents[key] = parents[parents[key]]
            key = parents[key]
        return key

    for source in accepted:
        domain = 'domain:' + source['provider']
        find(domain)
        if source['group']:
            parents[find(domain)] = find('group:' + source['group'])
    independent = any(find('domain:' + a['provider']) != find('domain:' + b['provider'])
                      and a['sha256'] != b['sha256']
                      for i, a in enumerate(accepted) for b in accepted[i + 1:])
    if not independent:
        errors.append('classicEvidence: fewer than two independent providers/captures')


def validate_record(record: object, *, as_of: date | datetime, evidence_root: Path) -> dict:
    as_of = _as_date(as_of)
    root = Path(evidence_root).resolve()
    errors, problems = [], []
    result = {'id': None, 'eligible': False, 'errors': errors, 'warnings': [], 'identities': []}
    if not isinstance(record, dict):
        errors.append('record must be an object')
        return result
    result['id'] = record.get('id') if isinstance(record.get('id'), str) else None
    if not _text(record.get('id')) or not re.fullmatch(r'classic:[a-z0-9][a-z0-9:._-]*', record['id']):
        errors.append('id: stable classic: ID is required')
    if not _text(record.get('title')):
        errors.append('title: required')
    if record.get('primaryDomain') not in DOMAINS:
        errors.append('primaryDomain: must be AI, SLAM, GNC, CV or UAV')
    if record.get('status') not in ('candidate', 'verified'):
        errors.append('status: must be candidate or verified')
    aliases = record.get('titleAliases', [])
    if not isinstance(aliases, list) or not all(_text(v) for v in aliases):
        errors.append('titleAliases: must be nonempty title strings')
    ids = record.get('identifiers', {})
    identifiers = {}
    if not isinstance(ids, dict):
        errors.append('identifiers: must be an object')
    else:
        for name, value in ids.items():
            if name not in {'doi', 'arxiv'}:
                errors.append('identifiers.' + name + ': unsupported identifier type')
            elif value is not None:
                try:
                    identifiers[name] = (normalize_doi if name == 'doi' else normalize_arxiv)(value)
                except ValueError as exc:
                    errors.append(f'identifiers.{name}: {exc}')
    authors = record.get('authors')
    if (not isinstance(authors, list) or not authors or not all(_text(v) for v in authors)
            or any(re.search(r'\bet\s+al\b|\.\.\.|…', v, re.I) for v in authors if isinstance(v, str))):
        problems.append('authors: full author list is required; et al. is not complete')
    year = record.get('year')
    valid_year = type(year) is int and 1 <= year <= as_of.year
    if not valid_year:
        problems.append('year: must be an integer publication year, not future')
    for field in ('venue', 'classicRationale'):
        if not _text(record.get(field)):
            problems.append(field + ': required')
    try:
        _url(record.get('canonicalUrl'))
    except ValueError as exc:
        problems.append('canonicalUrl: ' + str(exc))
    published = None
    precise = record.get('publicationDate')
    if precise is not None:
        try:
            if not isinstance(precise, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', precise):
                raise ValueError('ISO date required')
            published = date.fromisoformat(precise)
            if not valid_year or published.year != year:
                raise ValueError('date must match publication year')
        except (ValueError, TypeError):
            problems.append('publicationDate: invalid or does not match year')
            published = None
    elif valid_year:
        published = date(year, 12, 31)
    if published:
        try:
            anniversary = published.replace(year=published.year + 5)
        except ValueError:
            anniversary = date(published.year + 5, 3, 1)
        if as_of < anniversary:
            problems.append('age: paper must be at least five full calendar years old')
    _bibliography(record, root, as_of, problems, identifiers)
    _classics(record, root, as_of, problems, identifiers)
    result['identities'] = sorted(identity_keys(record))
    if record.get('status') == 'candidate':
        result['warnings'].extend(problems)
    else:
        errors.extend(problems)
    result['eligible'] = record.get('status') == 'verified' and not errors
    return result


def validate_catalog(records: list, *, as_of: date | datetime, evidence_root: Path,
                     require_complete: bool = False) -> dict:
    as_of = _as_date(as_of)
    report = {'schemaVersion': 1, 'asOf': as_of.isoformat(), 'ok': False, 'complete': False,
              'verifiedCount': 0, 'candidateCount': 0, 'domainCounts': {d: 0 for d in DOMAINS},
              'records': [], 'errors': [], 'duplicates': []}
    if not isinstance(records, list):
        report['errors'].append('catalog records must be an array')
        return report
    owners = {}
    collisions = set()
    for i, record in enumerate(records):
        checked = validate_record(record, as_of=as_of, evidence_root=evidence_root)
        checked['index'] = i
        checked['primaryDomain'] = record.get('primaryDomain') if isinstance(record, dict) else None
        report['records'].append(checked)
        report['errors'].extend(f'record[{i}] {checked["id"]}: {error}' for error in checked['errors'])
        if isinstance(record, dict) and record.get('status') == 'candidate':
            report['candidateCount'] += 1
        for key in checked['identities']:
            owners.setdefault(key, []).append(i)
    for key, indices in sorted(owners.items()):
        if len(indices) > 1:
            collisions.update(indices)
            report['duplicates'].append({'identity': key, 'indices': indices,
                                         'paperIds': [report['records'][i]['id'] for i in indices]})
    if collisions:
        report['errors'].append('duplicate paper identities must be resolved before acceptance')
    for checked in report['records']:
        if checked['index'] in collisions:
            checked['eligible'] = False
            checked['errors'].append('identity collides with another catalog record')
        if checked['eligible']:
            report['domainCounts'][checked['primaryDomain']] += 1
            report['verifiedCount'] += 1
    report['complete'] = not report['errors'] and report['verifiedCount'] == 200 and all(
        n == 40 for n in report['domainCounts'].values())
    if require_complete and not report['complete']:
        report['errors'].append('complete catalog requires exactly 200 unique eligible papers and 40 per domain')
    report['ok'] = not report['errors']
    return report


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('non-JSON numeric constant: ' + value)


def audit_directory(directory: Path, *, as_of: date | datetime, evidence_root: Path,
                    require_complete: bool = False) -> dict:
    records, errors = [], []
    directory = Path(directory)
    for domain in DOMAINS:
        path = directory / (domain + '.json')
        try:
            payload = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique_pairs,
                                 parse_constant=_invalid_constant)
            if not isinstance(payload, dict):
                raise ValueError('domain document must be an object')
            if type(payload.get('schemaVersion')) is not int or payload['schemaVersion'] != 1:
                raise ValueError('schemaVersion must be integer 1')
            if payload.get('primaryDomain') != domain:
                raise ValueError('document primaryDomain must match filename')
            rows = payload.get('papers')
            if not isinstance(rows, list):
                raise ValueError('papers must be an array')
            for i, record in enumerate(rows):
                if isinstance(record, dict) and record.get('primaryDomain') != domain:
                    errors.append(f'{path.name}.papers[{i}]: primaryDomain does not match containing file')
                    continue
                records.append(record)
        except (OSError, ValueError, UnicodeError, RecursionError) as exc:
            errors.append(f'{path.name}: {exc}')
    report = validate_catalog(records, as_of=as_of, evidence_root=evidence_root,
                              require_complete=require_complete)
    if errors:
        report['errors'] = errors + report['errors']
        report['ok'] = report['complete'] = False
    return report


def main(argv=None):
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog-dir', type=Path, default=project / 'research/classics')
    parser.add_argument('--evidence-root', type=Path,
                        help='capture paths are relative to this root (defaults to catalog dir)')
    parser.add_argument('--as-of', default=datetime.now(BEIJING).date().isoformat())
    parser.add_argument('--require-complete', action='store_true')
    parser.add_argument('--report', type=Path, help='optional JSON report outside input/evidence directories')
    args = parser.parse_args(argv)
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', args.as_of):
            raise ValueError('ISO date YYYY-MM-DD required')
        as_of = date.fromisoformat(args.as_of)
    except ValueError:
        parser.error('--as-of requires a valid ISO date YYYY-MM-DD')
    evidence_root = args.evidence_root or args.catalog_dir
    report = audit_directory(args.catalog_dir, as_of=as_of, evidence_root=evidence_root,
                             require_complete=args.require_complete)
    if args.report:
        try:
            path = args.report.resolve()
            if any(path.is_relative_to(root.resolve()) for root in (args.catalog_dir, evidence_root)):
                raise ValueError('report cannot overwrite the catalog or evidence namespace')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        except (OSError, ValueError, RuntimeError) as exc:
            report['errors'].append('report output: ' + str(exc))
            report['ok'] = False
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
