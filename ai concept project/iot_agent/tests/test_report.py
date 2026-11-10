import unittest

from eval.report import escalation_scores, executed_repeats


class EscalationScoreTests(unittest.TestCase):
    def test_precision_and_recall_count_unneeded_and_missed_escalations(self):
        rows = [
            {"pred_tier": "L2", "gt_tier": "L2"},   # correct escalation
            {"pred_tier": "L2", "gt_tier": "L1"},   # unneeded escalation (wastes FAE time)
            {"pred_tier": "L1", "gt_tier": "L2"},   # missed escalation
            {"pred_tier": "L1", "gt_tier": "L1"},   # correct frontline closure
        ]
        precision, recall, unneeded, missed = escalation_scores(rows)
        self.assertEqual((precision, recall, unneeded, missed), (0.5, 0.5, 1, 1))

    def test_no_escalations_gives_zero_scores(self):
        self.assertEqual(escalation_scores([{"pred_tier": "L1", "gt_tier": "L1"}]), (0.0, 0.0, 0, 0))


class RepeatedQueryTests(unittest.TestCase):
    def test_counts_identical_queries_but_not_repeated_fix_attempts(self):
        trace = [
            {"tool": "get_base_status", "args": {}},
            {"tool": "get_base_status", "args": {}},
            {"tool": "ask_user", "args": {"question": "LED colour?"}},
            {"tool": "ask_user", "args": {"question": "led colour?"}},
            {"tool": "get_device_info", "args": {"device_id": "cam"}},
            {"tool": "instruct_user", "args": {"action": "Restart"}},
            {"tool": "instruct_user", "args": {"action": "Restart"}},
        ]
        self.assertEqual(executed_repeats({"trace": trace}), 2)


if __name__ == "__main__":
    unittest.main()
