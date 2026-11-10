"""Tests for the task 5.3 claim verifier.

The first five are Enock's, unchanged. Everything below the divider is a
regression test for one of the five amendments of 2026-11-10, each written
from a claim that the verifier got wrong when it was probed against the live
offline pipeline. A test here names the failure it locks down, because a bare
assertion does not tell the next reader why the line exists.
"""
import unittest

from src.task_5_3_verifier import verify_copy


def trace(result, arguments=None):
    return [{"event": "tool_call", "status": "ok",
             "tool": "stub_tool",
             "arguments": arguments or {},
             "result": {"result_id": "result_1", **result}}]


def one(claim, interpretation="", ids=("result_1",)):
    return {"evidence": [{"claim": claim,
                          "interpretation": interpretation,
                          "tool_result_ids": list(ids)}],
            "contradictory_evidence": []}


class VerifierTests(unittest.TestCase):
    def test_numeric_supported_and_percent_equivalence(self):
        out = {"evidence": [{"claim": "The adverse rate was 4.70%.",
                             "tool_result_ids": ["result_1"]}],
               "contradictory_evidence": []}
        checked, report = verify_copy(out, trace({"value": 0.0470, "fyear": 2022}))
        self.assertEqual(report["verified_items"], 1)
        self.assertEqual(len(checked["evidence"]), 1)

    def test_unsupported_number_blocked(self):
        out = {"evidence": [{"claim": "ROA fell by 40%.",
                             "tool_result_ids": ["result_1"]}],
               "contradictory_evidence": []}
        checked, report = verify_copy(out, trace({"value": 0.08, "fyear": 2022}))
        self.assertEqual(report["blocked_items"], 1)
        self.assertEqual(report["reasons"]["numeric_claim_unsupported"], 1)

    def test_unknown_result_id_blocked(self):
        out = {"evidence": [{"claim": "A claim.", "tool_result_ids": ["result_99"]}],
               "contradictory_evidence": []}
        _, report = verify_copy(out, trace({"value": 0.08}))
        self.assertEqual(report["reasons"]["missing_or_unknown_ids"], 1)

    def test_direction_conflict_blocked(self):
        out = {"evidence": [{"claim": "ROA is above its historical median.",
                             "tool_result_ids": ["result_1"]}],
               "contradictory_evidence": []}
        _, report = verify_copy(out, trace({"direction": "below", "change": -0.08}))
        self.assertEqual(report["reasons"]["direction_contradicts_result"], 1)

    def test_raw_output_preserved(self):
        out = {"evidence": [{"claim": "40% unsupported.",
                             "tool_result_ids": ["result_1"]}],
               "contradictory_evidence": []}
        checked, _ = verify_copy(out, trace({"value": 0.08}))
        self.assertEqual(len(out["evidence"]), 1)
        self.assertEqual(len(checked["evidence"]), 0)


# --- amendments of 2026-11-10 ---------------------------------------------


class DocumentLabelTests(unittest.TestCase):
    """Amendment 1. Digits in a document or statute name are not quantities.

    Every one of these was blocked as numeric_claim_unsupported before the
    fix, because the number pattern pulled 10 out of "10-K", 9 out of
    "Item 9A" and 404 out of "404(b)". That would have blocked every claim
    Said's filing tools produce, and it put the wrong reason on the block.
    """

    def test_ten_k_is_not_the_number_ten(self):
        _, report = verify_copy(
            one("The 10-K was filed.", ids=["result_1"]),
            trace({"value": 0.08}, {"fyear": 2018}),
        )
        self.assertEqual(report["reasons"]["numeric_claim_unsupported"], 0)

    def test_item_9a_is_not_the_number_nine(self):
        _, report = verify_copy(
            one("Item 9A is discussed.", ids=["result_1"]),
            trace({"section": "Item 9A", "value": 0.08}, {"fyear": 2018}),
        )
        self.assertEqual(report["blocked_items"], 0, report["issues"])

    def test_sox_404b_is_not_the_number_404(self):
        _, report = verify_copy(
            one("SOX 404(b) applies.", ids=["result_1"]),
            trace({"value": 0.08}, {"fyear": 2018}),
        )
        self.assertEqual(report["reasons"]["numeric_claim_unsupported"], 0)

    def test_a_real_quantity_beside_a_label_is_still_checked(self):
        """Masking the label must not excuse the rest of the sentence."""
        _, report = verify_copy(
            one("Item 9A reports a rate of 0.4100.", ids=["result_1"]),
            trace({"section": "Item 9A", "value": 0.08}, {"fyear": 2018}),
        )
        self.assertEqual(report["reasons"]["numeric_claim_unsupported"], 1)
        self.assertEqual(report["issues"][0]["detail"], ["0.4100"])


