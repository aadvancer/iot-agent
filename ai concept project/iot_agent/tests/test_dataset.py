import json
import unittest
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = PROJECT_ROOT / "data" / "cases"
TAXONOMY_PATH = PROJECT_ROOT / "data" / "taxonomy.yaml"


class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.causes = yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))["root_causes"]
        cls.devices = yaml.safe_load(
            (PROJECT_ROOT / "data" / "devices.yaml").read_text(encoding="utf-8")
        )
        cls.cases = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(CASES_DIR.glob("C*.json"))
        ]

    def test_dataset_has_core_and_challenge_splits(self):
        ids = [case["case_id"] for case in self.cases]
        self.assertEqual(ids, [f"C{i:03d}" for i in range(1, 53)])
        splits = {case["case_id"]: case.get("split", "core") for case in self.cases}
        self.assertEqual([i for i, s in splits.items() if s == "core"],
                         [f"C{i:03d}" for i in range(1, 41)])
        self.assertEqual([i for i, s in splits.items() if s == "challenge"],
                         [f"C{i:03d}" for i in range(41, 53)])

    def test_challenge_cases_declare_whether_dialogue_is_required(self):
        challenge = [case for case in self.cases if case.get("split") == "challenge"]
        for case in challenge:
            with self.subTest(case=case["case_id"]):
                self.assertIsInstance(case["requires_interaction"], bool)
                self.assertTrue(case["notes"])
        self.assertTrue(any(case["requires_interaction"] for case in challenge))
        self.assertTrue(any(not case["requires_interaction"] for case in challenge))

    def test_each_case_matches_the_taxonomy_and_has_simulation_fields(self):
        for case in self.cases:
            with self.subTest(case=case["case_id"]):
                cause = case["gt_root_cause"]
                self.assertIn(cause, self.causes)
                self.assertEqual(case["gt_tier"], self.causes[cause]["tier"])
                self.assertTrue(case["complaint"])
                self.assertTrue(case["hidden_state"]["base_station"])
                self.assertIsInstance(case["hidden_state"]["devices"], list)
                self.assertIsInstance(case["hidden_state"]["logs"], list)
                self.assertIsInstance(case["user_knowledge"], dict)
                self.assertIsInstance(case["action_outcomes"], dict)
                self.assertTrue(case["gt_key_checks"])

    def test_expanded_set_covers_every_taxonomy_cause(self):
        covered = {case["gt_root_cause"] for case in self.cases}
        self.assertEqual(covered, set(self.causes))

    def test_each_label_is_supported_by_its_case_evidence(self):
        for case in self.cases:
            with self.subTest(case=case["case_id"], cause=case["gt_root_cause"]):
                cause = case["gt_root_cause"]
                state = case["hidden_state"]
                base = state["base_station"]
                peripherals = state["devices"]
                if cause == "BS_NETWORK_DOWN":
                    self.assertFalse(base["online"])
                    self.assertEqual(base["uplink_status"], "no_internet")
                elif cause == "PAIR_TIMEOUT":
                    pending = [device for device in peripherals if device["status"] == "not_paired"]
                    self.assertTrue(pending)
                    self.assertLess(sum(device["bound_in_base"] for device in peripherals),
                                    self.devices["base_stations"][base["model"]]["max_devices"])
                elif cause == "CAPACITY_EXCEEDED":
                    self.assertGreaterEqual(
                        sum(device["bound_in_base"] for device in peripherals),
                        self.devices["base_stations"][base["model"]]["max_devices"],
                    )
                elif cause == "WEAK_SIGNAL":
                    weak = [device for device in peripherals
                            if device["status"] != "online" and device["rssi"] is not None
                            and device["rssi"] < -80]
                    self.assertEqual(len(weak), 1)
                elif cause == "BATTERY_LOW":
                    self.assertTrue(any(
                        device["status"] != "online" and device["battery"] is not None
                        and device["battery"] < 10 for device in peripherals
                    ))
                elif cause in ("PERIPHERAL_FW_OUTDATED", "PROTOCOL_CONFLICT"):
                    incompatible = []
                    base_protocols = self.devices["base_stations"][base["model"]]["firmware"][
                        base["fw"]
                    ]["protocol"]
                    for device in peripherals:
                        if device["status"] == "online":
                            continue
                        firmware = self.devices["peripherals"][device["model"]]["firmware"][
                            device["fw"]
                        ]
                        if firmware["protocol"] not in base_protocols:
                            incompatible.append(firmware.get("ota_to"))
                    self.assertTrue(incompatible)
                    if cause == "PERIPHERAL_FW_OUTDATED":
                        self.assertTrue(any(incompatible))
                    else:
                        # taxonomy: no OTA path, or the available OTA fails
                        ota_outcome = case["action_outcomes"].get("ota_upgrade", "").lower()
                        self.assertTrue(all(path is None for path in incompatible)
                                        or "fail" in ota_outcome)
                elif cause == "STORAGE_FULL":
                    self.assertGreaterEqual(base["storage_used_pct"], 98)
                    self.assertFalse(base["loop_recording"])
                elif cause == "BATCH_LINK_FAILURE":
                    abnormal = [device for device in peripherals if device["status"] != "online"]
                    self.assertTrue(base["online"])
                    self.assertGreaterEqual(len(abnormal), 2)
                    self.assertIn("E-610", base["error_codes"])
                elif cause == "UPLINK_BLOCKED_PERSIST":
                    self.assertTrue(base["online"])
                    self.assertIn("E-503", base["error_codes"])
                    self.assertIn("reset_router_dns", case["action_outcomes"])
                elif cause == "BINDING_TABLE_CORRUPT":
                    self.assertTrue(any(
                        device["bound_in_app"] != device["bound_in_base"]
                        for device in peripherals
                    ))
                elif cause == "HW_FAULT_SUSPECTED":
                    self.assertEqual(case["user_knowledge"]["device_location"],
                                     "next to the base station")
                    self.assertIn("reset_performed", case["user_knowledge"])


    def test_cases_are_not_trivial(self):
        for case in self.cases:
            with self.subTest(case=case["case_id"]):
                state = case["hidden_state"]
                self.assertGreaterEqual(len(case["complaint"]), 200)
                self.assertGreaterEqual(len(state["devices"]), 5)
                self.assertGreaterEqual(len(state["logs"]), 4)
                self.assertGreaterEqual(len(case["user_knowledge"]), 3)
                self.assertGreaterEqual(len(case["action_outcomes"]), 3)

    def test_customer_app_view_hides_deleted_devices(self):
        from env.user_simulator import UserSimulator

        case = next(c for c in self.cases if c["case_id"] == "C045")
        system = UserSimulator(case).system
        self.assertNotIn('"Sensor 7"', system)          # ghost binding, deleted in the app
        self.assertIn('"New Garage Door"', system)      # being paired by the customer
        self.assertIn('"Front Door"', system)

    def test_distractors_do_not_change_rule_evidence(self):
        from agent import planner
        from agent.memory import SessionMemory
        from agent.rules import escalation_triggers, match_causes
        from env.case_env import CaseEnv
        from env.tools import execute

        # these causes are only confirmed after a failed fix or by the LLM, not by console evidence
        needs_dialogue = {"UPLINK_BLOCKED_PERSIST", "HW_FAULT_SUSPECTED"}
        for case in self.cases:
            with self.subTest(case=case["case_id"]):
                env = CaseEnv(case)
                memory = SessionMemory(case["complaint"])
                while (query := planner.next_query(memory)) is not None:
                    tool, args, _ = query
                    memory.update(tool, args, execute(env, tool, args))
                abnormal = {d["id"] for d in case["hidden_state"]["devices"]
                            if d["status"] != "online"}
                self.assertLessEqual(set(memory.devices), abnormal)
                # challenge cases flagged requires_interaction deliberately carry stale console readings
                if (case["gt_root_cause"] not in needs_dialogue
                        and not case.get("requires_interaction", False)):
                    hints = {hint["cause"] for hint in match_causes(memory)}
                    self.assertIn(case["gt_root_cause"], hints)
                if case["gt_tier"] == "L1" and not case.get("requires_interaction", False):
                    self.assertEqual(escalation_triggers(memory, case["gt_root_cause"]), [])


if __name__ == "__main__":
    unittest.main()
