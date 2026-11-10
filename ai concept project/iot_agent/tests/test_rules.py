import unittest

from agent.memory import SessionMemory
from agent.rules import escalation_triggers, match_causes


def _two_offline(logs, codes=()):
    m = SessionMemory("Two sensors are offline.")
    m.base = {"online": True, "uplink_status": "ok", "error_codes": list(codes)}
    m.topology = {"bound_count": 2, "max_devices": 16, "devices": [
        {"id": dev, "status": "offline", "bound_in_base": True, "bound_in_app": True} for dev in ("a", "b")]}
    m.devices = {dev: {"id": dev, "status": "offline", "rssi": -60, "battery": 80} for dev in ("a", "b")}
    m.logs = {"": logs}
    return m


def _rules(m, cause=None):
    return [t["rule"] for t in escalation_triggers(m, cause)]


class BatchRuleTests(unittest.TestCase):
    def test_devices_lost_hours_apart_are_not_a_batch_failure(self):
        m = _two_offline(["02:14:51 a lost", "05:47:09 b lost"])
        self.assertNotIn("R1_BATCH", _rules(m))
        self.assertNotIn("BATCH_LINK_FAILURE", [h["cause"] for h in match_causes(m)])

    def test_devices_offline_without_loss_timestamps_are_not_a_batch_failure(self):
        self.assertNotIn("R1_BATCH", _rules(_two_offline(["a offline since yesterday"])))

    def test_devices_lost_within_the_window_escalate(self):
        m = _two_offline(["14:02:11 a lost", "14:02:12 b lost"])
        self.assertIn("R1_BATCH", _rules(m))
        self.assertIn("BATCH_LINK_FAILURE", [h["cause"] for h in match_causes(m)])

    def test_e610_counts_as_simultaneous_loss(self):
        self.assertIn("R1_BATCH", _rules(_two_offline(["E-610 radio module self-test warning"], ["E-610"])))


class FixFailedRuleTests(unittest.TestCase):
    def _after(self, standard_fix):
        m = SessionMemory("One camera keeps dropping.")
        m.add_action("Restart the camera.", "WEAK_SIGNAL", "Still offline.", False, standard_fix)
        return _rules(m, "WEAK_SIGNAL")

    def test_failed_non_standard_action_does_not_trigger_r3(self):
        self.assertEqual(self._after(False), [])

    def test_failed_standard_fix_triggers_r3(self):
        self.assertEqual(self._after(True), ["R3_FIX_FAILED"])

    def test_unknown_standard_fix_keeps_staff_reported_failures(self):
        self.assertEqual(self._after(None), ["R3_FIX_FAILED"])


class ProtocolRuleTests(unittest.TestCase):
    def _incompatible(self, logs):
        m = SessionMemory("Sensor stopped sending alerts after an update.")
        m.compat = {"s1": {"device_id": "s1", "compatible": False, "device_protocol": "v2",
                           "ota_available_to": "1.4"}}
        m.logs = {"": logs}
        return m

    def test_ota_path_without_failed_attempt_stays_frontline(self):
        m = self._incompatible(["s1: E-305 protocol v2 not supported"])
        self.assertEqual(_rules(m), [])
        self.assertEqual([h["cause"] for h in match_causes(m)], ["PERIPHERAL_FW_OUTDATED"])

    def test_logged_ota_failure_escalates_as_protocol_conflict(self):
        m = self._incompatible(["s1: OTA to 1.4 failed at 61% (image checksum mismatch)"])
        self.assertEqual(_rules(m), ["R2_PROTOCOL"])
        self.assertEqual([h["cause"] for h in match_causes(m)], ["PROTOCOL_CONFLICT"])


class HardwareRuleTests(unittest.TestCase):
    """R5 (policy rule 5): still failing next to the base station after a reset."""

    def _session(self, answers, failed=(), abnormal=True):
        m = SessionMemory("The garage camera is offline.")
        status = "offline" if abnormal else "online"
        m.topology = {"bound_count": 1, "max_devices": 8, "devices": [
            {"id": "cam", "status": status, "bound_in_base": True, "bound_in_app": True}]}
        m.devices = {"cam": {"id": "cam", "status": status, "rssi": -85, "battery": 90}}
        m.user_facts = [{"question": q, "answer": a} for q, a in answers]
        for action, outcome in failed:
            m.add_action(action, "WEAK_SIGNAL", outcome, False, True)
        return m

    def test_reset_and_next_to_base_with_offline_device_escalates(self):
        m = self._session([("Did you reset it?", "I held its reset button for 10 seconds."),
                           ("Where is it now?", "Right next to the base station.")])
        self.assertIn("R5_HW_PERSISTS", _rules(m, "WEAK_SIGNAL"))
        self.assertIn("HW_FAULT_SUSPECTED", [h["cause"] for h in match_causes(m)])

    def test_negated_reset_does_not_escalate(self):
        m = self._session([("Did you reset it?", "No, I have not reset it."),
                           ("Where is it?", "It is next to the base station.")])
        self.assertNotIn("R5_HW_PERSISTS", _rules(m))

    def test_without_proximity_test_does_not_escalate(self):
        m = self._session([("Did you reset it?", "Yes, I reset it yesterday.")])
        self.assertNotIn("R5_HW_PERSISTS", _rules(m))

    def test_recovered_device_needs_explicit_failure_report(self):
        answers = [("Reset?", "I reset it."), ("Where?", "Next to the base station.")]
        self.assertNotIn("R5_HW_PERSISTS", _rules(self._session(answers, abnormal=False)))
        failed = [("Move it next to the base.", "It is next to the base station and still offline.")]
        self.assertIn("R5_HW_PERSISTS", _rules(self._session(answers, failed, abnormal=False)))


class HardwareRuleDatasetTests(unittest.TestCase):
    """Worst case: every customer fact is asked and every scripted action reported as failed."""

    @staticmethod
    def _worst_case_memory(case):
        from env.case_env import CaseEnv

        env = CaseEnv(case)
        m = SessionMemory(case["complaint"])
        m.update("get_topology", {}, env.get_topology())
        for d in case["hidden_state"]["devices"]:
            m.update("get_device_info", {"device_id": d["id"]}, env.get_device_info(d["id"]))
        m.user_facts = [{"question": k.replace("_", " "), "answer": str(v)}
                        for k, v in case["user_knowledge"].items()]
        for action, outcome in case["action_outcomes"].items():
            m.add_action(action.replace("_", " "), None, str(outcome), False, None)
        return m

    def test_r5_never_fires_on_frontline_cases_and_flags_dialogue_hardware_cases(self):
        import json

        import config

        fired = set()
        for path in sorted(config.CASES_DIR.glob("C*.json")):
            case = json.loads(path.read_text(encoding="utf-8"))
            if "R5_HW_PERSISTS" in _rules(self._worst_case_memory(case)):
                fired.add(case["case_id"])
                self.assertEqual(case["gt_tier"], "L2", case["case_id"])
        self.assertTrue({"C038", "C039", "C040", "C041", "C050"} <= fired, fired)


if __name__ == "__main__":
    unittest.main()
