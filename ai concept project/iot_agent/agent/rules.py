"""Deterministic fault-rule matching over structured memory.

`match_causes` maps confirmed evidence to candidate root causes (fed to the LLM
as hints). `escalation_triggers` implements the hard escalation rules R1-R5 of
taxonomy.yaml; the triage module uses them to override the LLM's tier.
"""
import re

import yaml

import config
from agent.memory import SessionMemory

TAXONOMY = yaml.safe_load((config.DATA_DIR / "taxonomy.yaml").read_text(encoding="utf-8"))
CAUSES = TAXONOMY["root_causes"]
WEAK_RSSI = -80
LOW_BATTERY = 10
SIMULTANEOUS_WINDOW_S = 300   # device losses within 5 min count as "at the same time" (policy L2 rule 1)
_LOSS_LINE = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2})\s+(\S+)\s+lost\b")
_OTA_FAILED = re.compile(r"\bOTA\b.*\bfail", re.IGNORECASE)
# policy L2 rule 5 is only observable in the customer's own words, so it is matched on
# customer answers / failed-action reports, clause by clause, and kept deliberately strict
_RESET = re.compile(r"\breset\b", re.IGNORECASE)
_NEGATION = re.compile(r"\b(not|never|no|haven't|hasn't|didn't|won't)\b|n't\b", re.IGNORECASE)
_NEAR_BASE = re.compile(r"\b(next to|beside|right by)\b[^.;]{0,30}\bbase\b", re.IGNORECASE)
_STILL_FAILING = re.compile(r"\b(still|again)\b[^.]{0,30}\b(offline|fail\w*|not|no|drops?|disconnect\w*)\b",
                            re.IGNORECASE)


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


def _loss_times(m: SessionMemory):
    """device_id -> seconds of day of its logged "<hh:mm:ss> <device> lost" events."""
    times = {}
    for lines in m.logs.values():
        for line in lines:
            hit = _LOSS_LINE.match(line.strip())
            if hit:
                h, mi, sec, dev = hit.groups()
                times.setdefault(dev, []).append(int(h) * 3600 + int(mi) * 60 + int(sec))
    return times


def _simultaneous_batch(m: SessionMemory):
    """Abnormal bound devices that demonstrably failed at the same time.

    Evidence is either E-610 (logged by the base when several peripherals drop at once)
    or loss events of two or more of them within SIMULTANEOUS_WINDOW_S. Devices that are
    merely offline together, without such evidence, are not treated as a batch failure.
    """
    batch = _bound_abnormal(m)
    if len(batch) < 2:
        return []
    if "E-610" in _codes(m):
        return batch
    events = sorted((t, dev) for dev, ts in _loss_times(m).items() if dev in batch for t in ts)
    best = []
    for i, (start, _) in enumerate(events):
        group = {dev for t, dev in events[i:] if t - start <= SIMULTANEOUS_WINDOW_S}
        if len(group) > len(best):
            best = sorted(group)
    return best if len(best) >= 2 else []


def _ota_failed(m: SessionMemory, dev_id):
    """Policy L2 rule 2: an OTA attempt failed, either as a guided fix or as logged by the base."""
    if any(a["target_cause"] == "PERIPHERAL_FW_OUTDATED" or "ota" in a["action"].lower()
           or "firmware" in a["action"].lower() or "upgrade" in a["action"].lower()
           for a in _failed_actions(m)):
        return True
    return any(dev_id in line and _OTA_FAILED.search(line) for lines in m.logs.values() for line in lines)


def _failed_actions(m: SessionMemory, cause=None):
    """Failed standard fixes. Actions judged not to be the standard fix (diagnostic tests,
    unrelated restarts) do not count; unknown (None, e.g. staff-entered verdicts) does."""
    return [a for a in m.actions if a["resolved"] is False and a.get("standard_fix") is not False
            and (cause is None or a["target_cause"] == cause)]


