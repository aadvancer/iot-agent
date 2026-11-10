import json
import threading
import unittest
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

from agent.interactive import InteractiveDiagnosis, SessionBusy
from agent.persistence import load_case_facts
from agent.workflow import apply_human_reply
from env.case_env import load_case


def fresh_case():
    case = load_case("C001")
    case["case_id"] = f"test-{uuid4()}"
    return case


class FakeMemory:
    def __init__(self):
        self.user_facts = []
        self.actions = []

    def update(self, tool, args, result):
        self.user_facts.append({"tool": tool, "args": args, "result": result})

    def add_action(self, action, target_cause, outcome, resolved, standard_fix=None):
        self.actions.append({
            "action": action,
            "target_cause": target_cause,
            "outcome": outcome,
            "resolved": resolved,
            "standard_fix": standard_fix,
        })


class InteractiveDiagnosisTests(unittest.TestCase):
    def make_session(self, pending):
        session = InteractiveDiagnosis.__new__(InteractiveDiagnosis)
        session.pending = pending
        session.memory = FakeMemory()
        session.env = SimpleNamespace(trace=[], actions_done=[])
        session.notes = []
        session.step = 1
        session._lock = threading.Lock()
        return session

    def test_customer_answer_is_saved_and_recorded_in_trace(self):
        session = self.make_session({
            "tool": "ask_user",
            "args": {"question": "What color is the base station LED?"},
        })

        apply_human_reply(
            session.memory,
            session.env,
            session.pending,
            {"answer": "  Solid blue  ", "resolved": None},
        )

        self.assertEqual(session.memory.user_facts[0]["result"], {"answer": "Solid blue"})
        self.assertEqual(session.env.trace[0]["result"], {"answer": "Solid blue"})

    def test_action_reply_records_the_customers_resolution_choice(self):
        session = self.make_session({
            "tool": "instruct_user",
            "args": {"action": "Move the base station closer.", "target_cause": "WEAK_SIGNAL"},
        })

        apply_human_reply(
            session.memory,
            session.env,
            session.pending,
            {"answer": "The camera stayed online.", "resolved": True},
        )

        self.assertEqual(session.env.actions_done, ["Move the base station closer."])
        self.assertTrue(session.memory.actions[0]["resolved"])
        self.assertEqual(session.env.trace[0]["result"],
                         {"outcome": "The camera stayed online.", "resolved": True})

    def test_unclear_action_reply_is_recorded_but_not_as_a_failed_fix(self):
        session = self.make_session({
            "tool": "instruct_user",
            "args": {"action": "Restart the sensor.", "target_cause": "HW_FAULT_SUSPECTED"},
        })

        apply_human_reply(
            session.memory,
            session.env,
            session.pending,
            {"answer": "terrible", "resolved": None},
        )

        self.assertIsNone(session.memory.actions[0]["resolved"])
        self.assertEqual(session.env.trace[0]["result"], {"outcome": "terrible", "resolved": None})

    def test_reply_is_rejected_while_the_previous_one_is_processing(self):
        session = self.make_session({"tool": "ask_user", "args": {"question": "Where is it?"}})
        session._lock.acquire()

        with self.assertRaises(SessionBusy):
            session.submit("In the study.")

        self.assertEqual(session.memory.user_facts, [])

    def test_agent_judges_whether_the_guided_action_resolved_the_issue(self):
        session = InteractiveDiagnosis(fresh_case())
        instruct = {"tool_calls": [{"name": "instruct_user", "arguments": json.dumps({
            "action": "Move the base station back to the hallway.", "target_cause": "WEAK_SIGNAL"})}]}
        submit = {"tool_calls": [{"name": "submit_diagnosis", "arguments": json.dumps({
            "root_cause": "WEAK_SIGNAL", "rationale": "Moving the base station fixed the link."})}]}
        with patch("agent.workflow.llm.chat", side_effect=[instruct, submit]), \
                patch("agent.workflow.llm.chat_json",
                      return_value={"resolved": True, "reason": "客户说摄像头一整天都在线。"}) as judge, \
                patch("agent.workflow.build_output", return_value={
                    "repair_steps": ["Keep the base station in the hallway."],
                    "customer_reply": "Glad it works now.",
                }):
            session.start()
            self.assertIsNone(session.submit("移回走廊后摄像头一整天都没掉线"))

        self.assertIn("移回走廊后摄像头一整天都没掉线", judge.call_args[0][0][0]["content"])
        self.assertEqual(session.judgement,
                         {"resolved": True, "standard_fix": None, "reason": "客户说摄像头一整天都在线。"})
        self.assertTrue(session.memory.actions[0]["resolved"])
        self.assertEqual(session.result["pred_tier"], "L1")

    def test_blank_customer_reply_is_rejected_before_resume(self):
        session = self.make_session({"tool": "ask_user", "args": {"question": "Where is it?"}})

        with self.assertRaisesRegex(ValueError, "enter a reply"):
            session.submit("   ")

        self.assertIsNotNone(session.pending)

    def test_session_pauses_for_customer_then_finishes_with_the_reply(self):
        session = InteractiveDiagnosis(fresh_case())
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
        with patch("agent.workflow.llm.chat", side_effect=[ask, submit]), \
                patch("agent.workflow.build_output", return_value={
                "repair_steps": ["Confirm the connection."],
                "customer_reply": "We have identified the issue.",
                "symptom_summary": "The device remains offline.",
                "suspected_root_cause": "The link may be unstable.",
                "key_abnormal_indicators": [],
                }):
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
        self.assertEqual(
            load_case_facts(session.case["case_id"]),
            [{
                "question": "Did you move the base station recently?",
                "answer": "Yes, I moved it farther away.",
            }],
        )

    def test_session_resumes_after_an_instructed_action_and_model_retry(self):
        session = InteractiveDiagnosis(fresh_case())
        instruct = {
            "tool_calls": [{
                "name": "instruct_user",
                "arguments": json.dumps({
                    "action": "Restart the camera.",
                    "target_cause": "WEAK_SIGNAL",
                }),
            }],
        }
        submit = {
            "tool_calls": [{
                "name": "submit_diagnosis",
                "arguments": json.dumps({
                    "root_cause": "WEAK_SIGNAL",
                    "rationale": "The restart did not resolve the connectivity issue.",
                }),
            }],
        }
        with patch(
            "agent.workflow.llm.chat",
            side_effect=[instruct, RuntimeError("temporary model failure"), submit],
        ), patch("agent.workflow.build_output", return_value={
            "repair_steps": ["Confirm the connection."],
            "customer_reply": "We have identified the issue.",
            "symptom_summary": "The device remains offline.",
            "suspected_root_cause": "The link may be unstable.",
            "key_abnormal_indicators": [],
        }):
            self.assertIn("Restart the camera", session.start())
            with self.assertRaisesRegex(RuntimeError, "temporary model failure"):
                session.submit("It is still offline.", resolved=False)

            self.assertIsNone(session.pending)
            self.assertIsNone(session.resume())

        self.assertEqual(session.result["pred_root_cause"], "WEAK_SIGNAL")
        self.assertFalse(session.memory.actions[0]["resolved"])
        self.assertEqual(session.env.trace[-1]["tool"], "instruct_user")

    def test_checkpoint_restores_interrupted_session_in_a_new_instance(self):
        case = fresh_case()
        session = InteractiveDiagnosis(case)
        ask = {
            "tool_calls": [{
                "name": "ask_user",
                "arguments": json.dumps({"question": "Where is the base station?"}),
            }],
        }
        submit = {
            "tool_calls": [{
                "name": "submit_diagnosis",
                "arguments": json.dumps({
                    "root_cause": "WEAK_SIGNAL",
                    "rationale": "The confirmed location explains the weak link.",
                }),
            }],
        }
        with patch("agent.workflow.llm.chat", side_effect=[ask, submit]), \
                patch("agent.workflow.build_output", return_value={
                    "repair_steps": ["Confirm the connection."],
                    "customer_reply": "We have identified the issue.",
                    "symptom_summary": "The device remains offline.",
                    "suspected_root_cause": "The link may be unstable.",
                    "key_abnormal_indicators": [],
                }):
            session.start()
            restored = InteractiveDiagnosis(case)
            self.assertEqual(restored.pending["tool"], "ask_user")
            self.assertIsNone(restored.submit("The base is in the basement."))

        self.assertEqual(restored.result["pred_root_cause"], "WEAK_SIGNAL")
        self.assertEqual(
            restored.memory.user_facts[0]["answer"],
            "The base is in the basement.",
        )

    def test_abandoned_session_is_not_restored_for_the_case(self):
        case = fresh_case()
        session = InteractiveDiagnosis(case)
        ask = {
            "tool_calls": [{
                "name": "ask_user",
                "arguments": json.dumps({"question": "Where is the base station?"}),
            }],
        }
        with patch("agent.workflow.llm.chat", return_value=ask):
            session.start()
        self.assertIsNotNone(session.pending)

        session.abandon()
        restarted = InteractiveDiagnosis(case)

        self.assertFalse(restarted.resumed)
        self.assertIsNone(restarted.pending)
        self.assertNotEqual(
            restarted.graph_config["configurable"]["thread_id"],
            session.graph_config["configurable"]["thread_id"],
        )


if __name__ == "__main__":
    unittest.main()
