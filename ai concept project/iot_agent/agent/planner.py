"""Topology-aware evidence planner.

Walks the master-slave hierarchy in maintenance order
    S1 base station -> S2 binding/capacity -> S3 link quality -> S4 firmware/protocol -> S5 peripheral
and returns the next console query whose answer is not yet in memory.
Topology awareness means pruning checks that the hierarchy makes uninformative:
  * if the base station (master) is down, peripheral states only mirror that
    failure, so per-device stages S3-S5 are skipped;
  * only devices that are abnormal in the binding table are inspected, and
    unpaired devices skip link/firmware checks (they have no link yet).
These queries need no LLM call; the LLM only reasons over the collected evidence.
"""
from agent.memory import SessionMemory

MAX_DEVICES_INSPECTED = 5


def master_down(m: SessionMemory) -> bool:
    return m.base is not None and (not m.base["online"] or m.base.get("uplink_status") == "no_internet")


def next_query(m: SessionMemory):
    """Return (tool, args, stage) for the next evidence query, or None when done."""
    if m.base is None:
        return "get_base_status", {}, "S1"
    if master_down(m):
        return None
    if m.topology is None:
        return "get_topology", {}, "S2"

    status = {d["id"]: d["status"] for d in m.topology["devices"]}
    targets = [d for d in m.abnormal_devices() if status[d] != "not_paired"][:MAX_DEVICES_INSPECTED]
    for dev in targets:                                   # S3 + S5: link quality, battery
        if dev not in m.devices:
            return "get_device_info", {"device_id": dev}, "S3"
    if targets and "" not in m.logs:                      # S3: base station log
        return "get_logs", {"keyword": ""}, "S3"
    for dev in targets:                                   # S4: protocol compatibility
        if dev not in m.compat:
            return "check_firmware_compat", {"device_id": dev}, "S4"
    return None


def skipped_stages(m: SessionMemory):
    if master_down(m):
        return {"S2": "master down", "S3": "master down", "S4": "master down", "S5": "master down"}
    return {}
