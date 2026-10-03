"""Scheduling behavior; fixture papers are synthetic and never delivery counts."""
import copy
import json
import shutil
import sys
import tempfile
import unittest
from collections import Counter
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
try:
    import classic_papers as cp
except ImportError:
    cp = None

FIELDS = ('AI', 'SLAM', 'GNC', 'CV', 'UAV')
SECTIONS = ('problem', 'method', 'contribution', 'applicability', 'limitations', 'readingAdvice')


def make_pool(n=6):
    return [dict(id=f'fixture:{d}:{i}', title=f'Synthetic {d} {i}', authors=['Synthetic Author'],
                 year=2000, venue='Synthetic test fixture', primaryDomain=d,
                 canonicalUrl=f'https://example.org/{d}/{i}', identifiers={},
                 classicRationale='Synthetic rationale, not a real accepted paper.',
                 classicEvidence=[dict(kind='course', url='https://example.org/a', locator='fixture'),
                                  dict(kind='survey', url='https://example.net/b', locator='fixture')],
                 learningOrder=i, overview='概' * 160,
                 guide={k: '导' * 100 for k in SECTIONS},
                 fullText=dict(url='https://example.org/full.pdf', format='pdf', sha256='a' * 64,
                               pageCount=2, edition='Synthetic fixture edition'),
                 sourceLocators=[dict(section='method', classification='paperFact', locator='PDF1')],
                 guideInputSha256='b' * 64, catalogInputSha256='c' * 64)
            for d in FIELDS for i in range(1, n + 1)]


def make_archive(pool, day, ids):
    rows = {p['id']: p for p in pool}
    items = [dict(copy.deepcopy(rows[i]), classicReread=False, previousRecommendationDate=None) for i in ids]
    edition = dict(schemaVersion=1, kind='classicEdition', timezone='Asia/Shanghai',
                   anchorDate='2026-09-30', selectionRuleVersion='classic-calendar-v1',
                   recommendationDate=day, publishedAt=day + 'T12:00:00+08:00', itemCount=2, items=items)
    return dict(schemaVersion=1, kind='classicArchive', timezone='Asia/Shanghai',
                anchorDate='2026-09-30', selectionRuleVersion='classic-calendar-v1', editions={day: edition})


class ClassicSchedulingTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(cp, 'independent classic scheduling is not implemented')
        self.pool = make_pool()

    def ids(self, queue, day):
        return [p['id'] for p in queue['slots'][day]['items']]

    def test_literal_anchor_pairs_do_not_advance_by_run_count(self):
        expected = [('AI', 'SLAM'), ('GNC', 'CV'), ('UAV', 'AI'), ('SLAM', 'GNC'), ('CV', 'UAV')]
        for day, pair in zip(['2026-09-30', '2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04'], expected):
            self.assertEqual(cp.rotation_domains(day), pair)
            self.assertEqual(cp.rotation_domains(day), pair)
        self.assertEqual(cp.rotation_domains('2026-10-05'), ('AI', 'SLAM'))

    def test_beijing_midnight_and_aware_offsets_determine_the_calendar(self):
        self.assertEqual(cp.rotation_domains(datetime.fromisoformat('2026-09-30T15:59:59+00:00')), ('AI', 'SLAM'))
        self.assertEqual(cp.rotation_domains(datetime.fromisoformat('2026-09-30T16:00:00+00:00')), ('GNC', 'CV'))
        self.assertEqual(cp.beijing_date(datetime.fromisoformat('2026-09-30T09:00:00-07:00')), date(2026, 10, 1))

    def test_invalid_or_naive_dates_are_refused(self):
        for value in [None, True, 0, '2026-2-3', '2026-02-30', '2026-10-03T10:00:00', datetime(2026, 10, 3)]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                cp.beijing_date(value)

    def test_fifteen_real_calendar_slots_have_thirty_unique_papers(self):
        q, report = cp.prepare_queue(self.pool, '2026-10-03')
        self.assertEqual(len(q['slots']), 15)
        self.assertEqual(self.ids(q, '2026-10-03'), ['fixture:SLAM:1', 'fixture:GNC:1'])
        self.assertEqual(self.ids(q, '2026-10-04'), ['fixture:CV:1', 'fixture:UAV:1'])
        self.assertEqual(self.ids(q, '2026-10-05'), ['fixture:AI:1', 'fixture:SLAM:2'])
        all_ids = [p['id'] for s in q['slots'].values() for p in s['items']]
        self.assertEqual(len(set(all_ids)), 30)
        self.assertEqual(report['futureCompleteDays'], 14)
        self.assertEqual(report['futurePaperCount'], 28)

    def test_every_five_day_window_has_two_papers_per_domain(self):
        q, _ = cp.prepare_queue(self.pool, '2026-10-03')
        slots = list(q['slots'].values())
        for i in range(11):
            counts = Counter(p['primaryDomain'] for s in slots[i:i + 5] for p in s['items'])
            self.assertEqual(dict(counts), {d: 2 for d in FIELDS})

    def test_repeat_policy_refuses_89_days_and_accepts_90_in_both_directions(self):
        self.assertFalse(cp.repeat_allowed('2026-10-03', ['2026-07-06']))
        self.assertTrue(cp.repeat_allowed('2026-10-03', ['2026-07-05']))
        self.assertFalse(cp.repeat_allowed('2026-07-06', ['2026-10-03']))
        self.assertTrue(cp.repeat_allowed('2026-07-05', ['2026-10-03']))

    def test_real_rotation_at_88_days_excludes_previously_used_paper(self):
        a = make_archive(self.pool, '2026-07-07', ['fixture:AI:1', 'fixture:SLAM:1'])
        q, _ = cp.prepare_queue(self.pool, '2026-10-03', days=1, archive=a)
        self.assertEqual(self.ids(q, '2026-10-03'), ['fixture:SLAM:2', 'fixture:GNC:1'])

    def test_unrecommended_precedes_an_eligible_earlier_learning_order(self):
        a = make_archive(self.pool, '2026-07-05', ['fixture:SLAM:1', 'fixture:GNC:1'])
        q, _ = cp.prepare_queue(self.pool, '2026-10-03', days=1, archive=a)
        self.assertEqual(self.ids(q, '2026-10-03'), ['fixture:SLAM:2', 'fixture:GNC:2'])

    def test_eligible_rereads_keep_learning_order_before_oldest_date(self):
        pool = make_pool(2)
        a = make_archive(pool, '2026-07-05', ['fixture:SLAM:1', 'fixture:GNC:1'])
        a['editions'].update(make_archive(pool, '2026-06-30', ['fixture:SLAM:2', 'fixture:GNC:2'])['editions'])
        q, _ = cp.prepare_queue(pool, '2026-10-03', days=1, archive=a)
        self.assertEqual(self.ids(q, '2026-10-03'), ['fixture:SLAM:1', 'fixture:GNC:1'])

    def test_existing_future_slots_survive_repreparation_exactly(self):
        q, _ = cp.prepare_queue(self.pool, '2026-10-03')
        before = copy.deepcopy(q)
        q2, _ = cp.prepare_queue(list(reversed(self.pool)), '2026-10-03', existing_queue=q)
        self.assertEqual(q2, before)
        self.assertEqual(q, before)

    def test_future_reservation_outside_window_blocks_backfill_duplicate(self):
        locked, _ = cp.prepare_queue(self.pool, '2026-10-08', days=1)
        q, _ = cp.prepare_queue(self.pool, '2026-10-03', days=1, existing_queue=locked)
        self.assertEqual(self.ids(q, '2026-10-03'), ['fixture:SLAM:2', 'fixture:GNC:2'])
        self.assertEqual(q['slots']['2026-10-08'], locked['slots']['2026-10-08'])

    def test_conflicting_published_combination_is_not_overwritten(self):
        q, _ = cp.prepare_queue(self.pool, '2026-10-03', days=1)
        a = make_archive(self.pool, '2026-10-03', ['fixture:SLAM:2', 'fixture:GNC:2'])
        before = copy.deepcopy(q)
        with self.assertRaises(ValueError):
            cp.prepare_queue(self.pool, '2026-10-03', existing_queue=q, archive=a)
        self.assertEqual(q, before)

    def test_short_pool_stops_at_first_gap_without_one_paper_or_duplicate_fillers(self):
        q, report = cp.prepare_queue(make_pool(1), '2026-10-03')
        self.assertEqual(list(q['slots']), ['2026-10-03', '2026-10-04'])
        self.assertEqual(report['firstMissingDate'], '2026-10-05')
        self.assertEqual(report['readyPaperCount'], 4)
        self.assertTrue(report['lowStock'])
        self.assertTrue(all(len(s['items']) == 2 for s in q['slots'].values()))

    def test_inventory_excludes_published_stock_and_warns_below_fourteen(self):
        q, _ = cp.prepare_queue(self.pool, '2026-10-03')
        a = make_archive(self.pool, '2026-10-03', ['fixture:SLAM:1', 'fixture:GNC:1'])
        report = cp.inventory(q, a, '2026-10-03')
        self.assertEqual(report['readyPaperCount'], 28)
        self.assertEqual(report['futurePaperCount'], 28)
        self.assertFalse(report['lowStock'])
        report = cp.inventory(q, a, '2026-10-12')
        self.assertEqual(report['readyPaperCount'], 12)
        self.assertTrue(report['lowStock'])

    def test_incomplete_or_malformed_pool_cannot_become_ready_queue(self):
        for fault in ['overview', 'guide', 'domain', 'hash', 'year', 'duplicate', 'authors']:
            pool = copy.deepcopy(self.pool)
            if fault == 'overview': pool[0]['overview'] = '概' * 221
            elif fault == 'guide': del pool[0]['guide']['method']
            elif fault == 'domain': pool[0]['primaryDomain'] = 'cross-tags'
            elif fault == 'hash': pool[0]['fullText']['sha256'] = 'invented'
            elif fault == 'year': pool[0]['year'] = True
            elif fault == 'duplicate': pool.append(copy.deepcopy(pool[0]))
            else: pool[0]['authors'] = []
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                cp.prepare_queue(pool, '2026-10-03')

    def test_wrong_domain_date_or_rule_and_future_duplicate_queue_are_refused(self):
        q, _ = cp.prepare_queue(self.pool, '2026-10-03', days=6)
        for fault in ['domain', 'date', 'rule', 'duplicate', 'partial']:
            bad = copy.deepcopy(q)
            if fault == 'domain': bad['slots']['2026-10-03']['items'][0] = copy.deepcopy(self.pool[0])
            elif fault == 'date': bad['slots']['2026-10-03']['recommendationDate'] = '2026-10-04'
            elif fault == 'rule': bad['selectionRuleVersion'] = 'unsupported'
            elif fault == 'duplicate': bad['slots']['2026-10-08']['items'] = copy.deepcopy(bad['slots']['2026-10-03']['items'])
            else: bad['slots']['2026-10-03']['items'].pop()
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                cp.validate_queue(bad, self.pool)

    def test_compiled_paper_body_drift_is_rejected_against_frozen_pool(self):
        q, _ = cp.prepare_queue(self.pool, '2026-10-03', days=1)
        q['slots']['2026-10-03']['items'][0]['guide']['method'] = '伪' * 100
        with self.assertRaises(ValueError): cp.validate_queue(q, self.pool)

    def test_invalid_horizon_or_nested_input_returns_value_error(self):
        for kwargs in [dict(days=0), dict(days=True), dict(days='15'), dict(existing_queue=[]), dict(archive=[] )]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                cp.prepare_queue(self.pool, '2026-10-03', **kwargs)

    def test_preparation_copies_bodies_without_mutating_or_aliasing_inputs(self):
        before = copy.deepcopy(self.pool)
        q, _ = cp.prepare_queue(self.pool, '2026-10-03')
        q['slots']['2026-10-03']['items'][0]['guide']['method'] = 'changed queue object'
        self.assertEqual(self.pool, before)

    def test_strict_json_refuses_duplicate_keys_nonfinite_and_surrogates(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'bad.json'
            for raw in ['{"slots":{},"slots":{}}', '{"x":NaN}', '{"x":"\\ud800"}']:
                p.write_text(raw)
                with self.subTest(raw=raw), self.assertRaises(ValueError): cp.read_json(p)

    def test_loader_uses_thirty_actual_frozen_guides_and_complete_bibliographies(self):
        pool = cp.load_ready_pool(ROOT, date(2026, 10, 3))
        self.assertEqual(len(pool), 30)
        self.assertEqual(dict(Counter(p['primaryDomain'] for p in pool)), {d: 6 for d in FIELDS})
        self.assertTrue(all(p['authors'] and p['overview'] and p['guide']['method'] for p in pool))
        self.assertEqual(len({p['id'] for p in pool}), 30)

    def test_gate_valid_catalog_semantic_or_byte_drift_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            shutil.copytree(ROOT / 'research', project / 'research')
            shutil.copytree(ROOT / 'docs/audits/2026-10-02-classic-guides',
                            project / 'docs/audits/2026-10-02-classic-guides')
            path = project / 'research/classics/AI.json'
            original = path.read_bytes()
            data = json.loads(original)
            data['papers'][2]['classicRationale'] = 'This is a gate-valid but unreviewed replacement claim.'
            for altered in (json.dumps(data, ensure_ascii=False).encode(), original + b'\n'):
                with self.subTest(semantic=altered != original + b'\n'):
                    path.write_bytes(altered)
                    report = cp.audit_directory(project / 'research/classics', as_of=date(2026, 10, 1),
                                                evidence_root=project / 'research/classics', require_complete=True)
                    self.assertTrue(report['ok'], 'test must isolate accepted-byte binding, not structural gate')
                    with self.assertRaisesRegex(ValueError, 'frozen catalog'):
                        cp.load_ready_pool(project, date(2026, 10, 3))

    def test_nested_nonstring_source_tags_return_validation_errors(self):
        for area, field in [('classicEvidence', 'kind'), ('sourceLocators', 'classification')]:
            pool = copy.deepcopy(self.pool)
            pool[0][area][0][field] = []
            try:
                cp.prepare_queue(pool, '2026-10-03')
            except Exception as exc:
                self.assertIsInstance(exc, ValueError, 'Malformed tags must not leak TypeError')
            else:
                self.fail('Malformed tag accepted')

    def test_malformed_review_seal_returns_validation_error_before_compilation(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            shutil.copytree(ROOT / 'research/classics', project / 'research/classics')
            shutil.copytree(ROOT / 'research/classic-guides', project / 'research/classic-guides')
            shutil.copytree(ROOT / 'research/classic-publishing', project / 'research/classic-publishing')
            folder = project / 'docs/audits/2026-10-02-classic-guides'
            folder.mkdir(parents=True)
            (folder / 'sealed-inputs.json').write_text('{"fieldInputs":[]}')
            try:
                cp.load_ready_pool(project, date(2026, 10, 3))
            except Exception as exc:
                self.assertIsInstance(exc, ValueError, 'Malformed review seal must not leak indexing exceptions')
            else:
                self.fail('Malformed review seal accepted')


if __name__ == '__main__':
    unittest.main()
