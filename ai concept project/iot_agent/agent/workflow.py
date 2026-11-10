"""LangGraph workflow shared by batch and interactive diagnosis."""
import json
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

import config
import llm
from agent import planner
from agent.memory import SessionMemory
from agent.observability import get_logger
from agent.persistence import get_checkpointer, save_case_facts
from agent.rules import CAUSES, match_causes
from agent.triage import build_output, classify_tier, validate_output
from env.case_env import CaseEnv
from env.tools import execute

SYSTEM_PROMPT = """You are a copilot for FRONTLINE SUPPORT STAFF of a gateway-centric smart security system
(one base station = master; cameras and sensors = slaves that can only talk through the base station).
Your reader is the support staff member, never the end customer: you never talk to the customer directly.
The staff member has the support console and talks to the customer; ask_user means "suggest a question the staff
member should put to the customer" and instruct_user means "give the staff member one action to walk the customer
through". Write these as concise instructions to the staff member, and report back what the customer said.
Your goals: find the root cause, help staff resolve self-recoverable faults at frontline (L1), and prepare an
escalation ticket only for genuine complex faults for FAE engineers (L2). Wrong escalations waste scarce FAE time;
missed escalations delay critical fixes.

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
Historical facts from earlier sessions are unverified clues; confirm them before treating them as current.

Root-cause labels (tier):
{labels}"""

STEP_PROMPT = """Customer complaint: "{complaint}"

MEMORY:
{memory}

RULE HINTS:
{hints}

YOUR RECENT NOTES:
{notes}

RELEVANT RECALLS FROM THIS SESSION:
{recalled}

Choose the next action (call exactly one tool)."""

JUDGE_REPLY_PROMPT = """You review a technical-support conversation for a smart security system.
Customer's original complaint: "{complaint}"
The support staff asked the customer to perform: "{action}"
The action was meant to resolve: {target_cause}
Standard frontline fix for that cause: "{standard_fix}"
The staff member recorded the customer's reply (may be in any language, may be terse): "{reply}"

1. Decide whether the reply shows that the action resolved the ORIGINAL problem.
- "resolved": true  -> the customer clearly reports the problem is gone / the fix worked.
- "resolved": false -> the customer clearly reports the problem persists or the action failed.
- "resolved": null  -> the reply does not say (e.g. not performed yet, off-topic, only an emotion, a question).
2. Decide whether the action carried out the standard frontline fix above (its essential step, any wording).
- "standard_fix": true  -> it did.
- "standard_fix": false -> it was something else: a diagnostic test, an unrelated restart, a different fix.
- "standard_fix": null  -> no standard fix is given.
Return JSON only: {{"resolved": true|false|null, "standard_fix": true|false|null,
"reason": "<one short sentence in Chinese>"}}"""


def judge_action_reply(complaint, action, reply, target_cause=None):
    """Infer from the customer's own words whether a guided action fixed the issue,
    and whether it was the standard fix for its target cause (only those feed R3)."""
    standard = CAUSES.get(target_cause, {}).get("resolution")
    verdict = llm.chat_json(
        [{"role": "user", "content": JUDGE_REPLY_PROMPT.format(
            complaint=complaint, action=action, reply=reply,
            target_cause=target_cause or "(not given)", standard_fix=standard or "(none)")}],
        model=config.REASONING_MODEL, role="agent",
    )
    resolved = verdict.get("resolved")
    if not isinstance(resolved, bool):
        resolved = None
    standard_fix = verdict.get("standard_fix") if standard else None
    if not isinstance(standard_fix, bool):
        standard_fix = None
    return resolved, standard_fix, str(verdict.get("reason") or "").strip()


def labels():
    return "\n".join(
        f"- {key} ({value['tier']}): {', '.join(value['symptoms'])}"
        for key, value in CAUSES.items()
    )


class WorkflowState(TypedDict, total=False):
    case: dict
    memory: dict
    trace: list
    actions_done: list
    user_history: list
    log: list
    notes: list
    step: int
    tool_call: dict | None
    pending: dict | None
    diagnosis: dict | None
    result: dict | None
    system: str
    persist_history: bool
    tool_result: dict
    tool_validation: str | None
    judgement: dict | None


LOGGER = get_logger()