class YearGroundingTests(unittest.TestCase):
    """Amendment 2. A year is grounded by the entity layer, not the numeric one.

    "Features are drawn from 2018" was blocked, because 2018 is not among the
    values score_firm returns. The system prompt asks the model to state the
    assessment year, so the verifier was blocking compliant output.
    """

    def test_year_the_tool_was_called_with_is_grounded(self):
        _, report = verify_copy(
            one("Features are drawn from 2018.", ids=["result_1"]),
            trace({"value": 0.08}, {"gvkey": "FIRM_A", "fyear": 2018}),
        )
        self.assertEqual(report["blocked_items"], 0, report["issues"])

    def test_year_the_tool_returned_is_grounded(self):
        _, report = verify_copy(
            one("Controls were effective in 2018.", ids=["result_1"]),
            trace({"value": {"effective_years": [2018]}}, {"gvkey": "FIRM_A"}),
        )
        self.assertEqual(report["blocked_items"], 0, report["issues"])

    def test_a_year_no_cited_call_touched_is_blocked(self):
        _, report = verify_copy(
            one("Controls failed in 2021.", ids=["result_1"]),
            trace({"value": 0.08}, {"gvkey": "FIRM_A", "fyear": 2018}),
        )
        self.assertEqual(report["reasons"]["entity_not_in_results"], 1)
        self.assertIn("2021", report["issues"][0]["detail"])

    def test_year_grounding_fails_closed(self):
        """No grounded year at all means no year may be named."""
        _, report = verify_copy(
            one("Controls failed in 2018.", ids=["result_1"]),
            trace({"value": 0.08}, {"gvkey": "FIRM_A"}),
        )
        self.assertEqual(report["reasons"]["entity_not_in_results"], 1)


class ProseEntityTests(unittest.TestCase):
    """Amendment 3. Entity grounding reads the prose.

    "Enron shows elevated risk" passed before the fix. Section 3.3 of the spec
    calls this the most dangerous failure mode we have, because it is the model
    substituting a company it knows from training for the firm under
    assessment.
    """

    def test_a_company_the_model_invented_is_blocked(self):
        _, report = verify_copy(
            one("Enron shows elevated risk.", ids=["result_1"]),
            trace({"value": 0.08}, {"gvkey": "FIRM_A", "fyear": 2018}),
        )
        self.assertEqual(report["reasons"]["entity_not_in_results"], 1)
        self.assertIn("Enron", report["issues"][0]["detail"])

    def test_the_session_alias_is_allowed(self):
        _, report = verify_copy(
            one("FIRM_A shows elevated risk.", ids=["result_1"]),
            trace({"gvkey": "FIRM_A", "value": 0.08}, {"fyear": 2018}),
        )
        self.assertEqual(report["blocked_items"], 0, report["issues"])

    def test_ordinary_reporting_language_is_allowed(self):
        _, report = verify_copy(
            one("Comparable firms show an elevated adverse rate.", ids=["result_1"]),
            trace({"value": 0.08}, {"fyear": 2018}),
        )
        self.assertEqual(report["blocked_items"], 0, report["issues"])


class InterpretationTests(unittest.TestCase):
    """Amendment 4. The interpretation text is displayed, so it is checked.

    An unsupported figure in the interpretation reaches the reader exactly as
    one in the claim does. Spec section 3.1 said "claim's text" and is amended.
    """

    def test_unsupported_number_in_the_interpretation_is_blocked(self):
        _, report = verify_copy(
            one("Risk is elevated.", "The rate is 0.9900.", ids=["result_1"]),
            trace({"value": 0.08}, {"fyear": 2018}),
        )
        self.assertEqual(report["reasons"]["numeric_claim_unsupported"], 1)

    def test_invented_name_in_the_interpretation_is_blocked(self):
        _, report = verify_copy(
            one("Risk is elevated.", "Comparable to Wirecard.", ids=["result_1"]),
            trace({"value": 0.08}, {"fyear": 2018}),
        )
        self.assertEqual(report["reasons"]["entity_not_in_results"], 1)


class DirectionWordBoundaryTests(unittest.TestCase):
    """Amendment 5. Direction terms match on word boundaries.

    Substring matching made "undergo" collide with "under", so a neutral
    sentence could be reported as contradicting the tool.
    """

    def test_a_word_containing_a_direction_term_is_not_a_conflict(self):
        _, report = verify_copy(
            one("Controls undergo annual testing.", ids=["result_1"]),
            trace({"direction": "above", "value": 0.08}, {"fyear": 2018}),
        )
        self.assertEqual(report["reasons"]["direction_contradicts_result"], 0)

    def test_a_real_contradiction_is_still_caught(self):
        _, report = verify_copy(
            one("The rate is lower than its own median.", ids=["result_1"]),
            trace({"direction": "above", "value": 0.08}, {"fyear": 2018}),
        )
        self.assertEqual(report["reasons"]["direction_contradicts_result"], 1)


class ReportShapeTests(unittest.TestCase):
    """Spec section 4 fixes the report shape. The evaluation reads it."""

    def test_report_carries_every_reason_key_even_at_zero(self):
        _, report = verify_copy(
            one("The probability is 0.08.", ids=["result_1"]),
            trace({"value": 0.08}, {"fyear": 2018}),
        )
        self.assertEqual(
            set(report["reasons"]),
            {"missing_or_unknown_ids", "numeric_claim_unsupported",
             "direction_contradicts_result", "entity_not_in_results"},
        )
        self.assertEqual(report["block_rate"], 0.0)

    def test_block_rate_is_blocked_over_total(self):
        out = {"evidence": [
            {"claim": "The probability is 0.08.", "tool_result_ids": ["result_1"]},
            {"claim": "The probability is 0.99.", "tool_result_ids": ["result_1"]},
        ], "contradictory_evidence": []}
        _, report = verify_copy(out, trace({"value": 0.08}, {"fyear": 2018}))
        self.assertEqual(report["verified_items"], 1)
        self.assertEqual(report["blocked_items"], 1)
        self.assertEqual(report["block_rate"], 0.5)

    def test_an_empty_output_does_not_divide_by_zero(self):
        _, report = verify_copy({"evidence": [], "contradictory_evidence": []},
                                trace({"value": 0.08}))
        self.assertEqual(report["block_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
