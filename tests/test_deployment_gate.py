"""Only trusted, successful main publications may trigger production deployment."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from deployment_gate import allowed

REPO = 'voilalz/frontier-pulse'


class DeploymentGateTests(unittest.TestCase):
    def event(self, name='Daily classic papers'):
        return {'workflow_run': {'name': name, 'conclusion': 'success', 'head_branch': 'main',
                                 'head_repository': {'full_name': REPO}}}

    def test_successful_trusted_main_publications(self):
        for name in ('Daily classic papers', 'Daily news update', 'Full stream update', 'Restore retained release'):
            self.assertTrue(allowed('workflow_run', self.event(name), REPO, 'refs/heads/main'))

    def test_failed_foreign_and_untrusted_events_are_refused(self):
        base = self.event()
        for change in ({'conclusion': 'failure'}, {'head_branch': 'feature'},
                       {'name': 'Untrusted build'}, {'head_repository': {'full_name': 'other/fork'}}):
            candidate = copy.deepcopy(base)
            candidate['workflow_run'].update(change)
            self.assertFalse(allowed('workflow_run', candidate, REPO, 'refs/heads/main'))
        self.assertFalse(allowed('workflow_run', {}, REPO, 'refs/heads/main'))

    def test_main_push_and_manual_dispatch_only(self):
        for event in ('push', 'workflow_dispatch'):
            self.assertTrue(allowed(event, {}, REPO, 'refs/heads/main'))
            self.assertFalse(allowed(event, {}, REPO, 'refs/heads/feature'))
        self.assertFalse(allowed('pull_request', {}, REPO, 'refs/heads/main'))
