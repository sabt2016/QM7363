import unittest
from src.task_5_2_integration import IntegrationError, validate_temporal_arguments

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

if __name__ == "__main__":
    unittest.main()
