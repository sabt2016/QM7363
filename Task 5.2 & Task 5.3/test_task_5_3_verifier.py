import unittest
from src.task_5_3_verifier import verify_copy

def trace(result):
    return [{"event": "tool_call", "status": "ok",
             "result": {"result_id": "result_1", **result}}]

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

if __name__ == "__main__":
    unittest.main()
