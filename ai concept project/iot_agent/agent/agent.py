"""Topology-aware diagnostic agent, orchestrated with LangGraph."""
import copy

import config
from agent.memory import SessionMemory
from agent.rules import CAUSES
from agent.workflow import build_workflow, judge_action_reply
from env.case_env import CaseEnv
from env.tools import TOOL_SCHEMAS, execute

# after this many consecutive knowledge-base searches without a new snippet, further
# searches are answered from memory: the KB has nothing more on the question (cf. C045)
KB_STALE_LIMIT = 2
KB_NO_NEW_NOTE = ("No new knowledge: every result was already in MEMORY. The knowledge base has no "
                  "further procedure for this; decide from the evidence you have.")
KB_EXHAUSTED_NOTE = ("Search not executed: the last searches found nothing new, so the knowledge base does "
                     "not cover this. Stop searching and submit_diagnosis from the collected evidence and "
                     "the RULE HINTS.")


def _agent_tools():
    tools = copy.deepcopy(TOOL_SCHEMAS)
    for tool in tools:
        if tool["function"]["name"] == "instruct_user":
            parameters = tool["function"]["parameters"]
            parameters["properties"]["target_cause"] = {
                "type": "string",
                "enum": list(CAUSES),
                "description": "Root cause this fix is meant to resolve.",
            }
            parameters["required"].append("target_cause")
    tools.append(
        {
            "type": "function",
            "function": {
                "name": "submit_diagnosis",
                "description": "Submit the final root cause.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "root_cause": {"type": "string", "enum": list(CAUSES)},
                        "rationale": {
                            "type": "string",
                            "description": "2-3 sentences citing the decisive evidence.",
                        },
                    },
                    "required": ["root_cause", "rationale"],
                },
            },
        }
    )
    return tools


class TopologyAgent:
    name = "topology_agent"
    # ablation switches; all on for the full system
    use_planner = True
    use_hints = True
    use_memory = True
    use_override = True

    def __init__(self, max_steps=config.MAX_STEPS):
        self.max_steps = max_steps
        self.tools = _agent_tools()
        self.workflow = build_workflow(self)

    def _call(self, env, memory: SessionMemory, tool, args):
        cached = memory.lookup(tool, args) if self.use_memory else None
        if cached is not None:
            memory.dedup_hits += 1
            return {"note": "already in memory", **cached}
        if tool == "instruct_user":
            result = execute(env, tool, {"action": args["action"]})
            # Same judgement as the interactive workbench: an unclear reply or a
            # non-standard action must not count as a failed standard fix (R3).
            resolved, standard_fix, _ = judge_action_reply(
                memory.complaint, args["action"], result["outcome"], args.get("target_cause"))
            memory.add_action(args["action"], args.get("target_cause"), result["outcome"],
                              resolved, standard_fix)
            return result
        if tool == "search_kb" and self.use_memory:
            return self._search_kb(env, memory, args)
        result = execute(env, tool, args)
        memory.update(tool, args, result)
        return result

    def _search_kb(self, env, memory: SessionMemory, args):
        """search_kb with a memory-based stop: repeated rephrasings that only return
        snippets already in memory are cut off instead of burning the step budget."""
        if memory.stale_kb_searches >= KB_STALE_LIMIT:
            return {"results": [], "note": KB_EXHAUSTED_NOTE}
        known = {k["source"] for k in memory.kb}
        result = execute(env, "search_kb", args)
        memory.update("search_kb", args, result)
        if isinstance(result.get("results"), list) and all(r["source"] in known for r in result["results"]):
            memory.stale_kb_searches += 1
            return {**result, "note": KB_NO_NEW_NOTE}
        memory.stale_kb_searches = 0
        return result

    def run(self, env: CaseEnv) -> dict:
        memory = SessionMemory(env.case["complaint"])
        state = self.workflow.invoke(
            {
                "case": env.case,
                "memory": memory.to_dict(),
                "trace": env.trace,
                "actions_done": env.actions_done,
                "user_history": env.user.history,
                "log": [],
                "notes": [],
                "step": 0,
                "system": self.name,
            }
        )
        env.trace = state["trace"]
        env.actions_done = state["actions_done"]
        env.user.history = state["user_history"]
        result = state["result"]
        result["system"] = self.name
        return result


class NoPlannerAgent(TopologyAgent):
    """Ablation: no topology planner; the LLM must gather console evidence itself."""
    name = "abl_no_planner"
    use_planner = False


class NoHintsAgent(TopologyAgent):
    """Ablation: no deterministic rule hints in the prompt or the budget fallback."""
    name = "abl_no_hints"
    use_hints = False


class NoMemoryAgent(TopologyAgent):
    """Ablation: raw tool transcript instead of the structured memory; no dedup or recall."""
    name = "abl_no_memory"
    use_memory = False


class NoOverrideAgent(TopologyAgent):
    """Ablation: tier taken from the taxonomy only, without hard escalation rules."""
    name = "abl_no_override"
    use_override = False


ABLATIONS = {cls.name: cls for cls in (NoPlannerAgent, NoHintsAgent, NoMemoryAgent, NoOverrideAgent)}
