"""Sanity checks: data files are consistent and the LLM endpoint works
(plain chat, JSON mode, tool calling). Run: python smoke_test.py"""
import json

import yaml

import config
import llm


def check_data():
    taxonomy = yaml.safe_load((config.DATA_DIR / "taxonomy.yaml").read_text(encoding="utf-8"))
    devices = yaml.safe_load((config.DATA_DIR / "devices.yaml").read_text(encoding="utf-8"))
    causes = taxonomy["root_causes"]
    models = set(devices["base_stations"]) | set(devices["peripherals"])
    cases = sorted(config.CASES_DIR.glob("*.json"))
    assert len(cases) >= 40, f"expected at least 40 dataset cases, found {len(cases)}"
    for p in cases:
        c = json.loads(p.read_text(encoding="utf-8"))
        assert c["gt_root_cause"] in causes, f"{p.name}: unknown root cause"
        assert causes[c["gt_root_cause"]]["tier"] == c["gt_tier"], f"{p.name}: tier mismatch"
        assert c["hidden_state"]["base_station"]["model"] in models, f"{p.name}: unknown base model"
        for d in c["hidden_state"]["devices"]:
            assert d["model"] in models, f"{p.name}: unknown device model {d['model']}"
    kb = list(config.KB_DIR.glob("*.md"))
    print(f"[data] {len(causes)} root causes, {len(cases)} cases, {len(kb)} KB docs - OK")


def check_llm(model):
    out = llm.chat([{"role": "user", "content": "Reply with exactly: pong"}], model=model, use_cache=False)
    print(f"[{model}] chat -> {out['content']!r} ({out['seconds']:.1f}s)")

    j = llm.chat_json([
        {"role": "system", "content": "Return a JSON object."},
        {"role": "user", "content": 'Return {"tier": "L1"} as JSON.'}], model=model, use_cache=False)
    print(f"[{model}] json -> {j}")

    tools = [{"type": "function", "function": {
        "name": "get_topology", "description": "List devices bound to the base station.",
        "parameters": {"type": "object", "properties": {}, "required": []}}}]
    out = llm.chat([{"role": "user", "content": "Which devices are bound to my base station? Use the tool."}],
                   model=model, tools=tools, use_cache=False)
    print(f"[{model}] tool call -> {[tc['name'] for tc in out['tool_calls']]}")


if __name__ == "__main__":
    check_data()
    for m in {config.AGENT_MODEL, config.USER_SIM_MODEL}:
        check_llm(m)
    print(f"[usage] {llm.USAGE.calls} calls, {llm.USAGE.prompt_tokens} prompt + "
          f"{llm.USAGE.completion_tokens} completion tokens")