def _customer_reports(m: SessionMemory, with_question=True):
    """What the customer said in this session: answers (optionally with their question) and failed-fix reports."""
    texts = [f"{f['question']} {f['answer']}" if with_question else f["answer"] for f in m.user_facts]
    texts += [f"{a['action']}: {a['outcome']}" if with_question else a["outcome"]
              for a in m.actions if a["resolved"] is False]
    return texts


def _clauses(text):
    return [c.strip() for c in re.split(r"[.;!?]", text) if c.strip()]


def _fails_near_base_after_reset(m: SessionMemory):
    """Policy L2 rule 5: the device still fails next to the base station after a reset.

    Needs (a) a non-negated reset reported by the customer, (b) the customer placing the
    device next to the base, and (c) evidence that it still fails there: either the customer
    says so, or a bound device is still abnormal on the console. The reset must come from the
    customer's own words (a question that mentions a reset is not evidence). Returns evidence or None.
    """
    reports = _customer_reports(m)
    clauses = [c for t in _customer_reports(m, with_question=False) for c in _clauses(t)]
    reset = next((c for c in clauses if _RESET.search(c) and not _NEGATION.search(c)), None)
    if reset is None:
        return None
    near_fail = next((t for t in reports if _NEAR_BASE.search(t) and _STILL_FAILING.search(t)), None)
    near = near_fail or next((t for t in reports if _NEAR_BASE.search(t)), None)
    if near is None or not (near_fail or _bound_abnormal(m)):
        return None
    return f"customer: '{reset}' / '{near.strip()[:120]}'"


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
        mismatch = [d["id"] for d in t["devices"]
                    if d["bound_in_app"] != d["bound_in_base"] and d["status"] != "not_paired"]
        # a full table that the app does not agree with is explained by the ghost binding,
        # so the more specific mismatch hint goes first
        if mismatch or "E-207" in codes:
            add("BINDING_TABLE_CORRUPT", f"app/base binding mismatch: {mismatch or 'E-207 logged'}")
        if t["bound_count"] >= t["max_devices"] or "E-201" in codes:
            add("CAPACITY_EXCEEDED", f"{t['bound_count']}/{t['max_devices']} slots used")
        unpaired = [d["id"] for d in t["devices"] if d["status"] == "not_paired"]
        if unpaired and t["bound_count"] < t["max_devices"] and "E-207" not in codes:
            add("PAIR_TIMEOUT", f"device(s) {unpaired} not paired while capacity is available")

    batch = _simultaneous_batch(m)
    if batch or "E-610" in codes:
        add("BATCH_LINK_FAILURE", f"devices failed together {batch}; codes {sorted(codes & {'E-610'})}")

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
        ota_failed = _ota_failed(m, dev_id)
        if c["ota_available_to"] and not ota_failed:
            add("PERIPHERAL_FW_OUTDATED", f"{dev_id} protocol {c['device_protocol']} unsupported, OTA to {c['ota_available_to']} available")
        else:
            add("PROTOCOL_CONFLICT", f"{dev_id} protocol {c['device_protocol']} unsupported, "
                f"{'OTA failed' if ota_failed else 'no OTA path'}")

    hw = _fails_near_base_after_reset(m)
    if hw:
        add("HW_FAULT_SUSPECTED", f"still fails next to the base after a reset ({hw})")
    return hits


def escalation_triggers(m: SessionMemory, diagnosed_cause=None):
    """Hard rules R1-R5. Returns [{"rule", "evidence"}]; any trigger forces L2."""
    trig = []
    batch = _simultaneous_batch(m)
    bs = m.base or {}
    if batch and bs.get("online"):
        trig.append({"rule": "R1_BATCH", "evidence": f"{len(batch)} devices failed simultaneously: {batch}"})
    for dev_id, c in m.compat.items():
        if not c["compatible"]:
            ota_failed = _ota_failed(m, dev_id)
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
    hw = _fails_near_base_after_reset(m)
    if hw:
        trig.append({"rule": "R5_HW_PERSISTS", "evidence": hw})
    return trig
