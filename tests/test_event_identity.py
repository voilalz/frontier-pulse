import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("event_identity", ROOT / "scripts" / "event_identity.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def story(news_id, title, published="2026-09-21T10:00:00Z", **extra):
    return {"id": news_id, "originalTitle": title, "publishedAt": published, **extra}


def registry_for(*items):
    by_event = {}
    for item in items:
        record = by_event.setdefault(item["eventId"], {
            "eventId": item["eventId"], "newsIds": [], "identityRepresentatives": [],
        })
        record["newsIds"].append(item["id"])
        record["identityRepresentatives"].append(MODULE.event_identity_record(item))
    return {"items": list(by_event.values())}


class SameEventTests(unittest.TestCase):
    def test_hand_labeled_headline_pairs(self):
        # Labels describe discrete incidents/products, not topical similarity.
        cases = [
            ("same lawsuit",
             "Blue Water Autonomy, Saildrone launch lawsuits against Navy over MUSV Marketplace",
             "2 defense tech companies sue US Navy after losing out on MUSV program", True),
            ("same mission paraphrase",
             "NASA launches Europa Clipper mission aboard SpaceX Falcon 9",
             "Europa Clipper lifts off on its journey to Jupiter", True),
            ("same attack, changing casualty count",
             "Russian drone attack kills three at Kyiv hospital",
             "Russia drone strike on Kyiv hospital leaves seven dead", True),
            ("different Starship flight numbers",
             "SpaceX launches Starship flight 11 from Texas",
             "SpaceX launches Starship flight 12 from Texas", False),
            ("different mission Roman numerals",
             "NASA launches Artemis II mission",
             "NASA launches Artemis III mission", False),
            ("different products",
             "OpenAI releases GPT-5 model for developers",
             "OpenAI releases GPT-6 model for developers", False),
            ("different numbered payloads",
             "SpaceX launches Starlink 8-3 satellites aboard Falcon 9",
             "SpaceX launches Starlink 8-4 satellites aboard Falcon 9", False),
            ("different unnumbered payloads",
             "SpaceX launches Starlink satellites aboard Falcon 9 from Florida",
             "SpaceX launches SiriusXM satellite aboard Falcon 9 from Florida", False),
            ("different cities",
             "Russian drone attack kills three in Kyiv, Ukraine",
             "Russian drone attack kills three in Kharkiv, Ukraine", False),
            ("different countries despite generic wording",
             "Drone attack damages power station in Moscow",
             "Drone attack damages power station in Kyiv", False),
            ("same actor, different action",
             "OpenAI releases GPT-5 model for developers",
             "OpenAI withdraws GPT-5 model for developers", False),
            ("broad topic only",
             "Navy expands drone fleet after budget vote",
             "Navy studies drone fleet maintenance costs", False),
            ("generic title supplies no discrete event evidence",
             "Officials report new developments in artificial intelligence",
             "Officials report new developments in artificial intelligence", False),
            ("another attack is a new incident",
             "Russian drone attack hits Kyiv hospital",
             "Another Russian drone attack hits Kyiv hospital", False),
            ("different unfamiliar actors",
             "Astera Robotics releases Scout-2 warehouse robot",
             "Vectra Robotics releases Scout-2 warehouse robot", False),
            ("different unfamiliar locations",
             "Russian missile attack hits energy hub in Riverton",
             "Russian missile attack hits energy hub in Lakeside", False),
            ("different unfamiliar mission numbers",
             "Nova launches Pathfinder 3 lunar probe",
             "Nova launches Pathfinder 4 lunar probe", False),
            ("same carrier, different unfamiliar payloads",
             "SpaceX launches EchoStar satellite aboard Falcon 9",
             "SpaceX launches Eutelsat satellite aboard Falcon 9", False),
            ("a delayed launch is not a completed launch",
             "NASA launches Artemis II mission",
             "NASA delays Artemis II mission launch", False),
            ("a planned launch is not a completed launch",
             "NASA launches Artemis II mission",
             "NASA plans to launch Artemis II mission", False),
            ("different acquired companies",
             "OpenAI acquires Acme to expand coding platform",
             "OpenAI acquires Beta to expand coding platform", False),
            ("different regional releases",
             "Google releases Gemini chatbot in Brazil",
             "Google releases Gemini chatbot in Japan", False),
            ("attack direction cannot be reversed",
             "Israel launches missile attack on Iran nuclear sites",
             "Iran launches missile attack on Israel nuclear sites", False),
        ]
        for label, first, second, expected in cases:
            with self.subTest(label=label):
                a, b = story("a", first), story("b", second)
                self.assertEqual(MODULE.same_event(a, b), expected)
                self.assertEqual(MODULE.same_event(b, a), expected)

    def test_same_named_new_center_from_two_publishers_is_one_event(self):
        first = story("a", "US Navy stands up hub to prepare unmanned systems for combat",
                      "2026-09-25T18:13:48Z",
                      summary="US Navy establishes Robotic and Autonomous Systems Warfighting Development Center (RASWDC) to train sailors.")
        second = story("b", "U.S. Navy Establishes RASWDC To Accelerate Unmanned Systems Integration",
                       "2026-09-25T18:28:22Z",
                       summary="U.S. Navy officially established the Robotic and Autonomous Systems Warfighting Development Center (RASWDC).")
        self.assertTrue(MODULE.same_event(first, second))
        self.assertTrue(MODULE.same_event(second, first))
        unrelated = story("c", "US Navy stands up hub to prepare other unmanned systems for combat",
                          "2026-09-25T19:00:00Z", summary="US Navy establishes a separate logistics center (LDCOM).")
        self.assertFalse(MODULE.same_event(unrelated, second))
        renamed_action = story("d", "U.S. Navy closes RASWDC following review",
                               "2026-09-25T19:00:00Z", summary=second["summary"])
        self.assertFalse(MODULE.same_event(first, renamed_action))

    def test_same_immutable_article_wins_over_changed_title_and_date(self):
        first = story("article-1", "Initial report", "2026-09-01T10:00:00Z")
        second = story("article-1", "Corrected report", "2026-09-21T10:00:00Z")
        self.assertTrue(MODULE.same_event(first, second))

    def test_canonical_article_urls_match_through_source_lists(self):
        first = story("a", "Initial report", url="https://EXAMPLE.org/report?story=42&utm_source=rss#top")
        second = story("b", "Updated report", sources=[{"url": "https://example.org/report?story=42"}])
        self.assertTrue(MODULE.same_event(first, second))
        second["sources"][0]["url"] = "https://example.org/report?story=43"
        self.assertFalse(MODULE.same_event(first, second))

    def test_common_homepage_is_not_an_article_identity(self):
        self.assertFalse(MODULE.same_event(
            story("a", "Initial report", url="https://example.org/"),
            story("b", "Unrelated report", url="https://example.org/"),
        ))

    def test_distant_repeated_attack_does_not_match_identical_title(self):
        title = "Russian drone attack hits Kyiv hospital"
        self.assertFalse(MODULE.same_event(
            story("a", title, "2026-09-01T10:00:00Z"),
            story("b", title, "2026-09-21T10:00:00Z"),
        ))

    def test_next_day_repeated_attack_requires_explicit_followup(self):
        title = "Russian drone attack hits Kyiv hospital"
        self.assertFalse(MODULE.same_event(
            story("a", title, "2026-09-20T10:00:00Z"),
            story("b", title, "2026-09-21T09:00:00Z"),
        ))

    def test_explicit_cross_day_toll_update_keeps_incident_identity(self):
        self.assertTrue(MODULE.same_event(
            story("a", "Russian drone attack kills three at Kyiv hospital", "2026-09-20T10:00:00Z"),
            story("b", "Death toll rises to seven after Russia's Kyiv hospital drone attack", "2026-09-21T09:00:00Z"),
        ))

    def test_conflicting_explicit_incident_dates_override_same_publication_date(self):
        self.assertFalse(MODULE.same_event(
            story("a", "Death toll rises after Monday's Russian drone attack on Kyiv hospital", "2026-09-23T10:00:00Z"),
            story("b", "Death toll rises after Tuesday's Russian drone attack on Kyiv hospital", "2026-09-23T10:00:00Z"),
        ))

    def test_numbered_flight_failure_followup_can_match_its_launch(self):
        self.assertTrue(MODULE.same_event(
            story("a", "SpaceX launches Starship flight 11 from Texas", "2026-09-19T10:00:00Z"),
            story("b", "Investigation into SpaceX Starship flight 11 failure continues", "2026-09-21T09:00:00Z"),
        ))

    def test_named_mission_health_followup_keeps_launch_identity(self):
        self.assertTrue(MODULE.same_event(
            story("a", "NASA launches Europa Clipper spacecraft to Jupiter", "2026-09-20T12:00:00Z"),
            story("b", "NASA confirms Europa Clipper spacecraft healthy after Jupiter launch", "2026-09-21T07:00:00Z"),
        ))

    def test_explicit_calendar_dates_distinguish_incidents(self):
        self.assertFalse(MODULE.same_event(
            story("a", "Death toll rises after September 19 Russian drone attack on Kyiv hospital"),
            story("b", "Death toll rises after September 20 Russian drone attack on Kyiv hospital"),
        ))

    def test_missing_or_invalid_dates_do_not_enable_semantic_matching(self):
        title = "NASA launches Europa Clipper mission"
        for timestamp in ("", "not-a-date"):
            with self.subTest(timestamp=timestamp):
                self.assertFalse(MODULE.same_event(story("a", title, timestamp), story("b", title, timestamp)))

    def test_edition_date_supplies_time_evidence_when_publication_is_absent(self):
        first = story("a", "NASA launches Europa Clipper mission", "", editionDate="2026-09-21")
        second = story("b", "Europa Clipper lifts off on Jupiter mission", "", editionDate="2026-09-21")
        self.assertTrue(MODULE.same_event(first, second))


class StableIdentityTests(unittest.TestCase):
    def test_batch_members_share_identity_independent_of_input_order(self):
        originals = [
            story("z-wire", "Russian drone attack kills three at Kyiv hospital"),
            story("a-report", "Russia drone strike on Kyiv hospital leaves seven dead"),
            story("m-other", "Russian drone attack kills three at Kharkiv hospital"),
        ]
        first, second = copy.deepcopy(originals), copy.deepcopy(list(reversed(originals)))
        MODULE.assign_event_ids(first, {}, {})
        MODULE.assign_event_ids(second, {}, {})
        ids = {item["id"]: item["eventId"] for item in first}
        self.assertEqual(ids, {item["id"]: item["eventId"] for item in second})
        self.assertEqual(ids["z-wire"], ids["a-report"])
        self.assertNotEqual(ids["z-wire"], ids["m-other"])
        self.assertTrue(all(item["eventIdentity"]["decision"] for item in first))
        self.assertTrue(all(item["eventIdentity"]["version"] for item in first))
        for event_id in ids.values():
            self.assertRegex(event_id, r"^evt-[0-9a-f]{12}$")

    def test_cross_run_followup_reuses_persisted_representative(self):
        initial = story("original", "Russian drone attack kills three at Kyiv hospital", "2026-09-20T10:00:00Z")
        MODULE.assign_event_ids([initial], {}, {})
        registry = json.loads(json.dumps(registry_for(initial)))
        followup = story("new-url", "Death toll rises after Russia's Kyiv hospital drone attack", "2026-09-21T09:00:00Z")
        MODULE.assign_event_ids([followup], registry, {})
        self.assertEqual(followup["eventId"], initial["eventId"])
        self.assertEqual(followup["eventIdentity"]["decision"], "registry-match")

    def test_exact_registry_membership_preserves_legacy_identity(self):
        item = story("archive-id", "Edited title")
        registry = {"items": [{"eventId": "evt-0123456789ab", "newsIds": ["archive-id"]}]}
        MODULE.assign_event_ids([item], registry, {})
        self.assertEqual(item["eventId"], "evt-0123456789ab")

    def test_legacy_group_cannot_propagate_to_new_topic_members(self):
        legacy = {"items": [{
            "eventId": "evt-0123456789ab", "newsIds": ["old-flight", "old-attack"],
            "title": "SpaceX launches Starship flight 11 from Texas",
            "timeline": [{"newsId": "old-flight", "title": "SpaceX launches Starship flight 11 from Texas", "publishedAt": "2026-09-21T10:00:00Z"}],
        }]}
        original = story("old-flight", "SpaceX launches Starship flight 11 from Texas")
        incoming = story("new-flight-report", "SpaceX launches Starship flight 11 from Texas")
        incoming["historyContext"] = {"relatedStories": [{
            "id": "old-flight", "eventId": "evt-0123456789ab", "associationScore": 100,
            "relationLabel": "同一事件后续",
        }]}
        MODULE.assign_event_ids([incoming, original], legacy, {})
        self.assertEqual(original["eventId"], "evt-0123456789ab")
        self.assertNotEqual(incoming["eventId"], original["eventId"])
        # Saving an exact legacy representative must not silently make its topic group reusable.
        migrated = registry_for(original)
        next_report = story("another-new-report", incoming["originalTitle"])
        MODULE.assign_event_ids([next_report], migrated, {})
        self.assertNotEqual(next_report["eventId"], original["eventId"])

    def test_history_scores_never_supply_missing_identity_evidence(self):
        item = {"id": "new", "historyContext": {"relatedStories": [{
            "id": "old", "eventId": "evt-0123456789ab", "associationScore": 100,
            "relationLabel": "同一事件后续",
        }]}}
        MODULE.assign_event_ids([item], {"items": [{"eventId": "evt-0123456789ab", "newsIds": ["old"]}]}, {})
        self.assertNotEqual(item["eventId"], "evt-0123456789ab")

    def test_corroborating_article_url_survives_registry_round_trip(self):
        initial = story("first", "Initial headline", sources=[{"url": "https://wire.example/story"}])
        MODULE.assign_event_ids([initial], {}, {})
        followup = story("second", "Changed headline", "2026-09-25T10:00:00Z", url="https://wire.example/story?utm_source=feed")
        MODULE.assign_event_ids([followup], registry_for(initial), {})
        self.assertEqual(followup["eventId"], initial["eventId"])

    def test_conflicting_registry_identities_do_not_force_an_ambiguous_merge(self):
        first = story("first", "NASA launches Europa Clipper mission")
        second = story("second", "Europa Clipper lifts off on its journey to Jupiter")
        MODULE.assign_event_ids([first], {}, {})
        MODULE.assign_event_ids([second], {}, {})
        self.assertNotEqual(first["eventId"], second["eventId"])
        incoming = story("third", "NASA launches Europa Clipper toward Jupiter")
        MODULE.assign_event_ids([incoming], registry_for(first, second), {})
        self.assertNotIn(incoming["eventId"], {first["eventId"], second["eventId"]})
        self.assertIn("ambiguous", incoming["eventIdentity"]["decision"])

    def test_strong_named_center_evidence_reconciles_two_exact_registry_ids(self):
        a = story("a", "US Navy stands up hub to prepare unmanned systems for combat",
                  "2026-09-25T18:13:48Z", summary="The Navy establishes RASWDC for unmanned systems.")
        b = story("b", "U.S. Navy Establishes RASWDC To Accelerate Unmanned Systems Integration",
                  "2026-09-25T18:28:22Z", summary="The U.S. Navy establishes RASWDC for integration.")
        MODULE.assign_event_ids([a], {}, {})
        MODULE.assign_event_ids([b], {}, {})
        self.assertNotEqual(a["eventId"], b["eventId"])
        registry = registry_for(a, b)
        current = [copy.deepcopy(a), copy.deepcopy(b)]
        MODULE.assign_event_ids(current, registry, {})
        canonical = min(a["eventId"], b["eventId"])
        self.assertEqual({item["eventId"] for item in current}, {canonical})
        self.assertEqual(MODULE.reconcile_registry_ids(registry),
                         {max(a["eventId"], b["eventId"]): canonical})
        self.assertEqual(registry, registry_for(a, b))

    def test_registry_and_source_items_are_not_mutated_when_matching(self):
        initial = story("original", "NASA launches Europa Clipper mission")
        MODULE.assign_event_ids([initial], {}, {})
        registry = registry_for(initial)
        before = copy.deepcopy(registry)
        current = story("next", "Europa Clipper lifts off toward Jupiter")
        MODULE.assign_event_ids([current], registry, {})
        self.assertEqual(registry, before)
        self.assertNotIn("eventIdentity", registry["items"][0]["identityRepresentatives"][0])

    def test_batch_bridge_cannot_merge_conflicting_numbered_flights(self):
        originals = [
            story("a", "SpaceX launches Starship flight 11 from Texas"),
            story("b", "SpaceX launches Starship from Texas"),
            story("c", "SpaceX launches Starship flight 12 from Texas"),
        ]
        first, second = copy.deepcopy(originals), copy.deepcopy(list(reversed(originals)))
        MODULE.assign_event_ids(first, {}, {})
        MODULE.assign_event_ids(second, {}, {})
        self.assertEqual(len({item["eventId"] for item in first}), 3)
        self.assertEqual({item["id"]: item["eventId"] for item in first},
                         {item["id"]: item["eventId"] for item in second})
        self.assertIn("ambiguous", first[1]["eventIdentity"]["decision"])

    def test_missing_article_identity_cannot_create_a_shared_fallback_id(self):
        items = [{"title": "Officials report new developments"},
                 {"title": "Officials report new developments"}]
        MODULE.assign_event_ids(items, {}, {})
        self.assertNotEqual(items[0]["eventId"], items[1]["eventId"])

    def test_representatives_are_bounded_and_json_serializable(self):
        initial = story("original", "NASA launches Europa Clipper mission", summary="evidence " * 2000,
                        sources=[{"url": f"https://source.example/articles/{index}"} for index in range(50)])
        MODULE.assign_event_ids([initial], {}, {})
        record = MODULE.event_identity_record(initial)
        self.assertLess(len(json.dumps(record)), 6000)
        self.assertLessEqual(len(record["urls"]), 12)
        self.assertEqual(record["id"], "original")
        self.assertEqual(record["eventId"], initial["eventId"])


if __name__ == "__main__":
    unittest.main()
