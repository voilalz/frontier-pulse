"""Synthetic guides and temporary bytes, never a real-guide inventory.

Reconstructed tests after workspace loss; no previous unsealed commit recovered.
"""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
try:
    import classic_guides as gate
except ImportError:
    gate = None

DOMAINS = ('AI', 'SLAM', 'GNC', 'CV', 'UAV')
SECTIONS = ('problem', 'method', 'contribution', 'applicability', 'limitations', 'readingAdvice')


class GuideFixture(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(gate, 'classic guide gate is not implemented')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog = []

    def guide(self, domain='AI', order=1):
        name = f'{domain.lower()}-{order}'
        paper_id = 'classic:synthetic:' + name
        title = 'Synthetic Guide Fixture ' + name
        if not any(row['id'] == paper_id for row in self.catalog):
            self.catalog.append({'id': paper_id, 'primaryDomain': domain,
                                 'title': title, 'status': 'verified'})
        source = self.root / domain / (name + '.pdf')
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b'%PDF-1.7\nSynthetic unit fixture; not a paper.\n%%EOF\n')
        pdf_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        extraction = {'schemaVersion': 1, 'pdfSha256': pdf_hash,
            'extractionMethod': 'synthetic unit text', 'pages': [
                {'pdfPage': 1, 'text': '前言。Synthetic context: 方法 supports inference.\n'},
                {'pdfPage': 2, 'text': 'Bibliography.'}]}
        text_file = source.with_suffix('.pages.json')
        text_file.write_text(json.dumps(extraction, ensure_ascii=False), encoding='utf-8')
        overview = '概' * 150
        bodies = {section: '文' * 84 for section in SECTIONS}
        evidence = [{'section': section, 'claim': body[:2], 'classification': 'paperFact',
            'sourcePages': [1], 'locator': 'PDF page 1, synthetic Section 2',
            'context': {'page': 1, 'start': 0, 'end': 2,
                        'sha256': hashlib.sha256('前言'.encode()).hexdigest()}}
            for section, body in {'overview': overview, **bodies}.items()]
        return {'paperId': paper_id, 'primaryDomain': domain, 'title': title,
            'status': 'ready', 'learningOrder': order, 'overview': overview, 'guide': bodies,
            'fullText': {'url': 'https://papers.example.org/' + name + '.pdf',
                'format': 'pdf', 'sha256': pdf_hash, 'pageCount': 2,
                'checkedAt': '2026-10-02T00:00:00Z', 'edition': 'synthetic fixture edition',
                'sourceFile': source.relative_to(self.root).as_posix(),
                'textFile': text_file.relative_to(self.root).as_posix(),
                'textSha256': hashlib.sha256(text_file.read_bytes()).hexdigest()},
            'review': {'fullTextRead': True, 'readPages': [1, 2],
                       'reviewedAt': '2026-10-02T01:00:00Z'}, 'claimEvidence': evidence}

    def datasets(self, rows):
        return {domain: {'schemaVersion': 1, 'primaryDomain': domain,
                        'guides': [row for row in rows if row['primaryDomain'] == domain]}
                for domain in DOMAINS}

    def audit(self, rows, originals=False, strict=False):
        return gate.validate_guides(self.datasets(rows), self.catalog,
            as_of=date(2026, 10, 2), source_root=self.root if originals else None,
            require_complete=strict)

    def rejected(self, row, originals=False, contains=None):
        report = self.audit([row], originals)
        self.assertFalse(report['ok'], report)
        self.assertEqual(report['readyCount'], 0, report)
        self.assertFalse(report['records'][0]['eligible'], report)
        if contains:
            self.assertTrue(any(contains in error for error in report['errors']), report['errors'])
        return report

    def rewrite_extraction(self, row, edit):
        path = self.root / row['fullText']['textFile']
        data = json.loads(path.read_text())
        edit(data)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        row['fullText']['textSha256'] = hashlib.sha256(path.read_bytes()).hexdigest()