def validate_tool_call(call, tools):
    schemas = {tool["function"]["name"]: tool["function"]["parameters"]
               for tool in tools}
    name = call.get("name")
    if name not in schemas:
        return f"Unknown tool: {name!r}"
    args = call.get("args")
    if not isinstance(args, dict):
        return "Tool arguments must be a JSON object."
    schema = schemas[name]
    missing = [key for key in schema.get("required", []) if key not in args]
    if missing:
        return f"Missing required tool arguments: {', '.join(missing)}"
    for key, value in args.items():
        prop = schema.get("properties", {}).get(key)
        if prop is None:
            return f"Unexpected tool argument: {key}"
        expected = prop.get("type")
        valid_type = {
            "string": lambda item: isinstance(item, str),
            "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
            "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
            "boolean": lambda item: isinstance(item, bool),
            "object": lambda item: isinstance(item, dict),
            "array": lambda item: isinstance(item, list),
        }.get(expected, lambda item: True)
        if not valid_type(value):
            return f"Tool argument {key!r} must be {expected}."
        if "enum" in prop and value not in prop["enum"]:
            return f"Tool argument {key!r} is not an allowed value."
    return None


def validate_diagnosis(diagnosis):
    if not isinstance(diagnosis, dict):
        return "Diagnosis must be a JSON object."
    if diagnosis.get("root_cause") not in CAUSES:
        return "Diagnosis contains an unknown root-cause label."
    if not isinstance(diagnosis.get("rationale"), str) or not diagnosis["rationale"].strip():
        return "Diagnosis must include a non-empty rationale."
    return None


def validate_tool_result(name, result):
    if not isinstance(result, dict):
        return "Tool returned a non-object result."
    if result.get("error"):
        return f"Tool returned an error: {result['error']}"
    expected = {
        "get_base_status": ("online", bool),
        "get_topology": ("devices", list),
        "get_device_info": ("id", str),
        "check_firmware_compat": ("compatible", bool),
        "get_logs": ("lines", list),
        "search_kb": ("results", list),
        "ask_user": ("answer", str),
        "instruct_user": ("outcome", str),
    }.get(name)
    if expected and (
        expected[0] not in result or not isinstance(result[expected[0]], expected[1])
    ):
        return f"Tool result is missing a valid {expected[0]!r} field."
    return None


def validate_final_output(tier, result):
    return validate_output(tier, result)


PLANNER_OFF_NOTE = """No console evidence has been collected yet: query the support console yourself
(get_base_status, get_topology, get_device_info, get_logs, check_firmware_compat) before deciding."""

HINTS_OFF_NOTE = "RULE HINTS are not available in this session; reason from the evidence yourself."


def _system_prompt(agent, budget):
    prompt = SYSTEM_PROMPT.format(budget=budget, labels=labels())
    if not getattr(agent, "use_planner", True):
        prompt = prompt.replace(
            "Support-console evidence has already been collected in topology\norder",
            "Check the support console in topology\norder",
        ) + "\n\n" + PLANNER_OFF_NOTE
    if not getattr(agent, "use_hints", True):
        prompt = prompt.replace(
            "RULE HINTS are candidate causes matched deterministically from the evidence - "
            "verify them, they can be incomplete.",
            HINTS_OFF_NOTE,
        )
    return prompt


def _raw_transcript(trace):
    """Unstructured tool log used by the no-memory ablation instead of the slot snapshot."""
    if not trace:
        return "(nothing yet)"
    return "\n".join(
        f"{i}. {t['tool']}({json.dumps(t['args'], ensure_ascii=False)}) -> "
        f"{json.dumps(t['result'], ensure_ascii=False)}"
        for i, t in enumerate(trace, 1)
    )


def _force_diagnosis(memory, use_hints=True):
    hints = match_causes(memory) if use_hints else []
    return {
        "root_cause": hints[0]["cause"] if hints else "HW_FAULT_SUSPECTED",
        "rationale": "Step budget exhausted; best rule-matched hypothesis.",
    }


def _restore(state):
    env = CaseEnv(state["case"])
    env.trace = list(state.get("trace", []))
    env.actions_done = list(state.get("actions_done", []))
    env.user.history = list(state.get("user_history", []))
    memory = SessionMemory.from_dict(state["memory"])
    return env, memory


def _persist(env, memory):
    return {
        "memory": memory.to_dict(),
        "trace": env.trace,
        "actions_done": env.actions_done,
        "user_history": env.user.history,
    }


def _finish(state, use_override=True):
    env, memory = _restore(state)
    diagnosis = state["diagnosis"]
    cause = diagnosis["root_cause"]
    tier, triggers, overridden = classify_tier(memory, cause, use_override=use_override)
    output = build_output(memory, cause, tier, diagnosis["rationale"], triggers)
    invalid_output = validate_final_output(tier, output)
    if invalid_output:
        LOGGER.error(
            "final_output_rejected",
            extra={"event": "final_output_rejected", "case_id": env.case["case_id"],
                   "status": tier, "detail": invalid_output},
        )
        raise ValueError(invalid_output)
    if state.get("persist_history"):
        save_case_facts(env.case["case_id"], memory.user_facts)
    LOGGER.info(
        "diagnosis_finished",
        extra={
            "event": "diagnosis_finished",
            "case_id": env.case["case_id"],
            "status": tier,
        },
    )
    return {
        "result": {
            "system": state.get("system", "interactive_topology_agent"),
            "case_id": env.case["case_id"],
            "pred_root_cause": cause,
            "pred_tier": tier,
            "tier_overridden": overridden,
            "triggers": triggers,
            "rationale": diagnosis["rationale"],
            "output": output,
            "rule_hints": match_causes(memory),
            "log": state["log"],
            "trace": env.trace,
            "dedup_hits": memory.dedup_hits,
            "memory": json.loads(memory.snapshot()),
        }
    }


