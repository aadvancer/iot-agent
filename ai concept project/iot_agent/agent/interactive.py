"""Resumable diagnosis session that pauses for real human replies in the UI."""
import json

import config
import llm
from agent import planner
from agent.agent import (
    STEP_PROMPT,
    SYSTEM_PROMPT,
    TopologyAgent,
    _labels,
)
from agent.memory import SessionMemory
from agent.rules import match_causes
from agent.triage import build_output, classify_tier
from env.case_env import CaseEnv
from env.tools import execute


class InteractiveDiagnosis:
    """Run the topology agent one conversational turn at a time."""

    def __init__(self, case, max_steps=config.MAX_STEPS):
        self.case = case
        self.env = CaseEnv(case)
        self.memory = SessionMemory(case["complaint"])
        self.agent = TopologyAgent(max_steps=max_steps)
        self.max_steps = max_steps
        self.step = 0
        self.notes = []
        self.log = []
        self.pending = None
        self.result = None

    def start(self):
        """Collect simulated console evidence and continue until a reply is needed."""
        while (query := planner.next_query(self.memory)) is not None:
            tool, args, stage = query
            result = execute(self.env, tool, args)
            self.memory.update(tool, args, result)
            self.log.append({"phase": "collect", "stage": stage, "tool": tool, "args": args})
        return self._continue_reasoning()

    def submit(self, answer, resolved=None):
        """Record a customer's reply and resume diagnosis until the next prompt."""
        if self.pending is None:
            raise RuntimeError("There is no pending customer question or action.")
        if not answer.strip():
            raise ValueError("Please enter a reply before continuing.")
        self._record_user_answer(answer, resolved)
        return self._continue_reasoning()

    def resume(self):
        """Retry reasoning after a transient model/API error."""
        if self.pending is not None or self.result is not None:
            raise RuntimeError("This diagnosis session is not waiting to resume.")
        return self._continue_reasoning()

    def _record_user_answer(self, answer, resolved):
        tool = self.pending["tool"]
        args = self.pending["args"]
        if tool == "ask_user":
            result = {"answer": answer.strip()}
            self.memory.update(tool, args, result)
        elif tool == "instruct_user":
            if not isinstance(resolved, bool):
                raise ValueError("Choose whether the requested action resolved the issue.")
            self.env.actions_done.append(args["action"])
            result = {"outcome": answer.strip()}
            self.memory.add_action(
                args["action"], args.get("target_cause"), answer.strip(), resolved
            )
        else:
            raise RuntimeError(f"Unsupported pending interaction: {tool!r}")

        self.env.trace.append({"tool": tool, "args": args, "result": result})
        self.notes.append(
            f"(step {self.step - 1}) {tool}({json.dumps(args, ensure_ascii=False)}) -> "
            f"{json.dumps(result, ensure_ascii=False)}"
        )
        self.pending = None

    def _continue_reasoning(self):
        while self.step < self.max_steps:
            current_step = self.step
            self.step += 1
            messages = [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT.format(
                        budget=self.max_steps - current_step, labels=_labels()
                    ),
                },
                {
                    "role": "user",
                    "content": STEP_PROMPT.format(
                        complaint=self.memory.complaint,
                        memory=self.memory.snapshot(),
                        hints=json.dumps(match_causes(self.memory), ensure_ascii=False),
                        notes="\n".join(self.notes[-3:]) or "(none)",
                    ),
                },
            ]
            response = llm.chat(messages, tools=self.agent.tools, role="agent")
            tool_calls = response.get("tool_calls") or []
            if not tool_calls:
                self.notes.append(f"(step {current_step}) {response.get('content') or ''}"[:300])
                continue

            call = tool_calls[0]
            args = json.loads(call["arguments"] or "{}")
            name = call["name"]
            if response.get("content"):
                self.notes.append(f"(step {current_step}) {response['content']}"[:300])
            if name == "submit_diagnosis":
                self.log.append({"phase": "reason", "tool": name, "args": args})
                return self._finish(args)

            if name in ("ask_user", "instruct_user"):
                remembered = self.memory.lookup(name, args)
                if remembered is not None:
                    self.memory.dedup_hits += 1
                    self.notes.append(
                        f"(step {current_step}) {name} already answered from memory."
                    )
                    continue
                self.pending = {"tool": name, "args": args}
                self.log.append({"phase": "reason", "tool": name, "args": args})
                return self._interaction_prompt()

            result = self.agent._call(self.env, self.memory, name, args)
            self.notes.append(
                f"(step {current_step}) {name}({json.dumps(args, ensure_ascii=False)}) -> "
                f"{json.dumps(result, ensure_ascii=False)}"[:300]
            )
            self.log.append({"phase": "reason", "tool": name, "args": args})

        hints = match_causes(self.memory)
        diagnosis = {
            "root_cause": hints[0]["cause"] if hints else "HW_FAULT_SUSPECTED",
            "rationale": "Step budget exhausted; best rule-matched hypothesis.",
        }
        return self._finish(diagnosis)

    def _interaction_prompt(self):
        args = self.pending["args"]
        if self.pending["tool"] == "ask_user":
            return f"建议您向客户确认：{args['question']}\n\n请把客户的回答录入下方。"
        return (
            f"建议您指导客户执行以下操作：\n\n"
            f"{args['action']}\n\n请录入客户的操作结果，并标记问题是否已解决。"
        )

    def _finish(self, diagnosis):
        cause = diagnosis["root_cause"]
        tier, triggers, overridden = classify_tier(self.memory, cause)
        output = build_output(
            self.memory, cause, tier, diagnosis["rationale"], triggers
        )
        self.result = {
            "system": "interactive_topology_agent",
            "case_id": self.env.case["case_id"],
            "pred_root_cause": cause,
            "pred_tier": tier,
            "tier_overridden": overridden,
            "triggers": triggers,
            "rationale": diagnosis["rationale"],
            "output": output,
            "rule_hints": match_causes(self.memory),
            "log": self.log,
            "trace": self.env.trace,
            "dedup_hits": self.memory.dedup_hits,
            "memory": json.loads(self.memory.snapshot()),
        }
        return None