class GuideGateTests(GuideFixture):
    def test_han_and_visible_counts_do_not_confuse_ascii_with_chinese(self):
        self.assertEqual(gate.text_counts('中𠀀豈A 1\n。'), {'han': 3, 'visible': 6})

    def test_declarations_are_eligible_without_claiming_bytes_rechecked(self):
        report = self.audit([self.guide()])
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['readyCount'], 1)
        self.assertEqual(report['fullTextBytesRechecked'], 0)
        self.assertTrue(report['records'][0]['eligible'])
        self.assertFalse(report['complete'])

    def test_actual_bytes_and_unicode_context_slices_are_rechecked(self):
        report = self.audit([self.guide()], originals=True)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['fullTextBytesRechecked'], 1)

    def test_missing_wrong_owner_title_or_unverified_catalog_record_rejects(self):
        for field, value in [('primaryDomain', 'CV'), ('title', 'Wrong title'), ('status', 'candidate'),
                            ('title', None), ('primaryDomain', None), ('status', None), ('id', 'classic:missing')]:
            self.catalog = []
            row = self.guide()
            self.catalog[0][field] = value
            with self.subTest(field=field, value=value):
                self.rejected(row, contains='catalog')
        self.catalog = []
        row = self.guide()
        self.catalog = []
        self.rejected(row, contains='catalog')

    def test_ambiguous_duplicate_catalog_id_is_not_silently_selected(self):
        row = self.guide()
        self.catalog.append(copy.deepcopy(self.catalog[0]))
        self.rejected(row, contains='catalog')

    def test_duplicate_paper_ids_block_both_ready_records(self):
        row = self.guide()
        second = copy.deepcopy(row)
        second['learningOrder'] = 2
        report = self.audit([row, second])
        self.assertFalse(report['ok'])
        self.assertEqual(report['readyCount'], 0)
        self.assertTrue(all(not row['eligible'] for row in report['records']))

    def test_duplicate_learning_orders_block_both_ready_records(self):
        first, second = self.guide(order=1), self.guide(order=2)
        second['learningOrder'] = 1
        report = self.audit([first, second])
        self.assertFalse(report['ok'])
        self.assertEqual(report['readyCount'], 0)

    def test_candidate_does_not_count_or_require_finished_body(self):
        row = self.guide()
        candidate = {key: row[key] for key in ('paperId', 'title', 'primaryDomain')}
        candidate.update(status='candidate', gap='Full text still under review')
        report = self.audit([candidate])
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['candidateCount'], 1)
        self.assertEqual(report['readyCount'], 0)
        self.assertFalse(report['records'][0]['eligible'])
        self.assertFalse(self.audit([candidate], strict=True)['ok'])

    def test_candidate_duplicate_also_blocks_ready_identity(self):
        row = self.guide()
        draft = {key: row[key] for key in ('paperId', 'title', 'primaryDomain')}
        draft['status'] = 'candidate'
        report = self.audit([row, draft])
        self.assertFalse(report['ok'])
        self.assertEqual(report['readyCount'], 0)
        self.assertEqual(report['candidateCount'], 1)

    def test_exact_six_sections_reject_missing_extra_or_alias(self):
        for mode in ('missing', 'extra', 'alias'):
            row = self.guide()
            if mode == 'missing':
                row['guide'].pop('method')
            elif mode == 'extra':
                row['guide']['summary'] = '文' * 10
            else:
                row['guide']['reading_advice'] = row['guide'].pop('readingAdvice')
            with self.subTest(mode=mode):
                self.rejected(row, contains='guide')

    def test_overview_han_minimum_and_visible_maximum_boundaries(self):
        for body, allowed in [('概' * 149, False), ('概' * 150, True), ('概' * 220, True),
                             ('概' * 221, False), ('概' * 149 + 'a' * 71, False),
                             ('概' * 150 + 'a' * 71, False), ('概' * 150 + ' \n' * 100, True)]:
            row = self.guide()
            row['overview'] = body
            with self.subTest(length=len(body), allowed=allowed):
                self.assertEqual(self.audit([row])['ok'], allowed)

    def test_guide_han_minimum_and_visible_maximum_boundaries(self):
        for total, ascii_count, allowed in [(499, 0, False), (500, 0, True), (800, 0, True),
                                           (801, 0, False), (499, 100, False), (500, 301, False)]:
            row = self.guide()
            row['guide'] = {section: '文' * 2 for section in SECTIONS}
            row['guide']['problem'] += '文' * (total - 12) + 'a' * ascii_count
            with self.subTest(total=total, ascii_count=ascii_count):
                self.assertEqual(self.audit([row])['ok'], allowed)

    def test_review_requires_true_and_every_unique_pdf_page(self):
        for field, value in [('fullTextRead', False), ('fullTextRead', 1), ('readPages', [1]),
                            ('readPages', [1, 1, 2]), ('readPages', [0, 1, 2]),
                            ('readPages', [1, 2, 3]), ('readPages', [True, 2])]:
            row = self.guide()
            row['review'][field] = value
            with self.subTest(field=field, value=value):
                self.rejected(row, contains='review')

    def test_each_of_seven_bodies_has_located_evidence(self):
        for section in ('overview',) + SECTIONS:
            row = self.guide()
            row['claimEvidence'] = [item for item in row['claimEvidence'] if item['section'] != section]
            with self.subTest(section=section):
                self.rejected(row, contains='claimEvidence')

    def test_claim_must_be_literal_substring_in_its_named_body(self):
        row = self.guide()
        row['claimEvidence'][0]['claim'] = 'Absent claim'
        self.rejected(row, contains='claim')
        row = self.guide()
        row['claimEvidence'][0]['section'] = 'unknown'
        self.rejected(row, contains='section')

    def test_reader_inference_requires_explicit_wording_in_claim(self):
        row = self.guide()
        item = row['claimEvidence'][0]
        item['classification'] = 'readerInference'
        self.rejected(row, contains='inference')
        row['overview'] = '据此推断' + row['overview']
        item['claim'] = '据此推断'
        self.assertTrue(self.audit([row])['ok'])
        item['classification'] = 'authorGuess'
        self.rejected(row, contains='classification')

    def test_context_declaration_requires_page_range_nonempty_hash_and_locator(self):
        for field, value in [('page', 0), ('page', 3), ('page', 2), ('start', -1),
                            ('start', True), ('end', 0), ('end', 1.5), ('sha256', 'bad')]:
            row = self.guide()
            row['claimEvidence'][0]['context'][field] = value
            with self.subTest(field=field, value=value):
                self.rejected(row, contains='context')
        for field, value in [('sourcePages', []), ('sourcePages', [3]), ('sourcePages', [1, 1]),
                            ('sourcePages', [True]), ('locator', '')]:
            row = self.guide()
            row['claimEvidence'][0][field] = value
            self.rejected(row, contains=field)

    def test_source_root_rejects_missing_bad_magic_and_changed_pdf_bytes(self):
        for mode in ('missing', 'magic', 'changed'):
            row = self.guide()
            path = self.root / row['fullText']['sourceFile']
            if mode == 'missing':
                path.unlink()
            elif mode == 'magic':
                path.write_bytes(b'<html>not a PDF</html>')
                row['fullText']['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            else:
                path.write_bytes(path.read_bytes() + b'changed')
            with self.subTest(mode=mode):
                self.rejected(row, originals=True, contains='sourceFile')

    def test_extraction_bytes_hash_binding_order_count_and_method_are_checked(self):
        for mode in ('missing', 'hash', 'binding', 'count', 'order', 'method', 'schema', 'text'):
            row = self.guide()
            path = self.root / row['fullText']['textFile']
            if mode == 'missing':
                path.unlink()
            elif mode == 'hash':
                path.write_bytes(path.read_bytes() + b' ')
            else:
                edits = {'binding': lambda d: d.update(pdfSha256='0' * 64),
                    'count': lambda d: d['pages'].pop(), 'order': lambda d: d['pages'].reverse(),
                    'method': lambda d: d.update(extractionMethod=''),
                    'schema': lambda d: d.update(schemaVersion=True),
                    'text': lambda d: d['pages'][0].update(text=None)}
                self.rewrite_extraction(row, edits[mode])
            with self.subTest(mode=mode):
                self.rejected(row, originals=True, contains='textFile')

    def test_actual_context_slice_hash_bounds_and_whitespace_are_checked(self):
        for mode in ('hash', 'bounds', 'whitespace'):
            row = self.guide()
            context = row['claimEvidence'][0]['context']
            if mode == 'hash':
                context['sha256'] = '0' * 64
            elif mode == 'bounds':
                context['end'] = 9999
            else:
                self.rewrite_extraction(row, lambda d: d['pages'][0].update(text='  '))
                context['sha256'] = hashlib.sha256(b'  ').hexdigest()
            with self.subTest(mode=mode):
                self.rejected(row, originals=True, contains='context')

    def test_safe_relative_source_paths_are_required_in_both_modes(self):
        for field in ('sourceFile', 'textFile'):
            for value in ('../escape', '/absolute', 'AI\\escape.pdf', 'AI/../escape', ''):
                row = self.guide()
                row['fullText'][field] = value
                for originals in (False, True):
                    with self.subTest(field=field, value=value, originals=originals):
                        self.rejected(row, originals, contains=field)

    def test_symlink_escape_cannot_read_pdf_or_extraction_outside_root(self):
        with tempfile.TemporaryDirectory() as outside:
            for field in ('sourceFile', 'textFile'):
                row = self.guide()
                path = self.root / row['fullText'][field]
                external = Path(outside) / path.name
                external.write_bytes(path.read_bytes())
                path.unlink()
                path.symlink_to(external)
                with self.subTest(field=field):
                    self.rejected(row, originals=True, contains=field)
                path.unlink()

    def test_public_https_and_timezone_aware_nonfuture_times_are_required(self):
        for value in ('http://papers.example.org/a.pdf', 'https://user:pass@example.org/a.pdf',
                     'https://127.0.0.1/a.pdf', 'https://localhost/a.pdf', 'javascript:alert(1)'):
            row = self.guide()
            row['fullText']['url'] = value
            self.rejected(row, contains='url')
        for owner, field in (('fullText', 'checkedAt'), ('review', 'reviewedAt')):
            for value in ('2026-10-02T00:00:00', '2026-10-03T00:00:00Z', {},
                          '0001-01-01T00:00:00+23:00', '9999-12-31T23:59:00-23:00'):
                row = self.guide()
                row[owner][field] = value
                with self.subTest(owner=owner, value=value):
                    self.rejected(row, contains=field)

    def test_retrieval_time_cannot_follow_review_time(self):
        row = self.guide()
        row['review']['reviewedAt'] = '2026-10-01T23:00:00Z'
        self.rejected(row, contains='reviewedAt')

    def test_full_text_edition_pdf_format_page_count_and_hashes_are_required(self):
        for field, value in [('edition', ''), ('format', 'html'), ('pageCount', 0),
                            ('pageCount', True), ('sha256', 'bad'), ('textSha256', None)]:
            row = self.guide()
            row['fullText'][field] = value
            with self.subTest(field=field):
                self.rejected(row, contains=field)

    def test_learning_order_is_integer_one_through_six_and_status_is_known(self):
        for field, value in [('learningOrder', 0), ('learningOrder', 7), ('learningOrder', True),
                            ('learningOrder', '1'), ('status', 'verified'), ('status', [])]:
            row = self.guide()
            row[field] = value
            self.rejected(row, contains=field)

    def test_malformed_nested_types_report_errors_instead_of_crashing(self):
        for field, value in [('guide', []), ('overview', {}), ('fullText', []), ('review', None),
                            ('claimEvidence', {}), ('claimEvidence', [None]), ('paperId', []),
                            ('primaryDomain', [])]:
            row = self.guide()
            row[field] = value
            datasets = {'AI': {'schemaVersion': 1, 'primaryDomain': 'AI', 'guides': [row]}}
            with self.subTest(field=field):
                report = gate.validate_guides(datasets, self.catalog, as_of=date(2026, 10, 2))
                self.assertFalse(report['ok'])
                self.assertEqual(report['readyCount'], 0)
        for field in ('section', 'classification', 'sourcePages', 'context', 'claim', 'locator'):
            row = self.guide()
            row['claimEvidence'][0][field] = []
            self.rejected(row)

    def test_malformed_datasets_catalog_and_guide_rows_are_structured_errors(self):
        for datasets in (None, [], {'BOGUS': {}}, {'AI': []},
            {'AI': {'schemaVersion': True, 'primaryDomain': 'AI', 'guides': []}},
            {'AI': {'schemaVersion': 1, 'primaryDomain': 'CV', 'guides': []}},
            {'AI': {'schemaVersion': 1, 'primaryDomain': 'AI', 'guides': {}}},
            {'AI': {'schemaVersion': 1, 'primaryDomain': 'AI', 'guides': [None]}}):
            report = gate.validate_guides(datasets, [], as_of=date(2026, 10, 2))
            self.assertFalse(report['ok'], report)
        row = self.guide()
        for records in (None, {}, [None], [{'id': []}]):
            report = gate.validate_guides(self.datasets([row]), records, as_of=date(2026, 10, 2))
            self.assertFalse(report['ok'], report)

    def test_empty_and_sparse_inventories_are_ok_only_without_strict_completion(self):
        for datasets in ({}, self.datasets([])):
            report = gate.validate_guides(datasets, [], as_of=date(2026, 10, 2))
            self.assertTrue(report['ok'])
            self.assertFalse(report['complete'])
            self.assertEqual(report['domainCounts'], dict.fromkeys(DOMAINS, 0))
            self.assertFalse(gate.validate_guides(datasets, [], as_of=date(2026, 10, 2),
                                                 require_complete=True)['ok'])

    def test_malformed_or_symlink_loop_source_root_reports_an_input_error(self):
        loop = self.root / 'loop'
        loop.symlink_to(loop)
        for source_root in ([], {}, loop):
            with self.subTest(source_root=str(source_root)):
                try:
                    report = gate.validate_guides({}, [], as_of=date(2026, 10, 2), source_root=source_root)
                except (TypeError, ValueError, RuntimeError, OSError) as exc:
                    self.fail(f'malformed source root escaped structured reporting: {exc}')
                self.assertFalse(report['ok'])
                self.assertTrue(any('source_root' in error for error in report['errors']))

    def test_complete_requires_thirty_ready_six_per_domain_and_no_candidates(self):
        rows = [self.guide(domain, order) for domain in DOMAINS for order in range(1, 7)]
        report = self.audit(rows, originals=True, strict=True)
        self.assertTrue(report['ok'], report['errors'])
        self.assertTrue(report['complete'])
        self.assertEqual(report['readyCount'], 30)
        self.assertEqual(report['domainCounts'], dict.fromkeys(DOMAINS, 6))
        self.assertEqual(report['fullTextBytesRechecked'], 30)
        draft = self.guide('AI', 7)
        draft = {key: draft[key] for key in ('paperId', 'title', 'primaryDomain')}
        draft['status'] = 'candidate'
        report = self.audit(rows + [draft])
        self.assertTrue(report['ok'])
        self.assertEqual(report['readyCount'], 30)
        self.assertFalse(report['complete'])
        self.assertFalse(self.audit(rows[:-1], strict=True)['ok'])

    def test_as_of_reuses_catalog_timezone_and_rejects_naive_datetime(self):
        row = self.guide()
        report = gate.validate_guides(self.datasets([row]), self.catalog,
            as_of=datetime(2026, 10, 1, 18, 0, tzinfo=timezone.utc))
        self.assertTrue(report['ok'], report['errors'])
        with self.assertRaises(ValueError):
            gate.validate_guides({}, [], as_of=datetime(2026, 10, 2))

    def test_escaped_lone_surrogates_on_cited_or_uncited_pages_are_structured_errors(self):
        for page_index in (1, 0):
            row = self.guide()
            path = self.root / row['fullText']['textFile']
            data = json.loads(path.read_text())
            data['pages'][page_index]['text'] = '\ud800' + data['pages'][page_index]['text']
            # The file is valid UTF-8 JSON; its escaped string is not UTF-8 text.
            path.write_bytes(json.dumps(data, ensure_ascii=True).encode('utf-8'))
            row['fullText']['textSha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.subTest(pdf_page=page_index + 1):
                try:
                    report = self.audit([row], originals=True)
                except UnicodeError as exc:
                    self.fail(f'extraction text escaped structured reporting: {exc}')
                self.assertFalse(report['ok'], report)
                self.assertEqual(report['readyCount'], 0)
                self.assertEqual(report['fullTextBytesRechecked'], 1)
                self.assertTrue(any('fullText.textFile' in error for error in report['errors']))


class GuideCliTests(GuideFixture):
    def write_inventory(self, rows=()):
        guides_root, catalog_root = self.root / 'guides', self.root / 'catalog'
        guides_root.mkdir(exist_ok=True)
        catalog_root.mkdir(exist_ok=True)
        for domain in DOMAINS:
            (guides_root / (domain + '.json')).write_text(json.dumps(self.datasets(rows)[domain]), encoding='utf-8')
            (catalog_root / (domain + '.json')).write_text(json.dumps({'schemaVersion': 1,
                'primaryDomain': domain, 'papers': [row for row in self.catalog if row['primaryDomain'] == domain]}),
                encoding='utf-8')
        return guides_root, catalog_root

    def cli(self, guide_root, catalog_root, *extra):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/classic_guides.py'),
            '--guides-root', str(guide_root), '--catalog-root', str(catalog_root),
            '--as-of', '2026-10-02', *map(str, extra)], capture_output=True, text=True, cwd=ROOT)

    def test_cli_incomplete_and_missing_guide_files_are_empty_without_writes(self):
        guides_root, catalog_root = self.write_inventory()
        (guides_root / 'AI.json').unlink()
        output = self.root / 'report.json'
        for strict, expected in ((False, 0), (True, 1)):
            result = self.cli(guides_root, catalog_root, '--report', output,
                              *(['--require-complete'] if strict else []))
            self.assertEqual(result.returncode, expected, result.stderr)
            report = json.loads(result.stdout)
            self.assertFalse(report['complete'])
            self.assertEqual(report['readyCount'], 0)
            self.assertEqual(json.loads(output.read_text()), report)
            self.assertFalse((guides_root / 'AI.json').exists())

    def test_cli_complete_and_source_root_report_actual_rechecks(self):
        rows = [self.guide(domain, order) for domain in DOMAINS for order in range(1, 7)]
        guide_root, catalog_root = self.write_inventory(rows)
        result = self.cli(guide_root, catalog_root, '--require-complete', '--source-root', self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['complete'])
        self.assertEqual(report['fullTextBytesRechecked'], 30)

    def test_cli_rejects_invalid_json_duplicate_keys_nan_and_catalog_missing(self):
        for mode in ('json', 'keys', 'nan', 'catalog'):
            guides_root, catalog_root = self.write_inventory()
            if mode == 'catalog':
                (catalog_root / 'AI.json').unlink()
            else:
                contents = {'json': '{broken', 'keys': '{"guides":[],"guides":[]}',
                    'nan': '{"schemaVersion":1,"primaryDomain":"AI","guides":[],"x":NaN}'}
                (guides_root / 'AI.json').write_text(contents[mode])
            result = self.cli(guides_root, catalog_root)
            with self.subTest(mode=mode):
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertFalse(json.loads(result.stdout)['ok'])

    def test_report_cannot_overwrite_guides_catalog_or_original_sources(self):
        row = self.guide()
        guides_root, catalog_root = self.write_inventory([row])
        for path in [guides_root / 'AI.json', catalog_root / 'AI.json', self.root / row['fullText']['sourceFile']]:
            before = path.read_bytes()
            result = self.cli(guides_root, catalog_root, '--source-root', self.root, '--report', path)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertFalse(json.loads(result.stdout)['ok'])
            self.assertEqual(path.read_bytes(), before)

    def test_report_cannot_overwrite_external_targets_of_guide_or_catalog_symlinks(self):
        with tempfile.TemporaryDirectory() as external_root:
            for kind in ('guide', 'catalog'):
                row = self.guide()
                guides_root, catalog_root = self.write_inventory([row])
                input_path = (guides_root if kind == 'guide' else catalog_root) / 'AI.json'
                target = Path(external_root) / (kind + '-AI.json')
                before = input_path.read_bytes()
                target.write_bytes(before)
                input_path.unlink()
                input_path.symlink_to(target)
                try:
                    result = self.cli(guides_root, catalog_root, '--report', target)
                    with self.subTest(kind=kind):
                        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                        self.assertFalse(json.loads(result.stdout)['ok'])
                        self.assertEqual(target.read_bytes(), before)
                finally:
                    input_path.unlink()

    def test_report_hardlink_aliases_cannot_overwrite_loaded_inputs(self):
        row = self.guide()
        guides_root, catalog_root = self.write_inventory([row])
        paths = {'guide': guides_root / 'AI.json', 'catalog': catalog_root / 'AI.json',
                 'pdf': self.root / row['fullText']['sourceFile'],
                 'extraction': self.root / row['fullText']['textFile']}
        with tempfile.TemporaryDirectory() as external_root:
            for kind, input_path in paths.items():
                before = input_path.read_bytes()
                alias = Path(external_root) / (kind + '-report.json')
                alias.hardlink_to(input_path)
                result = self.cli(guides_root, catalog_root, '--source-root', self.root, '--report', alias)
                with self.subTest(kind=kind):
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertFalse(json.loads(result.stdout)['ok'])
                    self.assertEqual(input_path.read_bytes(), before)
                    self.assertEqual(alias.read_bytes(), before)
                # Restore fixtures after RED mutates input bytes, keeping cases independent.
                input_path.write_bytes(before)


if __name__ == '__main__':
    unittest.main()
