"""Title-grounded evidence must not import a neighbouring story's facts."""
import json
import unittest

from scripts.news_evidence import select_relevant_evidence


class NewsEvidenceTests(unittest.TestCase):
    def test_matching_short_article_beats_long_unrelated_article(self):
        mission = "NASA launched Europa Clipper on Monday to investigate Jupiter's icy moon."
        page = (
            '<article><h1>War closes a football stadium</h1><p>'
            + "The football stadium was damaged as fighting intensified along the border. " * 80
            + '</p></article><article><h1>NASA launches Europa Clipper</h1>'
            + f'<div class="article-body"><p>{mission}</p></div></article>'
        )
        result = select_relevant_evidence("NASA launches Europa Clipper", "", page)
        self.assertEqual(result["status"], "body")
        self.assertEqual(result["paragraphs"], [mission])
        self.assertNotIn("football", result["text"])

    def test_json_ld_articles_are_ranked_by_headline_instead_of_length(self):
        mission = "Europa Clipper separated from its rocket after NASA confirmed a successful launch."
        data = {"@graph": [
            {"@type": "NewsArticle", "headline": "Football club changes manager",
             "articleBody": "The football club appointed a manager after a difficult season. " * 100},
            {"@type": ["NewsArticle", "Article"], "headline": "NASA launches Europa Clipper",
             "articleBody": mission},
        ]}
        page = f'<script type="application/ld+json">{json.dumps(data)}</script>'
        result = select_relevant_evidence("NASA launches Europa Clipper", "", page)
        self.assertEqual(result["text"], mission)
        self.assertEqual(result["status"], "body")

    def test_conflicting_structured_headline_rejects_incidental_matching_body(self):
        data = {"@type": "NewsArticle", "headline": "Local football stadium reopens",
                "articleBody": "NASA launched Europa Clipper on Monday. " * 100}
        page = f'<script type="application/ld+json">{json.dumps(data)}</script>'
        result = select_relevant_evidence("NASA launches Europa Clipper", "", page)
        self.assertEqual(result["status"], "title-only")
        self.assertEqual(result["text"], "")

    def test_unrelated_paragraphs_are_removed_and_evidence_stays_in_source_order(self):
        first = "Europa Clipper launched from Florida after its final preflight checks."
        second = "NASA's Europa Clipper will investigate whether Jupiter's moon can support life."
        page = (f'<article><h1>NASA launches Europa Clipper</h1><p>{first}</p>'
                '<p>City councillors voted to extend the football stadium lease.</p>'
                f'<p>{second}</p></article>')
        result = select_relevant_evidence("NASA launches Europa Clipper", "", page)
        self.assertEqual(result["paragraphs"], [first, second])
        self.assertEqual(result["selectedCount"], 2)
        self.assertGreaterEqual(result["candidateCount"], 3)

    def test_adjacent_mission_details_remain_supported_context(self):
        first = "NASA's Europa Clipper spacecraft launched on Monday."
        detail = "The spacecraft carries nine scientific instruments to study the icy moon."
        page = f'<article><h1>NASA launches Europa Clipper</h1><p>{first}</p><p>{detail}</p></article>'
        result = select_relevant_evidence("NASA launches Europa Clipper", "", page)
        self.assertEqual(result["paragraphs"], [first, detail])

    def test_sidebar_navigation_and_subscription_promotions_are_not_evidence(self):
        mission = "NASA's Europa Clipper spacecraft launched on Monday."
        page = (
            '<nav><p>NASA Europa Clipper mission hub</p></nav>'
            '<article><h1>NASA launches Europa Clipper</h1>'
            '<aside><p>NASA Europa Clipper: ten facts from our archive.</p></aside>'
            '<div class="related-stories"><p>Europa Clipper viewing guide.</p></div>'
            '<div class="newsletter"><p>Subscribe for NASA Europa Clipper updates.</p></div>'
            '<p>Read more: NASA Europa Clipper photo gallery.</p>'
            f'<p>{mission}</p><footer><p>NASA Europa Clipper copyright notice.</p></footer></article>'
        )
        self.assertEqual(select_relevant_evidence("NASA launches Europa Clipper", "", page)["paragraphs"], [mission])

    def test_unrelated_feed_lead_cannot_poison_a_matching_body(self):
        mission = "NASA launched Europa Clipper toward Jupiter on Monday."
        page = f'<article><h1>NASA launches Europa Clipper</h1><p>{mission}</p></article>'
        result = select_relevant_evidence("NASA launches Europa Clipper", "The football cup final ended in a draw.", page)
        self.assertEqual(result["text"], mission)
        self.assertEqual(result["status"], "body")

    def test_relevant_feed_is_used_when_page_is_unrelated(self):
        lead = "NASA's Europa Clipper lifted off on Monday aboard a Falcon Heavy rocket."
        page = '<article><h1>City holds football final</h1><p>The match ended in a draw.</p></article>'
        result = select_relevant_evidence("NASA launches Europa Clipper", lead, page)
        self.assertEqual(result["text"], lead)
        self.assertEqual(result["status"], "feed")

    def test_short_relevant_lead_is_not_discarded_for_its_length(self):
        lead = "Europa Clipper lifts off."
        result = select_relevant_evidence("NASA launches Europa Clipper", lead, "")
        self.assertEqual(result["paragraphs"], [lead])
        self.assertEqual(result["status"], "feed")

    def test_plain_paragraphs_can_supply_evidence_without_article_markup(self):
        mission = "NASA's Europa Clipper lifted off from Florida on Monday."
        page = f'<h1>NASA launches Europa Clipper</h1><div><p>{mission}</p></div>'
        result = select_relevant_evidence("NASA launches Europa Clipper", "", page)
        self.assertEqual(result["text"], mission)
        self.assertEqual(result["status"], "body")

    def test_matching_html_is_not_overridden_by_unrelated_structured_data(self):
        mission = "NASA's Europa Clipper spacecraft launched on Monday."
        data = {"@type": "NewsArticle", "headline": "NASA names a new administrator",
                "articleBody": "NASA confirmed the administrator will start work next month. " * 90}
        page = (f'<script type="application/ld+json">{json.dumps(data)}</script>'
                f'<article><h1>NASA launches Europa Clipper</h1><p>{mission}</p></article>')
        self.assertEqual(select_relevant_evidence("NASA launches Europa Clipper", "", page)["text"], mission)

    def test_unrelated_sentences_in_json_ld_body_are_filtered(self):
        mission = "NASA launched Europa Clipper toward Jupiter on Monday."
        data = {"@type": "NewsArticle", "headline": "NASA launches Europa Clipper",
                "articleBody": "A football club changed managers. " + mission + " The city council raised parking fees."}
        page = f'<script type="application/ld+json">{json.dumps(data)}</script>'
        self.assertEqual(select_relevant_evidence("NASA launches Europa Clipper", "", page)["text"], mission)

    def test_long_feed_content_is_filtered_even_without_a_page(self):
        lead = (
            "The city council approved a new football stadium. "
            "NASA launched Europa Clipper toward Jupiter on Monday. "
            "The Europa Clipper mission will study the moon's icy shell. "
            "The local football club signed two players."
        )
        result = select_relevant_evidence("NASA launches Europa Clipper", lead, "")
        self.assertEqual(result["status"], "feed")
        self.assertIn("icy shell", result["text"])
        self.assertNotIn("football", result["text"])

    def test_html_feed_preserves_relevant_paragraph_boundaries(self):
        first = "NASA launched Europa Clipper toward Jupiter on Monday."
        second = "Europa Clipper will carry out repeated flybys of the icy moon."
        lead = f'<p>See our football coverage.</p><p>{first}</p><p>{second}</p>'
        result = select_relevant_evidence("NASA launches Europa Clipper", lead, "")
        self.assertEqual(result["paragraphs"], [first, second])

    def test_no_relevant_evidence_returns_empty_text_instead_of_repeating_title(self):
        result = select_relevant_evidence("NASA launches Europa Clipper", "The football match ended in a draw.", "")
        self.assertEqual(result["status"], "title-only")
        self.assertEqual(result["text"], "")
        self.assertEqual(result["paragraphs"], [])
        self.assertEqual(result["selectedCount"], 0)
        self.assertTrue(result["reason"])

    def test_generic_shared_news_words_do_not_admit_an_unrelated_body(self):
        title = "New autonomous submarine completes first trial"
        page = ('<main><p>A new national economic policy completes its first year with a trial '
                'programme to support local businesses and government officials.</p></main>')
        self.assertEqual(select_relevant_evidence(title, "", page)["status"], "title-only")

    def test_short_generic_acronym_is_not_enough_to_ground_an_article(self):
        page = '<article><p>The football league uses AI to schedule advertising around matches.</p></article>'
        self.assertEqual(select_relevant_evidence("AI", "", page)["text"], "")

    def test_acronyms_match_whole_words_without_matching_word_fragments(self):
        title = "ESA launches Hera asteroid mission"
        unrelated = "The senator said the local theatre raised ticket prices for the festival."
        result = select_relevant_evidence(title, unrelated, "")
        self.assertEqual(result["status"], "title-only")

    def test_hyphenated_model_names_match_but_different_versions_do_not(self):
        lead = "OpenAI released GPT‑5 with updated reasoning capabilities."
        good = select_relevant_evidence("OpenAI releases GPT-5", lead, "")
        bad = select_relevant_evidence("OpenAI releases GPT-5", "OpenAI released GPT-4 with updated reasoning capabilities.", "")
        self.assertEqual(good["text"], lead)
        self.assertEqual(bad["text"], "")

    def test_matching_headline_does_not_admit_a_conflicting_model_paragraph(self):
        evidence = "OpenAI released GPT-5 with improved reasoning capabilities."
        page = ('<article><h1>OpenAI releases GPT-5</h1>'
                f'<p>{evidence}</p><p>OpenAI GPT-4 has different benchmark results.</p></article>')
        result = select_relevant_evidence("OpenAI releases GPT-5", "", page)
        self.assertEqual(result["paragraphs"], [evidence])

    def test_matching_entities_do_not_override_a_conflicting_headline_state(self):
        cases = [
            ("OpenAI releases GPT-5 model", "OpenAI withdraws GPT-5 model",
             "OpenAI has withdrawn GPT-5 from all available services following safety failures."),
            ("NASA launches Artemis II", "NASA delays Artemis II launch",
             "NASA has delayed the Artemis II launch until next year."),
        ]
        for title, headline, body in cases:
            for structured in (False, True):
                with self.subTest(title=title, structured=structured):
                    if structured:
                        data = {"@type": "NewsArticle", "headline": headline, "articleBody": body}
                        page = f'<script type="application/ld+json">{json.dumps(data)}</script>'
                    else:
                        page = f'<article><h1>{headline}</h1><p>{body}</p></article>'
                    result = select_relevant_evidence(title, "", page)
                    self.assertEqual(result["status"], "title-only")
                    self.assertEqual(result["text"], "")

    def test_matching_launch_headline_preserves_historical_delay_context(self):
        history = "NASA delayed the Artemis II launch last year to complete additional checks."
        launched = "NASA launched Artemis II on Monday after completing the checks."
        page = (f'<article><h1>NASA launches Artemis II after delays</h1>'
                f'<p>{launched}</p><p>{history}</p></article>')
        result = select_relevant_evidence("NASA launches Artemis II", "", page)
        self.assertEqual(result["paragraphs"], [launched, history])

    def test_short_feed_with_shared_subject_and_action_can_omit_publisher_entity(self):
        lead = "A satellite launch is scheduled for Monday."
        result = select_relevant_evidence("ESA satellite launch", lead, "")
        self.assertEqual(result["status"], "feed")
        self.assertEqual(result["text"], lead)

    def test_short_feed_can_ground_an_unfamiliar_product_with_shared_action(self):
        lead = "Asteria has been released with support for image input."
        result = select_relevant_evidence("Acme releases Asteria model", lead, "")
        self.assertEqual(result["status"], "feed")
        self.assertEqual(result["text"], lead)

    def test_single_generic_subject_and_action_does_not_select_a_body(self):
        page = ('<article><p>A satellite launch is scheduled for Monday.</p></article>'
                '<article><p>A satellite launch is scheduled for Friday.</p></article>')
        self.assertEqual(select_relevant_evidence("ESA satellite launch", "", page)["text"], "")

    def test_short_feed_subject_fallback_does_not_substitute_a_different_agency(self):
        result = select_relevant_evidence("ESA satellite launch", "NASA satellite launch is scheduled for Monday.", "")
        self.assertEqual(result["text"], "")

    def test_adjacent_context_does_not_extend_through_an_unrelated_story(self):
        mission = "NASA's Europa Clipper spacecraft launched on Monday."
        page = (f'<article><h1>NASA launches Europa Clipper</h1><p>{mission}</p>'
                '<p>The local football stadium reopened on Monday.</p>'
                '<p>The spacecraft featured in a football advertising campaign.</p></article>')
        result = select_relevant_evidence("NASA launches Europa Clipper", "", page)
        self.assertEqual(result["paragraphs"], [mission])

    def test_cjk_entities_match_without_whitespace(self):
        mission = "欧洲航天局的赫拉探测器已升空，将考察小行星撞击试验的结果。"
        page = (f'<article><h1>欧洲航天局发射赫拉探测器</h1><p>{mission}</p>'
                '<p>欧洲足球俱乐部在决赛中获胜，球迷走上街头庆祝。</p></article>')
        result = select_relevant_evidence("欧洲航天局发射赫拉探测器", "", page)
        self.assertEqual(result["paragraphs"], [mission])

    def test_conflicting_page_headline_rejects_unlabelled_body(self):
        page = ('<h1>Football club appoints a new manager</h1><div class="article-body">'
                '<p>NASA launched Europa Clipper toward Jupiter on Monday.</p></div>')
        self.assertEqual(select_relevant_evidence("NASA launches Europa Clipper", "", page)["text"], "")

    def test_explicit_structured_paywall_uses_only_public_feed_evidence(self):
        data = {"@type": "NewsArticle", "headline": "NASA launches Europa Clipper",
                "isAccessibleForFree": False,
                "articleBody": "NASA's Europa Clipper carries nine instruments with restricted test data."}
        page = f'<script type="application/ld+json">{json.dumps(data)}</script>'
        lead = "NASA launched Europa Clipper on Monday."
        result = select_relevant_evidence("NASA launches Europa Clipper", lead, page)
        self.assertEqual(result["text"], lead)
        self.assertEqual(result["status"], "feed")
        self.assertNotIn("restricted test data", result["text"])

    def test_explicit_html_paywall_never_exposes_embedded_body(self):
        page = ('<article><h1>NASA launches Europa Clipper</h1>'
                '<div class="paywall">Sign in to read this article.</div>'
                '<p>NASA launched Europa Clipper with undisclosed instruments.</p></article>')
        result = select_relevant_evidence("NASA launches Europa Clipper", "", page)
        self.assertEqual(result["text"], "")

    def test_explicit_public_access_metadata_rejects_embedded_body(self):
        page = ('<meta itemprop="isAccessibleForFree" content="false">'
                '<article><h1>NASA launches Europa Clipper</h1>'
                '<p>NASA launched Europa Clipper with restricted test data.</p></article>')
        lead = "Europa Clipper lifted off."
        result = select_relevant_evidence("NASA launches Europa Clipper", lead, page)
        self.assertEqual(result["text"], lead)
        self.assertEqual(result["status"], "feed")

    def test_empty_and_malformed_pages_fail_closed(self):
        for title, lead, page in [("", "", ""), ("Latest news", "More details coming soon.", "<p>"),
                                  ("NASA launches Europa Clipper", "", '<script type="application/ld+json">{broken</script>')]:
            with self.subTest(title=title, page=page):
                result = select_relevant_evidence(title, lead, page)
                self.assertEqual(result["status"], "title-only")
                self.assertEqual(result["paragraphs"], [])

    def test_evidence_budget_is_bounded_and_duplicate_paragraphs_are_removed(self):
        paragraphs = [f"Europa Clipper observation {index} will measure the icy moon's surface composition and magnetic environment."
                      for index in range(150)]
        page = '<article><h1>NASA launches Europa Clipper</h1>' + ''.join(f'<p>{p}</p>' for p in paragraphs + paragraphs) + '</article>'
        result = select_relevant_evidence("NASA launches Europa Clipper", "", page)
        self.assertEqual(result["status"], "body")
        self.assertLessEqual(len(result["text"]), 6000)
        self.assertEqual(len(result["paragraphs"]), len(set(result["paragraphs"])))
        self.assertEqual(result["selectedCount"], len(result["paragraphs"]))
        self.assertEqual(result["text"], "\n\n".join(result["paragraphs"]))
        indices = [int(paragraph.split()[3]) for paragraph in result["paragraphs"]]
        self.assertEqual(indices, sorted(indices))


if __name__ == "__main__":
    unittest.main()
