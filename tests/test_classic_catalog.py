"""Catalog gates use synthetic papers and real temporary capture files.

These fixtures demonstrate rejection behavior; none is a research deliverable.
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
    import classic_catalog as catalog
except ImportError:
    catalog = None


class CatalogFixture(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(catalog, 'classic catalog gate is not implemented')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def capture(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return {'path': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def source(self, name, url, excerpt, kind, text=None):
        return {'kind': kind, 'url': url, 'checkedAt': '2026-09-30T01:00:00Z',
                'locator': 'section 2', 'excerpt': excerpt, 'reviewed': True,
                'capture': self.capture(name, text or excerpt)}

    def paper(self, name='example', domain='GNC'):
        title = 'An Example of Estimation ' + name
        authors = ['Alice Example', 'Boris Sample']
        doi = '10.1234/' + name
        arxiv = '1001.00001' if name == 'example' else None
        metadata = f'{title}\nAlice Example; Boris Sample\n2010\nExample Journal\n{doi}\n' + (arxiv or '')
        primary = self.source(name + '/metadata.txt', 'https://publisher.example.org/' + name,
                              metadata, 'publisher')
        primary['observed'] = {'title': title, 'authors': authors[:], 'year': 2010,
                               'venue': 'Example Journal', 'doi': doi}
        if arxiv:
            primary['observed']['arxiv'] = arxiv
        excerpt = title + ' is foundational for recursive estimation.'
        course = self.source(name + '/course.txt', 'https://course.example.edu/' + name,
                             excerpt, 'course', 'University course\n' + excerpt)
        survey = self.source(name + '/survey.txt', 'https://survey.example.net/' + name,
                             excerpt, 'survey', 'Independent research survey\n' + excerpt)
        for evidence in [course, survey]:
            evidence['supportsPaperId'] = 'classic:' + name
        return {'id': 'classic:' + name, 'title': title, 'authors': authors, 'year': 2010,
                'venue': 'Example Journal', 'primaryDomain': domain, 'status': 'verified',
                'canonicalUrl': 'https://doi.org/' + doi, 'identifiers': {'doi': doi, 'arxiv': arxiv},
                'classicRationale': 'Introduced a reusable estimation method with sustained teaching and survey coverage.',
                'bibliographicEvidence': [primary], 'classicEvidence': [course, survey]}

    def validate(self, record, as_of=date(2026, 10, 1)):
        return catalog.validate_record(record, as_of=as_of, evidence_root=self.root)

    def rejected(self, record):
        result = self.validate(record)
        self.assertFalse(result['eligible'])
        self.assertTrue(result['errors'])
        return result


class IdentityTests(CatalogFixture):
    def test_doi_prefix_url_case_and_escaped_slash_have_one_identity(self):
        for raw in ['10.1234/ABC', 'DOI:10.1234/abc',
                    'https://doi.org/10.1234/ABC', 'http://dx.doi.org/10.1234%2FABC']:
            with self.subTest(raw=raw):
                self.assertEqual(catalog.normalize_doi(raw), '10.1234/abc')

    def test_arxiv_revision_and_pdf_url_are_same_paper(self):
        for raw in ['1001.00001', 'arXiv:1001.00001v3', 'https://arxiv.org/pdf/1001.00001v2.pdf']:
            self.assertEqual(catalog.normalize_arxiv(raw), '1001.00001')
        self.assertEqual(catalog.normalize_arxiv('astro-ph/0601001v2'), 'astro-ph/0601001')

    def test_invalid_identifiers_cannot_be_treated_as_real_doi(self):
        for raw in ['not-a-doi', 'https://evil.example/10.1234/abc', '10.12/abc', '', 123]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                catalog.normalize_doi(raw)
        for raw in ['1000.00001', '1001.00', 'not-arxiv']:
            with self.assertRaises(ValueError):
                catalog.normalize_arxiv(raw)

    def test_shared_title_alias_deduplicates_preprint_with_changed_title(self):
        first = self.paper()
        second = copy.deepcopy(first)
        second['id'] = 'classic:preprint'
        second['title'] = 'Different Formal Title'
        second['titleAliases'] = [first['title'].upper().replace(' ', '  ')]
        second['identifiers'] = {}
        self.assertTrue(catalog.identity_keys(first) & catalog.identity_keys(second))


class QualificationTests(CatalogFixture):
    def test_short_title_alias_does_not_identify_a_paper_inside_learning(self):
        paper = self.paper()
        paper['titleAliases'] = ['NIN']
        source = paper['classicEvidence'][1]
        source['excerpt'] = 'CS 7643 Deep Learning'
        source['capture'] = self.capture('course-header.txt', source['excerpt'])
        self.rejected(paper)

    def test_punctuated_alias_does_not_match_partial_words_across_whitespace(self):
        paper = self.paper()
        paper['titleAliases'] = ['U-Net']
        source = paper['classicEvidence'][1]
        source['excerpt'] = 'LeCun et al. developed a CNN for phoneme recognition.'
        source['capture'] = self.capture('phoneme.txt', source['excerpt'])
        self.rejected(paper)

    def test_explicit_alias_keeps_punctuation_and_line_break_variants_usable(self):
        for excerpt in ['NIN is assigned reading.', 'U-Net is assigned reading.',
                        'U\nNet is assigned reading.', 'UNet is assigned reading.']:
            paper = self.paper()
            paper['titleAliases'] = ['NIN', 'U-Net']
            source = paper['classicEvidence'][1]
            source['excerpt'] = excerpt
            source['capture'] = self.capture('explicit-alias.txt', excerpt)
            with self.subTest(excerpt=excerpt):
                self.assertTrue(self.validate(paper)['eligible'])

    def test_reviewed_captured_metadata_and_two_independent_sources_pass(self):
        result = self.validate(self.paper())
        self.assertTrue(result['eligible'], result)
        self.assertEqual(result['errors'], [])

    def test_complete_candidate_stays_unpublishable(self):
        paper = self.paper()
        paper['status'] = 'candidate'
        result = self.validate(paper)
        self.assertFalse(result['eligible'])
        self.assertEqual(result['errors'], [])

    def test_incomplete_candidate_is_reported_without_counting_as_verified(self):
        result = self.validate({'id': 'classic:draft', 'title': 'Unreviewed draft',
                                'primaryDomain': 'AI', 'status': 'candidate'})
        self.assertFalse(result['eligible'])
        self.assertEqual(result['errors'], [])
        self.assertTrue(result['warnings'])

    def test_incomplete_or_et_al_author_list_cannot_pass_review(self):
        for authors in [[], ['Alice Example', 'et al.'], ['Alice Example']]:
            paper = self.paper()
            paper['authors'] = authors
            self.rejected(paper)

    def test_observed_metadata_must_match_title_year_venue_and_identifiers(self):
        for field, wrong in [('title', 'A Different Paper'), ('year', 2011),
                             ('venue', 'Invented Conference'), ('doi', '10.1234/other'),
                             ('arxiv', '1101.00001')]:
            paper = self.paper()
            paper['bibliographicEvidence'][0]['observed'][field] = wrong
            self.rejected(paper)

    def test_regex_valid_but_unverified_identifier_is_rejected(self):
        paper = self.paper()
        del paper['bibliographicEvidence'][0]['observed']['doi']
        self.rejected(paper)

    def test_observed_metadata_cannot_claim_values_missing_from_source(self):
        paper = self.paper()
        source = paper['bibliographicEvidence'][0]
        source['excerpt'] = 'The page does not contain this bibliography.'
        source['capture'] = self.capture('missing.txt', source['excerpt'])
        self.rejected(paper)

    def test_exact_five_year_anniversary_and_unknown_date_are_conservative(self):
        paper = self.paper()
        paper['year'] = 2021
        metadata = paper['bibliographicEvidence'][0]
        metadata['observed']['year'] = 2021
        metadata['excerpt'] = metadata['excerpt'].replace('2010', '2021')
        metadata['capture'] = self.capture('2021.txt', metadata['excerpt'])
        cases = [(None, '2026-10-01', False), (None, '2026-12-31', True),
                 ('2021-10-01', '2026-09-30', False), ('2021-10-01', '2026-10-01', True),
                 ('2021-10-02', '2026-10-01', False)]
        for published, as_of, expected in cases:
            if published:
                paper['publicationDate'] = published
                metadata['observed']['publicationDate'] = published
            else:
                paper.pop('publicationDate', None)
                metadata['observed'].pop('publicationDate', None)
            metadata['excerpt'] = f"{paper['title']} Alice Example Boris Sample 2021 Example Journal 10.1234/example 1001.00001 " + (published or '')
            metadata['capture'] = self.capture('2021.txt', metadata['excerpt'])
            with self.subTest(published=published, as_of=as_of):
                self.assertEqual(self.validate(paper, date.fromisoformat(as_of))['eligible'], expected)

    def test_publication_date_and_year_must_agree(self):
        paper = self.paper()
        paper['publicationDate'] = '2011-01-01'
        self.rejected(paper)

    def test_precise_publication_date_requires_source_verification(self):
        paper = self.paper()
        paper['publicationDate'] = '2010-01-01'
        self.rejected(paper)

    def test_early_paper_without_doi_uses_reviewed_url_and_internal_id(self):
        paper = self.paper()
        paper['identifiers'] = {}
        source = paper['bibliographicEvidence'][0]
        source['observed'].pop('doi')
        source['observed'].pop('arxiv')
        paper['canonicalUrl'] = source['url']
        self.assertTrue(self.validate(paper)['eligible'])

    def test_unrelated_canonical_doi_cannot_pass_verified_bibliography(self):
        paper = self.paper()
        paper['canonicalUrl'] = 'https://doi.org/10.1234/another-paper'
        self.rejected(paper)

    def test_identifier_prefix_or_changed_punctuation_is_not_located_metadata(self):
        for kind, truncated in [('doi', '10.1234/exam'), ('doi', '10.1234/ex-ample'),
                                ('arxiv', '1001.0000')]:
            paper = self.paper()
            paper['identifiers'][kind] = truncated
            paper['bibliographicEvidence'][0]['observed'][kind] = truncated
            if kind == 'doi':
                paper['canonicalUrl'] = 'https://doi.org/' + truncated
            with self.subTest(kind=kind, value=truncated):
                self.rejected(paper)

    def test_classic_basis_identifier_prefix_is_not_this_paper(self):
        paper = self.paper()
        source = paper['classicEvidence'][1]
        source['excerpt'] = '10.1234/example-more is widely taught.'
        source['capture'] = self.capture('wrong-classic-id.txt', source['excerpt'])
        self.rejected(paper)

    def test_exact_captured_identifier_urls_and_arxiv_revisions_pass(self):
        paper = self.paper()
        source = paper['bibliographicEvidence'][0]
        source['excerpt'] = source['excerpt'].replace('10.1234/example', 'https://doi.org/10.1234%2Fexample')
        source['excerpt'] = source['excerpt'].replace('1001.00001', 'https://arxiv.org/pdf/1001.00001v3.pdf')
        source['capture'] = self.capture('url-metadata.txt', source['excerpt'])
        self.assertTrue(self.validate(paper)['eligible'])

    def test_provider_group_ownership_propagates_to_ungrouped_same_domain(self):
        paper = self.paper()
        one, two = paper['classicEvidence']
        one['url'] = 'https://course.stanford.edu/one'
        two['url'] = 'https://stanford.ai/two'
        two['providerGroup'] = 'stanford'
        third = self.source('third.txt', 'https://library.stanford.edu/three', one['excerpt'],
                            'course', 'Third independent-looking capture\n' + one['excerpt'])
        third['supportsPaperId'] = paper['id']
        third['providerGroup'] = 'stanford'
        paper['classicEvidence'].append(third)
        self.rejected(paper)

    def test_extreme_review_timezone_is_reported_without_aborting_audit(self):
        for timestamp in ['0001-01-01T00:00:00+23:00', '9999-12-31T23:59:00-23:00']:
            paper = self.paper()
            paper['classicEvidence'][0]['checkedAt'] = timestamp
            with self.subTest(timestamp=timestamp):
                self.rejected(paper)

    def test_beijing_date_is_used_and_naive_datetime_is_rejected(self):
        paper = self.paper()
        paper['bibliographicEvidence'][0]['checkedAt'] = '2026-09-30T23:30:00+08:00'
        self.assertTrue(self.validate(paper, datetime(2026, 9, 30, 16, 0, tzinfo=timezone.utc))['eligible'])
        with self.assertRaises(ValueError):
            self.validate(paper, datetime(2026, 10, 1))

    def test_future_or_unreviewed_source_is_rejected(self):
        for value in ['2026-10-02T00:00:00+08:00', '2026-09-30T00:00:00']:
            paper = self.paper()
            paper['classicEvidence'][0]['checkedAt'] = value
            self.rejected(paper)
        paper = self.paper()
        paper['bibliographicEvidence'][0]['reviewed'] = False
        self.rejected(paper)

    def test_two_subdomains_of_one_institution_are_not_independent(self):
        paper = self.paper()
        paper['classicEvidence'][0]['url'] = 'https://course.example.ac.uk/one'
        paper['classicEvidence'][1]['url'] = 'https://library.example.ac.uk/two'
        self.rejected(paper)

    def test_identical_capture_mirror_or_provider_group_cannot_count_twice(self):
        for mode in ['capture', 'origin', 'group']:
            paper = self.paper()
            one, two = paper['classicEvidence']
            if mode == 'capture':
                two['capture'] = copy.deepcopy(one['capture'])
            elif mode == 'origin':
                two['originUrl'] = one['url']
            else:
                one['providerGroup'] = two['providerGroup'] = 'same-university'
            self.rejected(paper)

    def test_citation_count_is_not_an_independent_classic_basis(self):
        paper = self.paper()
        paper['classicEvidence'][1]['kind'] = 'citation_count'
        self.rejected(paper)

    def test_evidence_for_another_paper_cannot_be_reused(self):
        paper = self.paper()
        paper['classicEvidence'][1]['supportsPaperId'] = 'classic:other'
        self.rejected(paper)

    def test_supports_id_alone_cannot_turn_unrelated_text_into_classic_basis(self):
        paper = self.paper()
        source = paper['classicEvidence'][1]
        source['excerpt'] = 'This course teaches a different subject.'
        source['capture'] = self.capture('unrelated.txt', source['excerpt'])
        self.rejected(paper)

    def test_missing_corrupt_and_unlocatable_capture_are_rejected(self):
        for mode in ['missing', 'corrupt', 'quote']:
            paper = self.paper()
            source = paper['classicEvidence'][0]
            if mode == 'missing':
                (self.root / source['capture']['path']).unlink()
            elif mode == 'corrupt':
                (self.root / source['capture']['path']).write_text('changed')
            else:
                source['excerpt'] = 'A claim absent from the original capture.'
            self.rejected(paper)

    def test_capture_path_cannot_escape_root_through_parent_or_symlink(self):
        paper = self.paper()
        paper['classicEvidence'][0]['capture']['path'] = '../outside.txt'
        self.rejected(paper)
        outside = Path(self.temp.name).parent / (Path(self.temp.name).name + '-outside.txt')
        outside.write_text('outside')
        self.addCleanup(outside.unlink)
        link = self.root / 'escape.txt'
        link.symlink_to(outside)
        paper = self.paper()
        paper['classicEvidence'][0]['capture'] = {'path': 'escape.txt',
                                                 'sha256': hashlib.sha256(b'outside').hexdigest()}
        self.rejected(paper)

    def test_malformed_record_types_and_unsafe_urls_are_reported(self):
        for record in [None, [], 'paper', 123]:
            self.rejected(record)
        for field, wrong in [('authors', 'Alice'), ('year', True), ('year', '2010'),
                             ('identifiers', []), ('classicEvidence', {}),
                             ('canonicalUrl', 'javascript:alert(1)'), ('status', 'published')]:
            paper = self.paper()
            paper[field] = wrong
            self.rejected(paper)


class DirectoryTests(CatalogFixture):
    def setUp(self):
        super().setUp()
        self.assertTrue(callable(getattr(catalog, 'validate_catalog', None)),
                        'catalog-wide readiness reporting is not implemented')

    def write_domains(self, records=()):
        directory = self.root / 'catalog'
        directory.mkdir(exist_ok=True)
        for domain in ('AI', 'SLAM', 'GNC', 'CV', 'UAV'):
            payload = {'schemaVersion': 1, 'primaryDomain': domain,
                       'papers': [r for r in records if r['primaryDomain'] == domain]}
            (directory / (domain + '.json')).write_text(json.dumps(payload), encoding='utf-8')
        return directory

    def audit(self, records, require_complete=False):
        return catalog.validate_catalog(records, as_of=date(2026, 10, 1),
                                        evidence_root=self.root, require_complete=require_complete)

    def test_empty_catalog_is_not_ready_for_200_paper_acceptance(self):
        report = self.audit([])
        self.assertTrue(report['ok'])
        self.assertFalse(report['complete'])
        self.assertEqual(report['verifiedCount'], 0)
        self.assertEqual(report['domainCounts'], {'AI': 0, 'SLAM': 0, 'GNC': 0, 'CV': 0, 'UAV': 0})
        self.assertFalse(self.audit([], True)['ok'])

    def test_candidates_never_count_towards_domain_quotas(self):
        paper = self.paper()
        paper['status'] = 'candidate'
        report = self.audit([paper])
        self.assertEqual(report['candidateCount'], 1)
        self.assertEqual(report['verifiedCount'], 0)
        self.assertFalse(report['complete'])

    def test_cross_domain_doi_and_preprint_identity_collision_blocks_both(self):
        for identifier in ('doi', 'arxiv', 'title'):
            first = self.paper()
            second = self.paper('second', 'AI')
            if identifier == 'title':
                second['titleAliases'] = [first['title']]
            else:
                second['identifiers'][identifier] = first['identifiers'][identifier]
            report = self.audit([first, second])
            with self.subTest(identifier=identifier):
                self.assertFalse(report['ok'])
                self.assertTrue(report['duplicates'])
                self.assertEqual(report['verifiedCount'], 0)

    def test_candidate_duplicate_blocks_verified_counterpart_until_resolved(self):
        first = self.paper()
        candidate = {'id': 'classic:draft', 'title': 'Unconfirmed preprint', 'primaryDomain': 'AI',
                     'status': 'candidate', 'identifiers': {'doi': 'https://doi.org/10.1234/EXAMPLE'}}
        report = self.audit([first, candidate])
        self.assertFalse(report['ok'])
        self.assertEqual(report['verifiedCount'], 0)

    def test_complete_means_200_unique_verified_with_exactly_40_per_domain(self):
        records = [self.paper(f'{domain.lower()}-{n:02d}', domain)
                   for domain in ('AI', 'SLAM', 'GNC', 'CV', 'UAV') for n in range(40)]
        report = self.audit(records, True)
        self.assertTrue(report['ok'], report['errors'][:4])
        self.assertTrue(report['complete'])
        self.assertEqual(report['verifiedCount'], 200)
        # Retagging one record preserves 200 total but breaks the 40-per-domain requirement.
        records[0]['primaryDomain'] = 'SLAM'
        report = self.audit(records, True)
        self.assertFalse(report['ok'])
        self.assertEqual(report['verifiedCount'], 200)
        self.assertEqual(report['domainCounts']['AI'], 39)
        self.assertEqual(report['domainCounts']['SLAM'], 41)

    def test_missing_domain_invalid_json_and_wrong_domain_are_reported(self):
        for mode in ('missing', 'json', 'domain', 'schema', 'papers'):
            directory = self.write_domains()
            path = directory / 'AI.json'
            if mode == 'missing':
                path.unlink()
            elif mode == 'json':
                path.write_text('{bad json')
            else:
                payload = json.loads(path.read_text())
                payload[{'domain': 'primaryDomain', 'schema': 'schemaVersion', 'papers': 'papers'}[mode]] = {}
                path.write_text(json.dumps(payload))
            report = catalog.audit_directory(directory, as_of=date(2026, 10, 1), evidence_root=self.root)
            with self.subTest(mode=mode):
                self.assertFalse(report['ok'])
                self.assertFalse(report['complete'])
                self.assertTrue(report['errors'])

    def test_duplicate_json_keys_and_nan_are_rejected(self):
        for content in ['{"schemaVersion":1,"primaryDomain":"AI","papers":[],"papers":[]}',
                        '{"schemaVersion":1,"primaryDomain":"AI","papers":[],"count":NaN}']:
            directory = self.write_domains()
            (directory / 'AI.json').write_text(content)
            report = catalog.audit_directory(directory, as_of=date(2026, 10, 1), evidence_root=self.root)
            self.assertFalse(report['ok'])

    def test_paper_cannot_be_loaded_from_wrong_primary_domain_file(self):
        paper = self.paper()
        directory = self.write_domains()
        (directory / 'AI.json').write_text(json.dumps({'schemaVersion': 1, 'primaryDomain': 'AI',
                                                       'papers': [paper]}))
        report = catalog.audit_directory(directory, as_of=date(2026, 10, 1), evidence_root=self.root)
        self.assertFalse(report['ok'])
        self.assertEqual(report['verifiedCount'], 0)

    def test_nested_malformed_source_types_are_errors_without_traceback(self):
        for field, value in [('kind', []), ('checkedAt', {}), ('capture', []), ('url', []),
                             ('providerGroup', []), ('observed', []), ('excerpt', {})]:
            paper = self.paper()
            paper['bibliographicEvidence'][0][field] = value
            with self.subTest(field=field):
                self.assertFalse(self.audit([paper])['ok'])
        paper = self.paper()
        paper['classicEvidence'][0]['kind'] = []
        self.assertFalse(self.audit([paper])['ok'])

    def test_cli_reports_empty_inventory_and_strict_exit_is_failure(self):
        directory = self.write_domains()
        command = [sys.executable, str(ROOT / 'scripts/classic_catalog.py'), '--catalog-dir', str(directory),
                   '--evidence-root', str(self.root), '--as-of', '2026-10-01']
        for strict, expected in [(False, 0), (True, 1)]:
            output = self.root.parent / (self.root.name + '-report.json')
            self.addCleanup(lambda p=output: p.unlink(missing_ok=True))
            result = subprocess.run(command + ['--report', str(output)] + (['--require-complete'] if strict else []),
                                    text=True, capture_output=True, cwd=ROOT)
            self.assertEqual(result.returncode, expected, result.stderr)
            report = json.loads(result.stdout)
            self.assertFalse(report['complete'])
            self.assertEqual(report['verifiedCount'], 0)
            self.assertEqual(json.loads(output.read_text()), report)

    def test_cli_report_cannot_overwrite_input_corpus_or_evidence(self):
        directory = self.write_domains()
        original = (directory / 'AI.json').read_bytes()
        command = [sys.executable, str(ROOT / 'scripts/classic_catalog.py'), '--catalog-dir', str(directory),
                   '--evidence-root', str(self.root), '--as-of', '2026-10-01',
                   '--report', str(directory / 'AI.json')]
        result = subprocess.run(command, text=True, capture_output=True, cwd=ROOT)
        self.assertEqual(result.returncode, 1)
        self.assertEqual((directory / 'AI.json').read_bytes(), original)
        self.assertFalse(json.loads(result.stdout)['ok'])


if __name__ == '__main__':
    unittest.main()
