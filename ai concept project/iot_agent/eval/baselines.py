"""Vanilla LLM and retrieval-only baselines for controlled comparison."""
import json

import config
import llm
from agent.rules import CAUSES


def _cause_catalog():
    return "\n".join(
        f"- {name} ({item['tier']}): {', '.join(item['symptoms'])}"
        for name, item in CAUSES.items()
    )


def _diagnose(env, retrieved=None):
    context = ""
    if retrieved is not None:
        context = "\nRetrieved knowledge snippets:\n" + json.dumps(
            retrieved, ensure_ascii=False, indent=2
        )
    prompt = f"""Diagnose this smart-security support complaint using only the information below.
Do not claim to have inspected devices or performed troubleshooting; no support tools are available.
Choose exactly one root-cause label and an L1 or L2 tier. Return JSON with:
root_cause, tier, rationale, customer_reply, repair_steps (array),
symptom_summary, suspected_root_cause, key_abnormal_indicators (array).

Available root-cause labels:
{_cause_catalog()}

Customer complaint:
{env.case['complaint']}
{context}"""
    result = llm.chat_json(
        [{"role": "user", "content": prompt}],
        model=config.AGENT_MODEL,
        role="baseline",
    )
    cause = result.get("root_cause")
    tier = result.get("tier")
    if cause not in CAUSES:
        raise ValueError(f"Baseline returned unknown root cause: {cause!r}")
    if tier not in ("L1", "L2"):
        raise ValueError(f"Baseline returned invalid tier: {tier!r}")

    if tier == "L1":
        output = {
            "repair_steps": result.get("repair_steps", []),
            "customer_reply": result.get("customer_reply", ""),
        }
    else:
        output = {
            "symptom_summary": result.get("symptom_summary", ""),
            "suspected_root_cause": result.get("suspected_root_cause", ""),
            "key_abnormal_indicators": result.get("key_abnormal_indicators", []),
            "customer_reply": result.get("customer_reply", ""),
        }
    return {
        "system": "vanilla_rag" if retrieved is not None else "vanilla_llm",
        "case_id": env.case["case_id"],
        "pred_root_cause": cause,
        "pred_tier": tier,
        "tier_overridden": False,
        "triggers": [],
        "rationale": result.get("rationale", ""),
        "output": output,
        "rule_hints": [],
        "log": [],
        "trace": env.trace,
        "dedup_hits": 0,
        "memory": {},
    }


class VanillaLLM:
    """Direct classification from the complaint, without retrieval or tools."""

    name = "vanilla_llm"

    def run(self, env):
        return _diagnose(env)


class VanillaRAG:
    """Direct classification augmented only with retrieved KB snippets."""

    name = "vanilla_rag"

    def run(self, env):
        from env.knowledge_base import get_kb

        snippets = get_kb().search(env.case["complaint"])
        return _diagnose(env, retrieved=[
            {"source": f"{item['doc']}#{item['title']}", "text": item["text"]}
            for item in snippets
        ])


class RulesOnly:
    """Ablation: the agent's deterministic parts alone, with zero LLM calls.

    Runs the topology planner to collect console evidence, takes the strongest
    rule-matched cause (HW_FAULT_SUSPECTED if no rule fires) and applies the
    hard escalation rules. It never asks the customer or tries a fix, so it
    measures how much of the result the hand-written rules explain by themselves.
    """

    name = "rules_only"

    def run(self, env):
        from agent import planner
        from agent.memory import SessionMemory
        from agent.rules import match_causes
        from agent.triage import classify_tier
        from env.tools import execute

        memory = SessionMemory(env.case["complaint"])
        log = []
        while (query := planner.next_query(memory)) is not None:
            tool, args, stage = query
            memory.update(tool, args, execute(env, tool, args))
            log.append({"phase": "collect", "stage": stage, "tool": tool, "args": args})
        hints = match_causes(memory)
        cause = hints[0]["cause"] if hints else "HW_FAULT_SUSPECTED"
        tier, triggers, overridden = classify_tier(memory, cause)
        evidence = [h["evidence"] for h in hints if h["cause"] == cause]
        rationale = "; ".join(evidence) or "No rule matched; default to suspected hardware fault."
        spec = CAUSES[cause]
        if tier == "L1":
            output = {"repair_steps": [spec.get("resolution", "")],
                      "customer_reply": "We have identified the likely cause and will guide you through the fix."}
        else:
            output = {"symptom_summary": env.case["complaint"],
                      "suspected_root_cause": spec.get("escalation_reason", cause),
                      "key_abnormal_indicators": evidence,
                      "customer_reply": "We have escalated your case to an engineer who will follow up."}
        return {
            "system": self.name, "case_id": env.case["case_id"],
            "pred_root_cause": cause, "pred_tier": tier, "tier_overridden": overridden,
            "triggers": triggers, "rationale": rationale, "output": output,
            "rule_hints": hints, "log": log, "trace": env.trace, "dedup_hits": 0,
            "memory": json.loads(memory.snapshot()),
        }


