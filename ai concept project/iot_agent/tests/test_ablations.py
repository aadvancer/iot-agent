import json
import unittest
from unittest.mock import patch

from agent.agent import ABLATIONS, NoHintsAgent, NoMemoryAgent, NoOverrideAgent, NoPlannerAgent, TopologyAgent
from agent.workflow import HINTS_OFF_NOTE, PLANNER_OFF_NOTE, _system_prompt
from env.case_env import CaseEnv, load_case

L1_OUTPUT = {"repair_steps": ["Confirm the connection."], "customer_reply": "We have identified the issue."}
L2_OUTPUT = {"symptom_summary": "s", "suspected_root_cause": "c", "key_abnormal_indicators": [],
             "customer_reply": "An engineer will follow up."}


def _submit(cause):
    return {"tool_calls": [{"name": "submit_diagnosis",
                            "arguments": json.dumps({"root_cause": cause, "rationale": "Evidence."})}]}


def _run(agent_cls, case_id, cause, output=L1_OUTPUT):
    env = CaseEnv(load_case(case_id))
    with patch("agent.workflow.llm.chat", return_value=_submit(cause)) as chat, \
            patch("agent.workflow.build_output", return_value=output):
        result = agent_cls().run(env)
    return result, chat.call_args.args[0]


class AblationTests(unittest.TestCase):
    def test_ablations_are_registered_with_distinct_names(self):
        self.assertEqual(set(ABLATIONS),
                         {"abl_no_planner", "abl_no_hints", "abl_no_memory", "abl_no_override"})

    def test_prompt_switches_change_the_system_prompt(self):
        full = _system_prompt(TopologyAgent.__new__(TopologyAgent), 10)
        self.assertNotIn(PLANNER_OFF_NOTE, full)
        self.assertNotIn(HINTS_OFF_NOTE, full)
        no_planner = _system_prompt(NoPlannerAgent.__new__(NoPlannerAgent), 10)
        self.assertIn(PLANNER_OFF_NOTE, no_planner)
        self.assertNotIn("already been collected", no_planner)
        no_hints = _system_prompt(NoHintsAgent.__new__(NoHintsAgent), 10)
        self.assertIn(HINTS_OFF_NOTE, no_hints)
        self.assertNotIn("matched deterministically", no_hints)

    def test_no_planner_collects_no_evidence_before_reasoning(self):
        result, _ = _run(NoPlannerAgent, "C001", "WEAK_SIGNAL")
        self.assertEqual(result["trace"], [])
        self.assertFalse(any(entry["phase"] == "collect" for entry in result["log"]))

    def test_no_hints_hides_rule_hints_from_the_llm(self):
        _, messages = _run(NoHintsAgent, "C001", "WEAK_SIGNAL")
        self.assertIn("RULE HINTS:\n(disabled)", messages[1]["content"])

    def test_no_memory_shows_raw_transcript_instead_of_snapshot(self):
        _, messages = _run(NoMemoryAgent, "C001", "WEAK_SIGNAL")
        self.assertNotIn("stages_done", messages[1]["content"])
        self.assertIn("1. get_base_status({})", messages[1]["content"])

    def test_no_memory_disables_the_dedup_guard(self):
        agent = NoMemoryAgent()
        env = CaseEnv(load_case("C001"))
        from agent.memory import SessionMemory
        memory = SessionMemory(env.case["complaint"])
        agent._call(env, memory, "get_base_status", {})
        agent._call(env, memory, "get_base_status", {})
        self.assertEqual(memory.dedup_hits, 0)
        self.assertEqual(len(env.trace), 2)

    def test_no_override_keeps_the_taxonomy_tier(self):
        # C051: three sensors dropped together; a BATTERY_LOW guess is escalated only by R1_BATCH
        full, _ = _run(TopologyAgent, "C051", "BATTERY_LOW", L2_OUTPUT)
        self.assertEqual(full["pred_tier"], "L2")
        self.assertTrue(full["tier_overridden"])
        self.assertIn("R1_BATCH", [t["rule"] for t in full["triggers"]])
        ablated, _ = _run(NoOverrideAgent, "C051", "BATTERY_LOW")
        self.assertEqual(ablated["pred_tier"], "L1")
        self.assertEqual(ablated["triggers"], [])
        self.assertFalse(ablated["tier_overridden"])


class KnowledgeSearchGuardTests(unittest.TestCase):
    """Rephrased KB searches that only return known snippets are cut off (C045 failure mode)."""

    SAME = {"results": [{"source": "fault_codes#E-201", "text": "Remove an unused device."}]}

    def _searches(self, agent_cls, n):
        from agent.memory import SessionMemory

        agent, env = agent_cls(), CaseEnv(load_case("C045"))
        memory = SessionMemory(env.case["complaint"])
        with patch("agent.agent.execute", return_value=self.SAME) as execute:
            results = [agent._call(env, memory, "search_kb", {"query": f"orphaned slot {i}"}) for i in range(n)]
        return results, execute.call_count

    def test_stale_searches_are_flagged_then_blocked(self):
        results, executed = self._searches(TopologyAgent, 5)
        self.assertNotIn("note", results[0])
        self.assertIn("No new knowledge", results[1]["note"])
        self.assertIn("No new knowledge", results[2]["note"])
        self.assertEqual(results[3], {"results": [], "note": results[3]["note"]})
        self.assertIn("Stop searching", results[4]["note"])
        self.assertEqual(executed, 3)

    def test_no_memory_ablation_has_no_search_guard(self):
        results, executed = self._searches(NoMemoryAgent, 5)
        self.assertEqual(executed, 5)
        self.assertTrue(all("note" not in r for r in results))


if __name__ == "__main__":
    unittest.main()
