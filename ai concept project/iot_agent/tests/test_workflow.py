import json
import unittest
from unittest.mock import patch

from agent.agent import TopologyAgent
from agent.memory import SessionMemory
from agent.triage import build_output
from agent.workflow import (
    validate_diagnosis,
    validate_final_output,
    validate_tool_call,
    validate_tool_result,
)
from env.case_env import CaseEnv, load_case


class TopologyWorkflowTests(unittest.TestCase):
    def test_batch_agent_runs_reasoning_and_tool_nodes_in_langgraph(self):
        tool_calls = [
            {
                "tool_calls": [
                    {
                        "name": "get_topology",
                        "arguments": "{}",
                    }
                ]
            },
            {
                "tool_calls": [
                    {
                        "name": "submit_diagnosis",
                        "arguments": json.dumps(
                            {
                                "root_cause": "WEAK_SIGNAL",
                                "rationale": "The selected diagnosis is supported by the evidence.",
                            }
                        ),
                    }
                ]
            },
        ]
        env = CaseEnv(load_case("C001"))
        with patch("agent.workflow.llm.chat", side_effect=tool_calls), patch(
            "agent.workflow.build_output",
            return_value={
                "repair_steps": ["Confirm the connection."],
                "customer_reply": "We have identified the issue.",
            },
        ):
            result = TopologyAgent().run(env)

        self.assertEqual(result["system"], "topology_agent")
        self.assertEqual(result["pred_root_cause"], "WEAK_SIGNAL")
        self.assertEqual(
            [entry["tool"] for entry in result["log"][-2:]],
            ["get_topology", "submit_diagnosis"],
        )
        self.assertGreater(len(env.trace), 0)
        self.assertEqual(result["trace"], env.trace)

    def test_session_memory_recalls_relevant_interactions(self):
        memory = SessionMemory("Camera disconnects when the base station is far away.")
        memory.update(
            "ask_user",
            {"question": "Where is the base station?"},
            {"answer": "It is in the basement."},
        )

        recalled = memory.recall_interactions("base station location basement")

        self.assertEqual(len(recalled), 1)
        self.assertIn("basement", recalled[0])

    def test_validation_rejects_bad_tool_calls_results_and_diagnoses(self):
        agent = TopologyAgent()

        self.assertIsNone(
            validate_tool_call({"name": "get_topology", "args": {}}, agent.tools)
        )
        self.assertIn(
            "Missing required",
            validate_tool_call(
                {"name": "get_device_info", "args": {}}, agent.tools
            ),
        )
        self.assertIn(
            "missing a valid",
            validate_tool_result("get_topology", {"devices": "not-a-list"}),
        )
        self.assertIn(
            "unknown root-cause",
            validate_diagnosis({"root_cause": "UNKNOWN", "rationale": "A reason."}),
        )
        self.assertIsNone(
            validate_final_output(
                "L1",
                {
                    "repair_steps": ["Confirm the connection."],
                    "customer_reply": "We will help.",
                },
            )
        )

    def test_final_output_schema_failure_gets_one_repair_attempt(self):
        valid = {
            "repair_steps": ["Confirm the connection."],
            "customer_reply": "We will help.",
        }
        with patch(
            "agent.triage.llm.chat_json",
            side_effect=[{"customer_reply": ""}, valid],
        ) as model:
            result = build_output(
                SessionMemory("The camera keeps disconnecting."),
                "WEAK_SIGNAL",
                "L1",
                "The link is weak.",
                [],
            )

        self.assertEqual(result, valid)
        self.assertEqual(model.call_count, 2)
        self.assertFalse(model.call_args.kwargs["use_cache"])


class BatchActionOutcomeTests(unittest.TestCase):
    def _record(self, verdict, key="resolved"):
        env = CaseEnv(load_case("C046"))
        memory = SessionMemory(env.case["complaint"])
        with patch("agent.workflow.llm.chat_json", return_value=verdict) as model:
            TopologyAgent()._call(env, memory, "instruct_user",
                                  {"action": "Move the camera closer as a test.", "target_cause": "WEAK_SIGNAL"})
        self.judge_prompt = model.call_args.args[0][0]["content"]
        return memory.actions[-1][key]

    def test_unclear_reply_is_not_recorded_as_a_failed_fix(self):
        self.assertIsNone(self._record({"resolved": None, "reason": "仅为诊断性测试"}))
        self.assertIsNone(self._record({}))

    def test_clear_verdicts_are_kept(self):
        self.assertIs(self._record({"resolved": True}), True)
        self.assertIs(self._record({"resolved": False}), False)

    def test_judge_compares_the_action_with_the_standard_fix(self):
        self.assertIs(self._record({"resolved": False, "standard_fix": False}, "standard_fix"), False)
        self.assertIn("add the official repeater", self.judge_prompt)
        self.assertIs(self._record({"resolved": False, "standard_fix": True}, "standard_fix"), True)


if __name__ == "__main__":
    unittest.main()