REACT_SYSTEM = """You are a frontline technical-support diagnostic agent for a gateway-centric smart security system
(one base station = master; cameras and sensors = slaves that can only talk through the base station).
Use the tools to investigate: support-console queries, knowledge-base search, questions to the customer
(ask_user) and fix actions for the customer to perform (instruct_user). Find the root cause, then call
submit_diagnosis with the root-cause label and the tier: L1 = frontline can resolve, L2 = escalate to an FAE engineer.
Do not instruct base-station factory resets or firmware downgrades. Budget: {budget} tool calls.

Root-cause labels (tier):
{labels}"""


class ReActAgent:
    """Baseline: a standard ReAct tool-use loop over the same tools as the proposed agent.

    Differences from TopologyAgent (the controlled variables): no topology-ordered evidence
    planner, no structured memory snapshot (the model reads the raw growing transcript),
    no rule-matcher hints, no de-duplication guard and no rule-based tier override.
    """

    name = "react"

    def __init__(self, max_steps=config.MAX_STEPS):
        from env.tools import TOOL_SCHEMAS

        self.max_steps = max_steps
        self.tools = [*TOOL_SCHEMAS, {"type": "function", "function": {
            "name": "submit_diagnosis", "description": "Submit the final root cause and tier.",
            "parameters": {"type": "object", "properties": {
                "root_cause": {"type": "string", "enum": list(CAUSES)},
                "tier": {"type": "string", "enum": ["L1", "L2"]},
                "rationale": {"type": "string", "description": "2-3 sentences citing the decisive evidence."}},
                "required": ["root_cause", "tier", "rationale"]}}}]

    def run(self, env):
        from env.tools import execute

        messages = [
            {"role": "system", "content": REACT_SYSTEM.format(budget=self.max_steps, labels=_cause_catalog())},
            {"role": "user", "content": f'Customer complaint: "{env.case["complaint"]}"'},
        ]
        log, seen, repeated, diagnosis = [], set(), 0, None
        for _ in range(self.max_steps):
            out = llm.chat(messages, tools=self.tools, role="baseline")
            calls = out["tool_calls"]
            messages.append({"role": "assistant", "content": out["content"] or "", "tool_calls": [
                {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
                for c in calls]} if calls else {"role": "assistant", "content": out["content"] or ""})
            if not calls:
                messages.append({"role": "user", "content": "Call exactly one tool."})
                continue
            for call in calls:
                try:
                    args = json.loads(call["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                if call["name"] == "submit_diagnosis":
                    if args.get("root_cause") in CAUSES and args.get("tier") in ("L1", "L2"):
                        diagnosis = args
                    result = {"ok": diagnosis is not None}
                else:
                    key = (call["name"], json.dumps(args, sort_keys=True))
                    repeated += key in seen
                    seen.add(key)
                    result = execute(env, call["name"], args)
                    log.append({"phase": "react", "tool": call["name"], "args": args})
                messages.append({"role": "tool", "tool_call_id": call["id"],
                                 "content": json.dumps(result, ensure_ascii=False)})
            if diagnosis:
                break
        if diagnosis is None:
            diagnosis = {"root_cause": "HW_FAULT_SUSPECTED", "tier": "L2",
                         "rationale": "Step budget exhausted without a diagnosis."}
        return {
            "system": self.name, "case_id": env.case["case_id"],
            "pred_root_cause": diagnosis["root_cause"], "pred_tier": diagnosis["tier"],
            "tier_overridden": False, "triggers": [], "rationale": diagnosis["rationale"],
            "output": self._output(messages, diagnosis), "rule_hints": [], "log": log,
            "trace": env.trace, "dedup_hits": repeated, "memory": {},
        }

    def _output(self, messages, diagnosis):
        from agent.triage import L1_INSTRUCTION, L2_INSTRUCTION

        transcript = "\n".join(
            f"[{m['role']}] {m.get('content') or ''} "
            f"{json.dumps([c['function'] for c in m.get('tool_calls', [])], ensure_ascii=False) if m.get('tool_calls') else ''}"
            for m in messages[1:])
        instruction = L1_INSTRUCTION if diagnosis["tier"] == "L1" else L2_INSTRUCTION
        return llm.chat_json([{"role": "user", "content": (
            "You are writing the final hand-off for a frontline support staff member at the end of a "
            f"technical support session. Diagnosed root cause: {diagnosis['root_cause']} ({diagnosis['tier']}).\n"
            f"Rationale: {diagnosis['rationale']}\nSession transcript:\n{transcript[-12000:]}\n\n"
            f"{instruction}\nReturn JSON only.")}], model=config.OUTPUT_MODEL, role="baseline")
