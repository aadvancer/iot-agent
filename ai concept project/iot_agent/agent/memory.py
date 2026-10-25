"""Structured session memory.

Instead of relying on the raw chat transcript, the agent keeps confirmed facts in
typed slots. The slots drive (a) the planner's stage bookkeeping, (b) the rule
matcher and (c) the de-duplication guard that prevents re-querying known facts.
"""
import json

STAGES = {
    "S1": "base station status",
    "S2": "binding / capacity",
    "S3": "master-slave link quality",
    "S4": "firmware / protocol compatibility",
    "S5": "peripheral device itself",
}

NORMAL_STATUS = {"online"}


class SessionMemory:
    def __init__(self, complaint: str):
        self.complaint = complaint
        self.base = None          # result of get_base_status
        self.topology = None      # result of get_topology
        self.devices = {}         # device_id -> get_device_info result
        self.compat = {}          # device_id -> check_firmware_compat result
        self.logs = {}            # keyword -> log lines
        self.kb = []              # retrieved knowledge snippets (source, text)
        self.user_facts = []      # [{"question", "answer"}]
        self.actions = []         # [{"action", "target_cause", "outcome", "resolved"}]
        self.dedup_hits = 0       # repeated queries answered from memory

    # ---------- derived views ----------
    def abnormal_devices(self):
        """Devices whose status in the binding table is not normal."""
        if not self.topology:
            return []
        return [d["id"] for d in self.topology["devices"] if d["status"] not in NORMAL_STATUS]

    def stage_status(self):
        ab = self.abnormal_devices()
        return {
            "S1": self.base is not None,
            "S2": self.topology is not None,
            "S3": bool(ab) and all(d in self.devices for d in ab) and bool(self.logs),
            "S4": bool(ab) and all(d in self.compat for d in ab),
            "S5": bool(ab) and all(d in self.devices for d in ab),
        }

    # ---------- de-duplication guard ----------
    def lookup(self, tool: str, args: dict):
        """Return the remembered result if this exact query was already answered."""
        if tool == "get_base_status" and self.base is not None:
            return self.base
        if tool == "get_topology" and self.topology is not None:
            return self.topology
        if tool == "get_device_info" and args.get("device_id") in self.devices:
            return self.devices[args["device_id"]]
        if tool == "check_firmware_compat" and args.get("device_id") in self.compat:
            return self.compat[args["device_id"]]
        if tool == "get_logs" and (args.get("keyword", "") in self.logs or "" in self.logs):
            key = args.get("keyword", "")
            if key in self.logs:
                return {"lines": self.logs[key]}
            return {"lines": [l for l in self.logs[""] if key.lower() in l.lower()]}
        if tool == "ask_user":
            q = args.get("question", "").strip().lower()
            for f in self.user_facts:
                if f["question"].strip().lower() == q:
                    return {"answer": f["answer"]}
        return None

    # ---------- updates ----------
    def update(self, tool: str, args: dict, result: dict):
        if "error" in result:
            return
        if tool == "get_base_status":
            self.base = result
        elif tool == "get_topology":
            self.topology = result
        elif tool == "get_device_info":
            self.devices[result["id"]] = result
        elif tool == "check_firmware_compat":
            self.compat[result["device_id"]] = result
        elif tool == "get_logs":
            self.logs[args.get("keyword", "")] = result["lines"]
        elif tool == "search_kb":
            for r in result["results"]:
                if r["source"] not in {k["source"] for k in self.kb}:
                    self.kb.append(r)
        elif tool == "ask_user":
            self.user_facts.append({"question": args["question"], "answer": result["answer"]})

    def add_action(self, action, target_cause, outcome, resolved):
        self.actions.append({"action": action, "target_cause": target_cause,
                             "outcome": outcome, "resolved": resolved})

    # ---------- rendering for the LLM ----------
    def snapshot(self) -> str:
        view = {
            "stages_done": {k: f"{STAGES[k]}: {'done' if v else 'pending'}"
                            for k, v in self.stage_status().items()},
            "base_station": self.base,
            "binding_table": self.topology,
            "abnormal_devices": self.abnormal_devices(),
            "device_details": self.devices,
            "firmware_compat": self.compat,
            "logs": self.logs,
            "customer_answers": self.user_facts,
            "fix_attempts": self.actions,
            "knowledge_snippets": [f"[{k['source']}] {k['text']}" for k in self.kb],
        }
        return json.dumps(view, indent=1, ensure_ascii=False)
