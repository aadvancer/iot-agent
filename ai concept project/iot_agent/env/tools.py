"""OpenAI-style tool schemas shared by the proposed agent and the ReAct baseline,
plus a dispatcher that executes a model tool call against a CaseEnv."""
import json

from env.case_env import CaseEnv
from env.knowledge_base import get_kb


def _fn(name, description, props=None, required=None):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": props or {}, "required": required or []}}}


_DEVICE_ID = {"device_id": {"type": "string", "description": "Device id from get_topology, e.g. 'cam_living'."}}

TOOL_SCHEMAS = [
    _fn("get_base_status", "Support console: base station model, firmware, online/uplink status, storage, "
        "active fault codes, capacity and supported radio protocols."),
    _fn("get_topology", "Support console: devices bound to the base station (binding table) vs. the app's "
        "device list, with current status of each device."),
    _fn("get_device_info", "Support console: firmware, signal strength (RSSI, dBm), battery and status of one device.",
        _DEVICE_ID, ["device_id"]),
    _fn("check_firmware_compat", "Check whether a device's firmware protocol is supported by the base station "
        "and whether an OTA upgrade path exists.", _DEVICE_ID, ["device_id"]),
    _fn("get_logs", "Base station event log lines, optionally filtered by a keyword (device id, error code).",
        {"keyword": {"type": "string"}}),
    _fn("search_kb", "Search manuals, fault code reference, escalation policy and historical cases.",
        {"query": {"type": "string"}}, ["query"]),
    _fn("ask_user", "Ask the customer a question about things only they can observe "
        "(LED colour, location, recent changes).", {"question": {"type": "string"}}, ["question"]),
    _fn("instruct_user", "Ask the customer to perform one troubleshooting/fix action and report the result.",
        {"action": {"type": "string"}}, ["action"]),
]


def execute(env: CaseEnv, name: str, arguments) -> dict:
    """Run one tool call; `arguments` may be a JSON string (from the model) or a dict."""
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else dict(arguments or {})
    except json.JSONDecodeError:
        return {"error": "arguments were not valid JSON"}

    if name == "search_kb":
        hits = get_kb().search(args.get("query", ""))
        result = {"results": [{"source": f"{h['doc']}#{h['title']}", "text": h["text"]} for h in hits]}
        env.trace.append({"tool": name, "args": args, "result": result})
        return result

    method = getattr(env, name, None) if name in {t["function"]["name"] for t in TOOL_SCHEMAS} else None
    if method is None:
        return {"error": f"unknown tool '{name}'"}
    try:
        return method(**args)
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}
