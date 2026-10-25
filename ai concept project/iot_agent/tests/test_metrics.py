import unittest

from eval.metrics import calculate_metrics


class CalculateMetricsTests(unittest.TestCase):
    def test_metrics_include_case_accuracy_and_repeated_questions(self):
        rows = [
            {
                "pred_root_cause": "WEAK_SIGNAL",
                "gt_root_cause": "WEAK_SIGNAL",
                "pred_tier": "L1",
                "gt_tier": "L1",
                "user_turns": 2,
                "usability_score": 4,
                "log": [
                    {"tool": "ask_user", "args": {"question": "Where is the base?"}},
                    {"tool": "ask_user", "args": {"question": " where  is THE base? "}},
                ],
            },
            {
                "pred_root_cause": "PAIR_TIMEOUT",
                "gt_root_cause": "CAPACITY_EXCEEDED",
                "pred_tier": "L2",
                "gt_tier": "L1",
                "user_turns": 0,
                "log": [],
            },
        ]

        self.assertEqual(
            calculate_metrics(rows),
            {
                "case_count": 2,
                "diagnosis_success_rate": 0.5,
                "average_interaction_rounds": 1.0,
                "redundant_inquiry_rate": 0.5,
                "fault_classification_accuracy": 0.5,
                "support_usability_score": 4.0,
                "usability_scored_cases": 1,
            },
        )

    def test_no_questions_or_usability_scores_are_reported_as_zero_and_unscored(self):
        row = {
            "pred_root_cause": "WEAK_SIGNAL",
            "gt_root_cause": "WEAK_SIGNAL",
            "pred_tier": "L1",
            "gt_tier": "L1",
        }

        metrics = calculate_metrics([row])

        self.assertEqual(metrics["redundant_inquiry_rate"], 0.0)
        self.assertIsNone(metrics["support_usability_score"])
        self.assertEqual(metrics["usability_scored_cases"], 0)

    def test_empty_results_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "empty result set"):
            calculate_metrics([])


if __name__ == "__main__":
    unittest.main()
