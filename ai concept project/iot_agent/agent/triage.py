"""Dual-layer triage (frontline L1 vs FAE L2) and final output generation."""
import json

import config
import llm
from agent.memory import SessionMemory
from agent.rules import CAUSES, escalation_triggers

OUTPUT_PROMPT = """You are writing the final hand-off for a frontline support staff member (the reader is staff, not the
customer) at the end of a technical support session for a smart security system.
Diagnosed root cause: {cause} ({tier}).
Diagnosis rationale: {rationale}
Session memory (confirmed facts):
{memory}

{instruction}
Return JSON only."""

L1_INSTRUCTION = """The case can be closed by the frontline staff member without FAE. Return:
{"repair_steps": ["<short imperative step for the staff member to carry out or guide the customer through>", ...],
 "customer_reply": "<reply template the staff member can send to the customer, polite, max 80 words>"}"""

L2_INSTRUCTION = """The case must be escalated by the staff member to an FAE engineer. Return:
{"symptom_summary": "<1-2 sentences, written for the FAE>", "suspected_root_cause": "<1 sentence>",
 "key_abnormal_indicators": ["<value-level facts, e.g. rssi, fw, error codes>", ...],
 "customer_reply": "<reply template the staff member can send, telling the customer an engineer will follow up, max 60 words>"}"""


def classify_tier(m: SessionMemory, cause: str, use_override=True):
    """Tier from the taxonomy, overridden to L2 by any hard escalation rule."""
    base_tier = CAUSES.get(cause, {}).get("tier", "L2")   # unknown cause -> escalate (safe default)
    triggers = escalation_triggers(m, cause) if use_override else []
    tier = "L2" if triggers else base_tier
    return tier, triggers, tier != base_tier


def build_output(m: SessionMemory, cause, tier, rationale, triggers):
    instruction = L1_INSTRUCTION if tier == "L1" else L2_INSTRUCTION
    messages = [{"role": "user", "content": OUTPUT_PROMPT.format(
        cause=cause, tier=tier, rationale=rationale, memory=m.snapshot(), instruction=instruction)}]
    out = llm.chat_json(messages, model=config.OUTPUT_MODEL, role="agent")
    issue = validate_output(tier, out)
    if issue:
        retry_messages = [
            *messages,
            {"role": "assistant", "content": json.dumps(out, ensure_ascii=False)},
            {
                "role": "user",
                "content": (
                    f"Your output did not satisfy the required schema: {issue} "
                    "Return a corrected JSON object only."
                ),
            },
        ]
        out = llm.chat_json(
            retry_messages,
            model=config.OUTPUT_MODEL,
            role="agent",
            use_cache=False,
        )
        issue = validate_output(tier, out)
        if issue:
            raise ValueError(f"Model returned invalid {tier} output after retry: {issue}")
    if tier == "L2":
        # the deterministic part of the ticket comes straight from memory
        out["ticket"] = {
            "base_station": {k: m.base.get(k) for k in ("model", "fw", "online", "error_codes")} if m.base else None,
            "affected_devices": [m.devices[d] for d in m.abnormal_devices() if d in m.devices],
            "escalation_rules": triggers,
            "steps_performed": [f"{a['action']} -> {a['outcome']}" for a in m.actions],
        }
    return out


def validate_output(tier, result):
    if not isinstance(result, dict):
        return "Final output must be a JSON object."
    if not isinstance(result.get("customer_reply"), str) or not result["customer_reply"].strip():
        return "Final output must include a customer reply."
    if tier == "L1":
        if not isinstance(result.get("repair_steps"), list) or not result["repair_steps"] or not all(
            isinstance(step, str) and step.strip()
            for step in result["repair_steps"]
        ):
            return "L1 output must include one or more non-empty repair steps."
    else:
        for key in ("symptom_summary", "suspected_root_cause"):
            if not isinstance(result.get(key), str) or not result[key].strip():
                return f"L2 output must include a non-empty {key}."
        if not isinstance(result.get("key_abnormal_indicators"), list):
            return "L2 output must include key_abnormal_indicators as a list."
    return None
