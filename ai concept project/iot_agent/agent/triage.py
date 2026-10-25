"""Dual-layer triage (frontline L1 vs FAE L2) and final output generation."""
import json

import config
import llm
from agent.memory import SessionMemory
from agent.rules import CAUSES, escalation_triggers

OUTPUT_PROMPT = """You are writing the final output of a technical support session for a smart security system.
Diagnosed root cause: {cause} ({tier}).
Diagnosis rationale: {rationale}
Session memory (confirmed facts):
{memory}

{instruction}
Return JSON only."""

L1_INSTRUCTION = """The case is resolved at frontline. Return:
{"repair_steps": ["<short imperative step>", ...], "customer_reply": "<polite reply to the customer, max 80 words>"}"""

L2_INSTRUCTION = """The case must be escalated to an FAE engineer. Return:
{"symptom_summary": "<1-2 sentences>", "suspected_root_cause": "<1 sentence>",
 "key_abnormal_indicators": ["<value-level facts, e.g. rssi, fw, error codes>", ...],
 "customer_reply": "<polite reply telling the customer an engineer will follow up, max 60 words>"}"""


def classify_tier(m: SessionMemory, cause: str):
    """Tier from the taxonomy, overridden to L2 by any hard escalation rule."""
    base_tier = CAUSES.get(cause, {}).get("tier", "L2")   # unknown cause -> escalate (safe default)
    triggers = escalation_triggers(m, cause)
    tier = "L2" if triggers else base_tier
    return tier, triggers, tier != base_tier


def build_output(m: SessionMemory, cause, tier, rationale, triggers):
    instruction = L1_INSTRUCTION if tier == "L1" else L2_INSTRUCTION
    out = llm.chat_json([{"role": "user", "content": OUTPUT_PROMPT.format(
        cause=cause, tier=tier, rationale=rationale, memory=m.snapshot(), instruction=instruction)}],
        model=config.AGENT_MODEL, role="agent")
    if tier == "L2":
        # the deterministic part of the ticket comes straight from memory
        out["ticket"] = {
            "base_station": {k: m.base.get(k) for k in ("model", "fw", "online", "error_codes")} if m.base else None,
            "affected_devices": [m.devices[d] for d in m.abnormal_devices() if d in m.devices],
            "escalation_rules": triggers,
            "steps_performed": [f"{a['action']} -> {a['outcome']}" for a in m.actions],
        }
    return out