def build_workflow(agent, interactive=False):
    """Create the diagnosis graph; interactive runs checkpoint at human input."""

    use_planner = getattr(agent, "use_planner", True)
    use_hints = getattr(agent, "use_hints", True)
    use_memory = getattr(agent, "use_memory", True)
    use_override = getattr(agent, "use_override", True)

    def collect(state):
        env, memory = _restore(state)
        log = list(state.get("log", []))
        while use_planner and (query := planner.next_query(memory)) is not None:
            tool, args, stage = query
            result = agent._call(env, memory, tool, args)
            invalid = validate_tool_result(tool, result)
            if invalid:
                LOGGER.error(
                    "evidence_tool_failed",
                    extra={"event": "evidence_tool_failed", "case_id": env.case["case_id"],
                           "tool": tool, "detail": invalid},
                )
                raise RuntimeError(f"Evidence collection failed for {tool}: {invalid}")
            log.append({"phase": "collect", "stage": stage, "tool": tool, "args": args})
            LOGGER.info(
                "evidence_collected",
                extra={"event": "evidence_collected", "case_id": env.case["case_id"],
                       "tool": tool, "status": stage},
            )
        return {**_persist(env, memory), "log": log}

    def reason(state):
        step = state.get("step", 0)
        if step >= agent.max_steps:
            _, memory = _restore(state)
            return {"diagnosis": _force_diagnosis(memory, use_hints), "tool_call": None}

        env, memory = _restore(state)
        recent_notes = "\n".join(state.get("notes", [])[-3:])
        recalled = (
            memory.recall_interactions(f"{memory.complaint}\n{recent_notes}", k=3)
            if use_memory else []
        )
        messages = [
            {
                "role": "system",
                "content": _system_prompt(agent, agent.max_steps - step),
            },
            {
                "role": "user",
                "content": STEP_PROMPT.format(
                    complaint=memory.complaint,
                    memory=memory.snapshot() if use_memory else _raw_transcript(env.trace),
                    hints=(json.dumps(match_causes(memory), ensure_ascii=False)
                           if use_hints else "(disabled)"),
                    notes=recent_notes or "(none)",
                    recalled="\n".join(recalled) or "(none)",
                ),
            },
        ]
        LOGGER.info(
            "reasoning_started",
            extra={"event": "reasoning_started", "case_id": env.case["case_id"],
                   "step": step},
        )
        response = llm.chat(
            messages,
            model=config.REASONING_MODEL,
            tools=agent.tools,
            role="agent",
        )
        notes = list(state.get("notes", []))
        calls = response.get("tool_calls") or []
        if not calls:
            notes.append(f"(step {step}) {response.get('content') or ''}"[:300])
            return {"step": step + 1, "notes": notes, "tool_call": None}

        call = calls[0]
        args = json.loads(call.get("arguments") or "{}")
        if call["name"] == "submit_diagnosis":
            invalid = validate_diagnosis(args)
            if invalid:
                notes.append(f"Diagnosis validation failed: {invalid}")
                LOGGER.warning(
                    "diagnosis_rejected",
                    extra={"event": "diagnosis_rejected", "case_id": env.case["case_id"],
                           "step": step, "detail": invalid},
                )
                return {"step": step + 1, "notes": notes, "tool_call": None}
            log = list(state.get("log", []))
            log.append({"phase": "reason", "tool": "submit_diagnosis", "args": args})
            return {
                "step": step + 1,
                "notes": notes,
                "tool_call": None,
                "diagnosis": args,
                "log": log,
            }
        invalid = validate_tool_call(
            {"name": call["name"], "args": args}, agent.tools
        )
        if invalid:
            notes.append(f"Tool call validation failed: {invalid}")
            LOGGER.warning(
                "tool_call_rejected",
                extra={"event": "tool_call_rejected", "case_id": env.case["case_id"],
                       "step": step, "detail": invalid},
            )
            return {"step": step + 1, "notes": notes, "tool_call": None}
        return {
            "step": step + 1,
            "notes": notes,
            "tool_call": {"name": call["name"], "args": args},
            "pending": (
                {"tool": call["name"], "args": args}
                if interactive and call["name"] in ("ask_user", "instruct_user")
                else None
            ),
        }

    def execute_tool(state):
        env, memory = _restore(state)
        call = state["tool_call"]
        result = agent._call(env, memory, call["name"], call["args"])
        LOGGER.info(
            "tool_executed",
            extra={"event": "tool_executed", "case_id": env.case["case_id"],
                   "step": state["step"] - 1, "tool": call["name"]},
        )
        log = list(state.get("log", []))
        log.append({"phase": "reason", "tool": call["name"], "args": call["args"]})
        return {
            **_persist(env, memory),
            "log": log,
            "tool_result": result,
        }

    def validate_tool(state):
        call = state["tool_call"]
        result = state["tool_result"]
        invalid = validate_tool_result(call["name"], result)
        notes = list(state.get("notes", []))
        notes.append(
            f"(step {state['step'] - 1}) {call['name']}({json.dumps(call['args'], ensure_ascii=False)}) -> "
            f"{json.dumps(result, ensure_ascii=False)}"[:300]
        )
        if invalid:
            notes.append(f"Tool result validation failed: {invalid}")
            LOGGER.warning(
                "tool_result_rejected",
                extra={"event": "tool_result_rejected", "case_id": state["case"]["case_id"],
                       "step": state["step"] - 1, "tool": call["name"], "detail": invalid},
            )
        return {
            "notes": notes,
            "tool_call": None,
            "tool_result": {},
            "tool_validation": invalid,
        }

    def wait_for_human(state):
        pending = state["pending"]
        reply = interrupt(pending)
        env, memory = _restore(state)
        args = pending["args"]
        judgement = None
        if pending["tool"] == "instruct_user" and reply.get("resolved") is None:
            resolved, standard_fix, reason = judge_action_reply(
                memory.complaint, args["action"], reply["answer"].strip(), args.get("target_cause"))
            reply = {**reply, "resolved": resolved, "standard_fix": standard_fix}
            judgement = {"resolved": resolved, "standard_fix": standard_fix, "reason": reason}
        result = apply_human_reply(memory, env, pending, reply)
        if state.get("persist_history"):
            save_case_facts(env.case["case_id"], memory.user_facts)
        LOGGER.info(
            "human_reply_received",
            extra={"event": "human_reply_received", "case_id": env.case["case_id"],
                   "step": state.get("step", 0), "tool": pending["tool"]},
        )
        notes = list(state.get("notes", []))
        notes.append(
            f"(step {state['step'] - 1}) {pending['tool']}({json.dumps(args, ensure_ascii=False)}) -> "
            f"{json.dumps(result, ensure_ascii=False)}"
        )
        return {
            **_persist(env, memory),
            "notes": notes,
            "pending": None,
            "tool_call": None,
            "judgement": judgement,
        }

    def route(state):
        if state.get("diagnosis") is not None:
            return "finish"
        if state.get("tool_call") is None:
            return "reason"
        if interactive and state["tool_call"]["name"] in ("ask_user", "instruct_user"):
            return "wait"
        return "tool"

    graph = StateGraph(WorkflowState)
    graph.add_node("collect", collect)
    graph.add_node("reason", reason)
    graph.add_node("tool", execute_tool)
    graph.add_node("validate", validate_tool)
    graph.add_node("wait", wait_for_human)
    graph.add_node("finish", lambda state: _finish(state, use_override))
    graph.add_edge(START, "collect")
    graph.add_edge("collect", "reason")
    graph.add_conditional_edges(
        "reason", route, {"finish": "finish", "reason": "reason", "tool": "tool", "wait": "wait"}
    )
    graph.add_edge("tool", "validate")
    graph.add_edge("validate", "reason")
    graph.add_edge("wait", "reason")
    graph.add_edge("finish", END)
    if interactive:
        return graph.compile(checkpointer=get_checkpointer())
    return graph.compile()


def apply_human_reply(memory, env, pending, reply):
    args = pending["args"]
    if pending["tool"] == "ask_user":
        result = {"answer": reply["answer"].strip()}
        memory.update("ask_user", args, result)
    else:
        # resolved: True / False, or None when the reply does not say (not counted as a failed fix)
        if reply.get("resolved") not in (True, False, None):
            raise ValueError("resolved must be true, false or null.")
        result = {"outcome": reply["answer"].strip(), "resolved": reply.get("resolved")}
        env.actions_done.append(args["action"])
        memory.add_action(
            args["action"],
            args.get("target_cause"),
            result["outcome"],
            reply.get("resolved"),
            reply.get("standard_fix"),
        )
    env.trace.append({"tool": pending["tool"], "args": args, "result": result})
    return result
