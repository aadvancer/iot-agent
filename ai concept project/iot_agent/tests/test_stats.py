import unittest

from eval.dataset_stats import load_cases, split_stats
from eval.report import cost_breakdown_table, error_table, repeat_table, significance_table
from eval.stats import mcnemar_exact, paired_outcomes, wilson_ci


class WilsonTests(unittest.TestCase):
    def test_known_interval(self):
        lo, hi = wilson_ci(37, 40)
        self.assertAlmostEqual(lo, 0.8014, places=3)
        self.assertAlmostEqual(hi, 0.9742, places=3)

    def test_perfect_score_upper_bound_is_one_and_lower_bound_reflects_sample_size(self):
        lo, hi = wilson_ci(40, 40)
        self.assertEqual(hi, 1.0)
        self.assertAlmostEqual(lo, 0.9124, places=3)

    def test_empty(self):
        self.assertEqual(wilson_ci(0, 0), (0.0, 0.0))


class McNemarTests(unittest.TestCase):
    def test_exact_two_sided_values(self):
        self.assertAlmostEqual(mcnemar_exact(6, 0), 0.03125)
        self.assertAlmostEqual(mcnemar_exact(3, 0), 0.25)
        self.assertEqual(mcnemar_exact(1, 1), 1.0)
        self.assertEqual(mcnemar_exact(0, 0), 1.0)

    def test_symmetric(self):
        self.assertEqual(mcnemar_exact(5, 2), mcnemar_exact(2, 5))

    def test_paired_outcomes_only_count_shared_discordant_cases(self):
        a = [{"case_id": "C1", "ok": True}, {"case_id": "C2", "ok": True}, {"case_id": "C3", "ok": False},
             {"case_id": "C9", "ok": True}]
        b = [{"case_id": "C1", "ok": True}, {"case_id": "C2", "ok": False}, {"case_id": "C3", "ok": True}]
        self.assertEqual(paired_outcomes(a, b, lambda r: r["ok"]), (1, 1))


class ReportSectionTests(unittest.TestCase):
    rows = {
        "vanilla_llm": [
            {"case_id": "C1", "pred_root_cause": "A", "gt_root_cause": "B", "pred_tier": "L1", "gt_tier": "L2"},
            {"case_id": "C2", "pred_root_cause": "A", "gt_root_cause": "A", "pred_tier": "L1", "gt_tier": "L1"},
        ],
        "topology": [
            {"case_id": "C1", "pred_root_cause": "B", "gt_root_cause": "B", "pred_tier": "L2", "gt_tier": "L2"},
            {"case_id": "C2", "pred_root_cause": "A", "gt_root_cause": "A", "pred_tier": "L1", "gt_tier": "L1"},
        ],
    }

    def test_significance_row_compares_against_topology_agent(self):
        lines = significance_table(self.rows)
        self.assertIn("1/2 = 50%", lines[2])
        self.assertIn("| 1 / 0 | 1.000 |", lines[2])
        self.assertTrue(lines[3].endswith("| — | — | — | — |"))

    def test_error_table_lists_wrong_cases_only(self):
        lines = error_table(self.rows)
        self.assertIn("C1: A → B", lines[2])
        self.assertNotIn("C2", lines[2])
        self.assertIn("| none | none |", lines[3])


class RepeatAndCostTests(unittest.TestCase):
    @staticmethod
    def _row(case_id, pred, gt="A", tokens=100, trace=()):
        return {"case_id": case_id, "split": "core", "pred_root_cause": pred, "gt_root_cause": gt,
                "pred_tier": "L1", "gt_tier": "L1", "tokens": tokens, "llm_calls": 2, "trace": list(trace)}

    def test_repeat_table_reports_spread_and_unstable_cases(self):
        runs = {"topology": {1: [self._row("C1", "A"), self._row("C2", "A")],
                             2: [self._row("C1", "A"), self._row("C2", "B")]}}
        lines = repeat_table(runs, "core")
        self.assertIn("100% / 50%", lines[2])
        self.assertIn("75.0% ± 35.4%", lines[2])
        self.assertTrue(lines[2].endswith("| C2 |"))

    def test_single_run_gives_no_repeat_table(self):
        self.assertEqual(repeat_table({"topology": {1: [self._row("C1", "A")]}}, "core"), [])

    def test_cost_breakdown_counts_tools_per_case(self):
        trace = [{"tool": "get_topology"}, {"tool": "search_kb"}, {"tool": "search_kb"}, {"tool": "ask_user"}]
        lines = cost_breakdown_table({"react": [self._row("C1", "A", tokens=300, trace=trace),
                                                self._row("C2", "A", tokens=100)]})
        self.assertEqual(lines[2], "| ReAct (same tools) | 0.5 | 1.0 | 0.50 | 0.00 | 2.0 | 100 | 200 |")


class HumanRatingTests(unittest.TestCase):
    def test_spearman_handles_ties_and_perfect_order(self):
        from eval.human_rating import spearman

        self.assertAlmostEqual(spearman([1, 2, 3, 4], [2, 3, 4, 5]), 1.0)
        self.assertAlmostEqual(spearman([1, 2, 3], [3, 2, 1]), -1.0)
        self.assertAlmostEqual(spearman([1, 1, 2, 3], [1, 2, 2, 3]), 0.833333, places=5)  # = scipy.stats.spearmanr

    def test_agreement_summary(self):
        from eval.human_rating import agreement

        s = agreement([("topology", 4, 4), ("topology", 5, 3), ("react", 3, 4)])
        self.assertAlmostEqual(s["exact"], 1 / 3)
        self.assertAlmostEqual(s["within_1"], 2 / 3)
        self.assertEqual(s["per_system"]["topology"], (4.5, 3.5))


class HardCaseTests(unittest.TestCase):
    @staticmethod
    def _r(case_id, pred, gt="A", tier="L1"):
        return {"case_id": case_id, "pred_root_cause": pred, "gt_root_cause": gt, "pred_tier": tier, "gt_tier": "L1"}

    def test_rule_hard_cases_are_rules_only_errors(self):
        from eval.report import rule_hard_cases

        rows = {"rules_only": [self._r("C1", "A"), self._r("C2", "B"), self._r("C3", "B")]}
        self.assertEqual(rule_hard_cases(rows), ["C2", "C3"])

    def test_subset_stats_mean_and_pass_k(self):
        from eval.report import subset_stats

        run1 = {"C1": self._r("C1", "A"), "C2": self._r("C2", "A")}
        run2 = {"C1": self._r("C1", "A"), "C2": self._r("C2", "B", tier="L2")}
        s = subset_stats([run1, run2], ["C1", "C2"])
        self.assertAlmostEqual(s["cause"], 0.75)
        self.assertEqual((s["pass_cause"], s["pass_tier"], s["consistent"]), (1, 1, 1))
        self.assertIsNone(subset_stats([run1], ["C9"]))


class DatasetStatsTests(unittest.TestCase):
    def test_split_sizes_and_tiers_are_consistent(self):
        cases = load_cases()
        for split in ("core", "challenge"):
            rows = [c for c in cases if c["split"] == split]
            stats = split_stats(rows)
            self.assertEqual(stats["L1"] + stats["L2"], stats["cases"])
            self.assertEqual(stats["easy"] + stats["medium"] + stats["hard"], stats["cases"])
        self.assertEqual(sum(c["split"] == "core" for c in cases), 40)


if __name__ == "__main__":
    unittest.main()
