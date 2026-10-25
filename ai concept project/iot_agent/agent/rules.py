"""Deterministic fault-rule matching over structured memory.

`match_causes` maps confirmed evidence to candidate root causes (fed to the LLM
as hints). `escalation_triggers` implements the hard escalation rules R1-R4 of
taxonomy.yaml; the triage module uses them to override the LLM's tier.
"""
import yaml

import config
from agent.memory import SessionMemory

TAXONOMY = yaml.safe_load((config.DATA_DIR / "taxonomy.yaml").read_text(encoding="utf-8"))
CAUSES = TAXONOMY["root_causes"]
WEAK_RSSI = -80
LOW_BATTERY = 10


def _codes(m: SessionMemory):
    codes = set(m.base.get("error_codes", [])) if m.base else set()
    for lines in m.logs.values():
        for l in lines:
            for tok in l.replace(":", " ").split():
                if tok.startswith("E-") and tok[2:].isdigit():
                    codes.add(tok)
    return codes


def _bound_abnormal(m: SessionMemory):
    """Bound devices that are abnormal and NOT explained by a dead battery."""
    out = []
    for d in (m.topology or {}).get("devices", []):
        if d["status"] in ("online", "not_paired") or not d["bound_in_base"]:
            continue
        info = m.devices.get(d["id"], {})
        if info.get("battery") is not None and info["battery"] < LOW_BATTERY:
            continue
        out.append(d["id"])
    return out


def _failed_actions(m: SessionMemory, cause=None):
    return [a for a in m.actions if a["resolved"] is False and (cause is None or a["target_cause"] == cause)]


def match_causes(m: SessionMemory):
    """Return [{"cause", "tier", "evidence"}] supported by memory, strongest first."""
    hits = []

    def add(cause, evidence):
        hits.append({"cause": cause, "tier": CAUSES[cause]["tier"], "evidence": evidence})

    codes = _codes(m)
    bs = m.base or {}
    if m.base:
        if not bs["online"] or bs.get("uplink_status") == "no_internet":
            add("BS_NETWORK_DOWN", f"base online={bs['online']}, uplink={bs.get('uplink_status')}")
        if bs.get("storage_used_pct", 0) >= 98 and not bs.get("loop_recording", True):
            add("STORAGE_FULL", f"storage {bs['storage_used_pct']}%, loop recording off")
        if "E-503" in codes and bs["online"]:
            add("UPLINK_BLOCKED_PERSIST" if _failed_actions(m) else "BS_NETWORK_DOWN",
                "E-503 cloud reporting failure while base online")
    if m.topology:
        t = m.topology
        if t["bound_count"] >= t["max_devices"] or "E-201" in codes:
            add("CAPACITY_EXCEEDED", f"{t['bound_count']}/{t['max_devices']} slots used")
        mismatch = [d["id"] for d in t["devices"]
                    if d["bound_in_app"] != d["bound_in_base"] and d["status"] != "not_paired"]
        if mismatch or "E-207" in codes:
            add("BINDING_TABLE_CORRUPT", f"app/base binding mismatch: {mismatch or 'E-207 logged'}")
        unpaired = [d["id"] for d in t["devices"] if d["status"] == "not_paired"]
        if unpaired and t["bound_count"] < t["max_devices"] and "E-207" not in codes:
            add("PAIR_TIMEOUT", f"device(s) {unpaired} not paired while capacity is available")

    batch = _bound_abnormal(m)
    if len(batch) >= 2 or "E-610" in codes:
        add("BATCH_LINK_FAILURE", f"abnormal devices {batch}; codes {sorted(codes & {'E-610'})}")

    for dev_id, info in m.devices.items():
        if info["status"] == "online":
            continue
        if info.get("rssi") is not None and info["rssi"] < WEAK_RSSI and len(batch) <= 1:
            add("WEAK_SIGNAL", f"{dev_id} rssi {info['rssi']} dBm")
        if info.get("battery") is not None and info["battery"] < LOW_BATTERY:
            add("BATTERY_LOW", f"{dev_id} battery {info['battery']}%")

    for dev_id, c in m.compat.items():
        if c["compatible"]:
            continue
        ota_failed = any("ota" in a["action"].lower() or "firmware" in a["action"].lower()
                         or "upgrade" in a["action"].lower() for a in _failed_actions(m))
        if c["ota_available_to"] and not ota_failed:
            add("PERIPHERAL_FW_OUTDATED", f"{dev_id} protocol {c['device_protocol']} unsupported, OTA to {c['ota_available_to']} available")
        else:
            add("PROTOCOL_CONFLICT", f"{dev_id} protocol {c['device_protocol']} unsupported, "
                f"{'OTA failed' if ota_failed else 'no OTA path'}")
    return hits


def escalation_triggers(m: SessionMemory, diagnosed_cause=None):
    """Hard rules R1-R4. Returns [{"rule", "evidence"}]; any trigger forces L2."""
    trig = []
    batch = _bound_abnormal(m)
    bs = m.base or {}
    if len(batch) >= 2 and bs.get("online"):
        trig.append({"rule": "R1_BATCH", "evidence": f"{len(batch)} devices abnormal simultaneously: {batch}"})
    for dev_id, c in m.compat.items():
        if not c["compatible"]:
            ota_failed = any(a["target_cause"] == "PERIPHERAL_FW_OUTDATED" for a in _failed_actions(m))
            if not c["ota_available_to"] or ota_failed:
                trig.append({"rule": "R2_PROTOCOL", "evidence": f"{dev_id} incompatible and OTA "
                             f"{'failed' if ota_failed else 'unavailable'}"})
    if diagnosed_cause and CAUSES.get(diagnosed_cause, {}).get("tier") == "L1":
        failed = _failed_actions(m, diagnosed_cause)
        if failed and not any(a["resolved"] for a in m.actions if a["target_cause"] == diagnosed_cause):
            trig.append({"rule": "R3_FIX_FAILED", "evidence": f"standard fix for {diagnosed_cause} did not help: "
                         f"{failed[-1]['action']}"})
    if m.topology:
        mismatch = [d["id"] for d in m.topology["devices"]
                    if d["bound_in_app"] != d["bound_in_base"] and d["status"] != "not_paired"]
        if mismatch:
            trig.append({"rule": "R4_TOPOLOGY_MISMATCH", "evidence": f"app/base disagree on {mismatch}"})
    return trig
