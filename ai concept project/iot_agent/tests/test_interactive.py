import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agent.interactive import InteractiveDiagnosis
from env.case_env import load_case


class FakeMemory:
    def __init__(self):
        self.user_facts = []
        self.actions = []

    def update(self, tool, args, result):
        self.user_facts.append({"tool": tool, "args": args, "result": result})

    def add_action(self, action, target_cause, outcome, resolved):
        self.actions.append({
            "action": action,
            "target_cause": target_cause,
            "outcome": outcome,
            "resolved": resolved,
        })


class InteractiveDiagnosisTests(unittest.TestCase):
    def make_session(self, pending):
        session = InteractiveDiagnosis.__new__(InteractiveDiagnosis)
        session.pending = pending
        session.memory = FakeMemory()
        session.env = SimpleNamespace(trace=[], actions_done=[])
        session.notes = []
        session.step = 1
        return session

    def test_customer_answer_is_saved_and_recorded_in_trace(self):
        session = self.make_session({
            "tool": "ask_user",
            "args": {"question": "What color is the base station LED?"},
        })

        session._record_user_answer("  Solid blue  ", resolved=None)

        self.assertEqual(session.memory.user_facts[0]["result"], {"answer": "Solid blue"})
        self.assertEqual(session.env.trace[0]["result"], {"answer": "Solid blue"})
        self.assertIsNone(session.pending)

    def test_action_reply_records_the_customers_resolution_choice(self):
        session = self.make_session({
            "tool": "instruct_user",
            "args": {"action": "Move the base station closer.", "target_cause": "WEAK_SIGNAL"},
        })

        session._record_user_answer("The camera stayed online.", resolved=True)

        self.assertEqual(session.env.actions_done, ["Move the base station closer."])
        self.assertTrue(session.memory.actions[0]["resolved"])
        self.assertEqual(session.env.trace[0]["result"], {"outcome": "The camera stayed online."})
        self.assertIsNone(session.pending)

    def test_action_reply_requires_an_explicit_resolution_choice(self):
        session = self.make_session({
            "tool": "instruct_user",
            "args": {"action": "Restart the sensor.", "target_cause": "HW_FAULT_SUSPECTED"},
        })

        with self.assertRaisesRegex(ValueError, "Choose whether"):
            session._record_user_answer("It is still offline.", resolved=None)

        self.assertEqual(session.env.trace, [])
        self.assertIsNotNone(session.pending)

    def test_blank_customer_reply_is_rejected_before_resume(self):
        session = self.make_session({"tool": "ask_user", "args": {"question": "Where is it?"}})

        with self.assertRaisesRegex(ValueError, "enter a reply"):
            session.submit("   ")

        self.assertIsNotNone(session.pending)

    def test_session_pauses_for_customer_then_finishes_with_the_reply(self):
        session = InteractiveDiagnosis(load_case("C001"))
        ask = {
            "tool_calls": [{
                "name": "ask_user",
                "arguments": json.dumps({"question": "Did you move the base station recently?"}),
            }],
        }
        submit = {
            "tool_calls": [{
                "name": "submit_diagnosis",
                "arguments": json.dumps({
                    "root_cause": "WEAK_SIGNAL",
                    "rationale": "The camera has weak signal after relocation.",
                }),
            }],
        }
        with patch("agent.interactive.llm.chat", side_effect=[ask, submit]), \
                patch("agent.interactive.build_output", return_value={"repair_steps": []}):
            prompt = session.start()
            self.assertIn("move the base station", prompt)
            self.assertIsNone(session.result)

            next_prompt = session.submit("Yes, I moved it farther away.")

        self.assertIsNone(next_prompt)
        self.assertEqual(session.result["pred_root_cause"], "WEAK_SIGNAL")
        self.assertEqual(
            session.memory.user_facts[0]["answer"],
            "Yes, I moved it farther away.",
        )
        self.assertEqual(session.env.trace[-1]["tool"], "ask_user")


if __name__ == "__main__":
    unittest.main()
