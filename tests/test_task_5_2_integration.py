"""Tests for the task 5.2 integration layer.

The first two are Enock's. The rest were added on 2026-11-10 to cover what the
unit tests could not: the gate that refuses to run against stubs, and a full
pass of the offline pipeline through the verifier. The second of those is the
test that would have caught the verifier blocking legitimate claims, because
every defect found on 10 November was found by connecting components, not by
reading either one.
"""
import unittest

from src.task_5_2_integration import IntegrationError, build_tool_map, validate_temporal_arguments


class Dummy:
    def get_firm_history(self, gvkey, through_fyear): pass
    def get_control_history(self, gvkey, through_fyear): pass
    def get_cohort_rate(self, slice_name, fyear): pass


class IntegrationTests(unittest.TestCase):
    def test_temporal_contract_passes(self):
        validate_temporal_arguments({
            "get_firm_history": Dummy.get_firm_history,
            "get_control_history": Dummy.get_control_history,
            "get_cohort_rate": Dummy.get_cohort_rate,
        }, 2022)

    def test_control_history_without_cutoff_fails_closed(self):
        def unsafe_control_history(gvkey): pass
        with self.assertRaises(IntegrationError):
            validate_temporal_arguments({
                "get_firm_history": Dummy.get_firm_history,
                "get_control_history": unsafe_control_history,
                "get_cohort_rate": Dummy.get_cohort_rate,
            }, 2022)

    def test_cohort_rate_without_a_year_fails_closed(self):
        def unsafe_cohort_rate(slice_name): pass
        with self.assertRaises(IntegrationError):
            validate_temporal_arguments({
                "get_firm_history": Dummy.get_firm_history,
                "get_control_history": Dummy.get_control_history,
                "get_cohort_rate": unsafe_cohort_rate,
            }, 2022)


class StubGateTests(unittest.TestCase):
    """build_tool_map refuses the stub layer, and that is the intended state.

    Every tool in src/tools.py still carries "Stub implementation" in its
    source, so this raises today and will keep raising until Said lands the
    real tools. The test exists so that nobody reads the exception as a break.
    """

    def test_the_stub_layer_is_refused(self):
        # model_module is supplied so the test does not need config.py, which is
        # gitignored and differs per machine. The gate under test is the one on
        # the nine tools, not the model adapter.
        import types

        def score_firm(gvkey, fyear):
            return {"value": {}, "source": "test", "notes": ""}

        fake_model = types.SimpleNamespace(score_firm=score_firm)
        with self.assertRaises(IntegrationError) as caught:
            build_tool_map(model_module=fake_model)
        self.assertIn("stub", str(caught.exception).lower())


class OfflinePipelineTests(unittest.TestCase):
    """The offline demo, end to end, through the verifier.

    src.session drives the agent against the same tool layer with a scripted
    provider, so this runs with no key, no panel and no model file. It is the
    cheapest honest check that the loop, the tool contract and the verifier
    still fit together.
    """

    @classmethod
    def setUpClass(cls):
        from src.session import run_assessment
        cls.res = run_assessment(gvkey="001004", fyear=2018,
                                 inject_unsupported=True)

    def test_every_planned_tool_call_succeeded(self):
        """A failed call here means the scripted plan has drifted from the contract.

        It had: the plan called get_control_history without through_fyear after
        the look-ahead amendment of 6 November, so the first call raised
        TypeError and the prior-opinion evidence silently disappeared.
        """
        calls = [e for e in self.res["trace"] if e.get("event") == "tool_call"]
        self.assertTrue(calls)
        for call in calls:
            self.assertEqual(call["status"], "ok",
                             f"{call.get('tool')} failed: {call.get('error')}")

    def test_the_fabricated_claim_is_the_only_thing_blocked(self):
        report = self.res["report"]
        self.assertEqual(report["blocked_items"], 1, report["issues"])
        self.assertEqual(report["reasons"]["missing_or_unknown_ids"], 1)
        self.assertEqual(report["issues"][0]["detail"], ["result_99"])

    def test_no_legitimate_claim_is_over_blocked(self):
        """The numeric, direction and entity layers must leave good claims alone.

        This is the regression test for 10 November. The verifier blocked a
        claim naming the correct fiscal year, and any claim mentioning a 10-K
        or Item 9A, because digits inside those labels were read as quantities.
        """
        report = self.res["report"]
        self.assertEqual(report["reasons"]["numeric_claim_unsupported"], 0,
                         report["issues"])
        self.assertEqual(report["reasons"]["direction_contradicts_result"], 0,
                         report["issues"])
        self.assertEqual(report["reasons"]["entity_not_in_results"], 0,
                         report["issues"])
        self.assertGreaterEqual(len(self.res["output"]["evidence"]), 4)

    def test_the_model_never_receives_the_real_identifier(self):
        """The alias boundary, checked on the return path as well as the call."""
        import json
        blob = json.dumps(self.res["trace"], default=str)
        self.assertNotIn(self.res["gvkey"], blob)
        self.assertIn(self.res["alias"], blob)

    def test_the_report_carries_a_rate_and_a_reason_breakdown(self):
        report = self.res["report"]
        self.assertIn("block_rate", report)
        self.assertIn("reasons", report)
        self.assertEqual(
            report["blocked_items"] + report["verified_items"],
            self.res["claims_before"],
        )


if __name__ == "__main__":
    unittest.main()
