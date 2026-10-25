"""Proposed method: topology-aware diagnostic agent.

run() has four phases:
  1. Evidence collection - the planner walks S1..S5 over the support console (no LLM).
  2. Reasoning loop     - the LLM sees ONLY the structured memory snapshot plus rule-matcher
                          hints (not the raw transcript), and may search the KB, ask the customer,
                          instruct a fix, or submit a diagnosis.
  3. Triage             - taxonomy tier, overridden to L2 by hard escalation rules R1-R4.
  4. Output             - L1 repair steps + customer reply, or L2 escalation ticket.
"""
import copy
import json

import config
import llm
from agent import planner
from agent.memory import SessionMemory
from agent.rules import CAUSES, match_causes
from agent.triage import build_output, classify_tier
from env.case_env import CaseEnv
from env.tools import TOOL_SCHEMAS, execute

SYSTEM_PROMPT = """You are a frontline technical-support diagnostic agent for a gateway-centric smart security system
(one base station = master; cameras and sensors = slaves that can only talk through the base station).
Your goals: find the root cause, resolve self-recoverable faults at frontline (L1), and escalate only genuine
complex faults to FAE engineers (L2). Wrong escalations waste scarce FAE time; missed escalations delay critical fixes.

You receive a MEMORY snapshot of confirmed facts. Support-console evidence has already been collected in topology
order (S1 base station -> S2 binding/capacity -> S3 link quality -> S4 firmware/protocol -> S5 peripheral).
RULE HINTS are candidate causes matched deterministically from the evidence - verify them, they can be incomplete.

Procedure:
1. Reason from the master down: a fault at the base station explains peripheral symptoms; several peripherals failing
   at the same moment points to a system-level fault, not to individual signal or battery problems.
2. Never re-query or re-ask anything already in MEMORY. Use ask_user only for facts the console cannot show
   (LED colour, physical location, recent changes). Use search_kb when you need the fix procedure or policy.
3. For an L1 cause, instruct the customer to perform its standard fix once (instruct_user with target_cause) to confirm.
   If the fix resolves the issue, submit. If it does not, reconsider: a failed standard fix means escalation.
4. Do not instruct base-station factory resets or firmware downgrades.
5. Finish with submit_diagnosis as soon as the evidence is sufficient. Budget: {budget} actions left.

Root-cause labels (tier):
{labels}"""

STEP_PROMPT = """Customer complaint: "{complaint}"

MEMORY:
{memory}

RULE HINTS:
{hints}

YOUR RECENT NOTES:
{notes}

Choose the next action (call exactly one tool)."""

OUTCOME_PROMPT = """A support agent asked the customer to: "{action}"
The customer reported: "{outcome}"
Did this resolve the customer's original problem? Return JSON {{"resolved": true|false}}."""


def _labels():
    return "\n".join(f"- {k} ({v['tier']}): {', '.join(v['symptoms'])}" for k, v in CAUSES.items())


def _agent_tools():
    tools = copy.deepcopy(TOOL_SCHEMAS)
    for t in tools:
        if t["function"]["name"] == "instruct_user":
            p = t["function"]["parameters"]
            p["properties"]["target_cause"] = {"type": "string", "enum": list(CAUSES),
                                               "description": "Root cause this fix is meant to resolve."}
            p["required"].append("target_cause")
    tools.append({"type": "function", "function": {
        "name": "submit_diagnosis", "description": "Submit the final root cause.",
        "parameters": {"type": "object", "properties": {
            "root_cause": {"type": "string", "enum": list(CAUSES)},
            "rationale": {"type": "string", "description": "2-3 sentences citing the decisive evidence."}},
            "required": ["root_cause", "rationale"]}}})
    return tools


class TopologyAgent:
    name = "topology_agent"

    def __init__(self, max_steps=config.MAX_STEPS):
        self.max_steps = max_steps
        self.tools = _agent_tools()

    # ----- tool call with memory guard -----
    def _call(self, env, m: SessionMemory, tool, args):
        cached = m.lookup(tool, args)
        if cached is not None:
            m.dedup_hits += 1
            return {"note": "already in memory", **cached}
        if tool == "instruct_user":
            res = execute(env, tool, {"action": args["action"]})
            verdict = llm.chat_json([{"role": "user", "content": OUTCOME_PROMPT.format(
                action=args["action"], outcome=res["outcome"])}], model=config.USER_SIM_MODEL, role="agent")
            m.add_action(args["action"], args.get("target_cause"), res["outcome"], bool(verdict.get("resolved")))
            return res
        res = execute(env, tool, args)
        m.update(tool, args, res)
        return res

    def run(self, env: CaseEnv) -> dict:
        m = SessionMemory(env.case["complaint"])
        log = []

        # Phase 1: deterministic topology-ordered evidence collection
        while (q := planner.next_query(m)) is not None:
            tool, args, stage = q
            self._call(env, m, tool, args)
            log.append({"phase": "collect", "stage": stage, "tool": tool, "args": args})

        # Phase 2: LLM reasoning over structured memory
        notes, diagnosis = [], None
        for step in range(self.max_steps):
            budget = self.max_steps - step
            msgs = [
                {"role": "system", "content": SYSTEM_PROMPT.format(budget=budget, labels=_labels())},
                {"role": "user", "content": STEP_PROMPT.format(
                    complaint=m.complaint, memory=m.snapshot(),
                    hints=json.dumps(match_causes(m), ensure_ascii=False),
                    notes="\n".join(notes[-3:]) or "(none)")},
            ]
            out = llm.chat(msgs, tools=self.tools, role="agent")
            if not out["tool_calls"]:
                notes.append(f"(step {step}) {out['content'] or ''}"[:300])
                continue
            tc = out["tool_calls"][0]
            args = json.loads(tc["arguments"] or "{}")
            if out["content"]:
                notes.append(f"(step {step}) {out['content']}"[:300])
            if tc["name"] == "submit_diagnosis":
                diagnosis = args
                log.append({"phase": "reason", "tool": "submit_diagnosis", "args": args})
                break
            res = self._call(env, m, tc["name"], args)
            notes.append(f"(step {step}) {tc['name']}({json.dumps(args, ensure_ascii=False)}) -> "
                         f"{json.dumps(res, ensure_ascii=False)}"[:300])
            log.append({"phase": "reason", "tool": tc["name"], "args": args})

        if diagnosis is None:   # budget exhausted: force a decision from current memory
            hints = match_causes(m)
            diagnosis = {"root_cause": hints[0]["cause"] if hints else "HW_FAULT_SUSPECTED",
                         "rationale": "Step budget exhausted; best rule-matched hypothesis."}

        # Phase 3 + 4: triage and output
        cause = diagnosis["root_cause"]
        tier, triggers, overridden = classify_tier(m, cause)
        output = build_output(m, cause, tier, diagnosis["rationale"], triggers)
        return {
            "system": self.name, "case_id": env.case["case_id"],
            "pred_root_cause": cause, "pred_tier": tier, "tier_overridden": overridden,
            "triggers": triggers, "rationale": diagnosis["rationale"], "output": output,
            "rule_hints": match_causes(m), "log": log, "trace": env.trace,
            "dedup_hits": m.dedup_hits, "memory": json.loads(m.snapshot()),
        }
