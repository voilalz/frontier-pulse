import importlib.util
import sys
import unittest
from email.message import Message
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("check_production", ROOT / "scripts" / "check_production.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ProductionSmokeTests(unittest.TestCase):
    def test_cache_header_accepts_one_expected_directive(self):
        headers = Message()
        headers["Cache-Control"] = "public, max-age=300, must-revalidate"
        self.assertTrue(MODULE.cache_header_is_unambiguous(headers, 300))

    def test_cache_header_rejects_overlapping_rules(self):
        headers = Message()
        headers["Cache-Control"] = "public, max-age=3600, must-revalidate"
        headers["Cache-Control"] = "public, max-age=300, must-revalidate"
        self.assertFalse(MODULE.cache_header_is_unambiguous(headers, 300))


if __name__ == "__main__":
    unittest.main()
