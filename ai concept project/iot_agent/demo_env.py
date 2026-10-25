"""Scripted walk-through of the environment on one case (no agent yet).
Usage: python demo_env.py [CASE_ID]   (default C001)"""
import json
import sys

import llm
from env.case_env import CaseEnv, load_case
from env.tools import execute


def show(title, obj):
    print(f"\n### {title}")
    print(json.dumps(obj, indent=2, ensure_ascii=False) if not isinstance(obj, str) else obj)


def main(case_id):
    case = load_case(case_id)
    env = CaseEnv(case)
    show("Complaint", case["complaint"])

    # console tools, called through the same dispatcher the agent will use
    show("get_base_status", execute(env, "get_base_status", "{}"))
    show("get_topology", execute(env, "get_topology", "{}"))
    first = case["hidden_state"]["devices"][0]["id"]
    show(f"get_device_info({first})", execute(env, "get_device_info", {"device_id": first}))
    show(f"check_firmware_compat({first})", execute(env, "check_firmware_compat", {"device_id": first}))
    show(f"get_logs({first})", execute(env, "get_logs", {"keyword": first}))
    show("unknown device (error path)", execute(env, "get_device_info", {"device_id": "nope"}))

    # retrieval
    show("search_kb('camera intermittently offline weak signal')",
         execute(env, "search_kb", {"query": "camera intermittently offline weak signal"}))

    # simulated user: in-knowledge, out-of-knowledge, leading question
    for q in ["Where is the base station compared to the camera? Did anything change recently?",
              "What is the RSSI value of the camera?",
              "What do you think is causing the problem?"]:
        show(f"ask_user: {q}", execute(env, "ask_user", {"question": q}))

    # simulated user performing fixes: matching and non-matching actions
    for a in ["Please restart the base station with a short press of the rear button.",
              "Please move the base station back to the hallway, closer to the camera.",
              "Please clean the camera lens."]:
        show(f"instruct_user: {a}", execute(env, "instruct_user", {"action": a}))

    print(f"\n[trace] {len(env.trace)} steps: {[t['tool'] for t in env.trace]}")
    print(f"[usage] {llm.USAGE.calls} LLM calls, {llm.USAGE.prompt_tokens}+{llm.USAGE.completion_tokens} tokens")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "C001")
