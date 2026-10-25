"""Simulated support environment for one fault case.

The case's `hidden_state` plays the role of the vendor's support console
(what frontline staff can look up), while the simulated user owns everything
that only the customer knows or can physically do. Every interaction is
appended to `self.trace`, which the evaluator later uses to compute metrics.
"""
import json

import yaml

import config
from env.user_simulator import UserSimulator

_CATALOG = None


def catalog() -> dict:
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = yaml.safe_load((config.DATA_DIR / "devices.yaml").read_text(encoding="utf-8"))
    return _CATALOG


def load_case(case_id: str) -> dict:
    return json.loads((config.CASES_DIR / f"{case_id}.json").read_text(encoding="utf-8"))


class CaseEnv:
    def __init__(self, case: dict):
        self.case = case
        self.state = case["hidden_state"]
        self.user = UserSimulator(case)
        self.trace = []            # list of {"tool", "args", "result"}
        self.actions_done = []     # fixes the customer was asked to perform

    # ---------- helpers ----------
    def _base_spec(self):
        bs = self.state["base_station"]
        spec = catalog()["base_stations"][bs["model"]]
        return spec, spec["firmware"][bs["fw"]]["protocol"]

    def _device(self, device_id):
        for d in self.state["devices"]:
            if d["id"] == device_id:
                return d
        return None

    def _log(self, tool, args, result):
        self.trace.append({"tool": tool, "args": args, "result": result})
        return result

    # ---------- console tools (S1-S5 evidence) ----------
    def get_base_status(self):
        """S1: base station health, uplink, storage and active fault codes."""
        bs = self.state["base_station"]
        spec, protocols = self._base_spec()
        result = {**bs, "max_devices": spec["max_devices"], "supported_protocols": protocols}
        return self._log("get_base_status", {}, result)

    def get_topology(self):
        """S2: binding table of the base station vs. device list in the app."""
        devs = self.state["devices"]
        spec, _ = self._base_spec()
        result = {
            "bound_count": sum(d["bound_in_base"] for d in devs),
            "max_devices": spec["max_devices"],
            "devices": [{k: d[k] for k in ("id", "name", "model", "bound_in_base", "bound_in_app", "status")}
                        for d in devs],
        }
        return self._log("get_topology", {}, result)

    def get_device_info(self, device_id: str):
        """S3/S5: per-device link quality, battery, firmware."""
        d = self._device(device_id)
        if d is None:
            result = {"error": f"unknown device_id '{device_id}'"}
        else:
            result = {k: d[k] for k in ("id", "name", "model", "fw", "rssi", "battery", "status")}
        return self._log("get_device_info", {"device_id": device_id}, result)

    def check_firmware_compat(self, device_id: str):
        """S4: does the peripheral's protocol match the base station, and can OTA fix it?"""
        d = self._device(device_id)
        if d is None:
            return self._log("check_firmware_compat", {"device_id": device_id},
                             {"error": f"unknown device_id '{device_id}'"})
        _, base_protocols = self._base_spec()
        fw_spec = catalog()["peripherals"][d["model"]]["firmware"][d["fw"]]
        compatible = fw_spec["protocol"] in base_protocols
        result = {
            "device_id": device_id, "device_fw": d["fw"], "device_protocol": fw_spec["protocol"],
            "base_protocols": base_protocols, "compatible": compatible,
            "ota_available_to": None if compatible else fw_spec.get("ota_to"),
        }
        return self._log("check_firmware_compat", {"device_id": device_id}, result)

    def get_logs(self, keyword: str = ""):
        """Base station event log, optionally filtered by keyword (device id, error code...)."""
        lines = [l for l in self.state["logs"] if keyword.lower() in l.lower()]
        return self._log("get_logs", {"keyword": keyword}, {"lines": lines})

    # ---------- customer interaction ----------
    def ask_user(self, question: str):
        answer = self.user.answer(question)
        return self._log("ask_user", {"question": question}, {"answer": answer})

    def instruct_user(self, action: str):
        """Ask the customer to perform a fix and report what happened."""
        self.actions_done.append(action)
        outcome = self.user.perform(action)
        return self._log("instruct_user", {"action": action}, {"outcome": outcome})
