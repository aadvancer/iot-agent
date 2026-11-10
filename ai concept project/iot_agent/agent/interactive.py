"""Resumable diagnosis sessions backed by a checkpointed LangGraph workflow."""
import threading

import config
from agent.agent import TopologyAgent
from agent.memory import SessionMemory
from agent.persistence import (
    close_interactive_thread,
    get_or_create_interactive_thread,
    load_case_facts,
)
from agent.workflow import build_workflow
from env.case_env import CaseEnv
from langgraph.types import Command


class SessionBusy(RuntimeError):
    """Raised when a reply arrives while the previous one is still being processed."""


class InteractiveDiagnosis:
    """Run the topology graph until it needs human input, then resume it."""

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
        self.judgement = None    # agent's verdict on the last guided-action reply
        self._lock = threading.Lock()
        self.workflow = build_workflow(self.agent, interactive=True)
        thread_id = get_or_create_interactive_thread(case["case_id"])
        self.graph_config = {"configurable": {"thread_id": thread_id}}
        snapshot = self.workflow.get_state(self.graph_config)
        self._started = bool(snapshot and snapshot.values)
        self.resumed = self._started   # an unfinished session for this case was restored
        if self._started:
            self._refresh()

    def _refresh(self):
        snapshot = self.workflow.get_state(self.graph_config)
        if not snapshot or not snapshot.values:
            return
        values = snapshot.values
        if "memory" in values:
            self.memory = SessionMemory.from_dict(values["memory"])
        if "case" in values:
            self.env = CaseEnv(values["case"])
            self.env.trace = list(values.get("trace", []))
            self.env.actions_done = list(values.get("actions_done", []))
            self.env.user.history = list(values.get("user_history", []))
        self.log = values.get("log", self.log)
        self.notes = values.get("notes", self.notes)
        self.step = values.get("step", self.step)
        self.pending = values.get("pending")
        self.result = values.get("result")
        self.judgement = values.get("judgement")
        if self.result is not None:
            close_interactive_thread(
                self.case["case_id"], self.graph_config["configurable"]["thread_id"]
            )

    @property
    def busy(self):
        return self._lock.locked()

    def _run(self, input_value):
        # Streamlit can start a second script run while the first is still inside invoke();
        # two concurrent resumes of the same thread would apply one reply twice.
        if not self._lock.acquire(blocking=False):
            raise SessionBusy("上一条回复仍在处理中，请稍候。")
        try:
            self.workflow.invoke(input_value, config=self.graph_config)
        finally:
            try:
                self._refresh()
            finally:
                self._lock.release()
        return self._interaction_prompt() if self.pending is not None else None

    def start(self):
        """Collect simulated console evidence and continue until a reply is needed."""
        if self._started:
            if self.pending is not None:
                return self._interaction_prompt()
            if self.result is not None:
                return None
            return self.resume()
        self._started = True
        self.memory.historical_facts = load_case_facts(self.case["case_id"])
        return self._run(
            {
                "case": self.env.case,
                "memory": self.memory.to_dict(),
                "trace": self.env.trace,
                "actions_done": self.env.actions_done,
                "user_history": self.env.user.history,
                "log": [],
                "notes": [],
                "step": 0,
                "system": "interactive_topology_agent",
                "persist_history": True,
            }
        )

    def submit(self, answer, resolved=None):
        """Resume the graph with the customer's reply as relayed by staff.

        For a guided action, leave `resolved` as None and the agent judges from the
        reply whether the action fixed the problem; pass True/False only to override.
        """
        if self.busy:
            raise SessionBusy("上一条回复仍在处理中，请稍候。")
        if self.pending is None:
            raise RuntimeError("There is no pending customer question or action.")
        if not answer.strip():
            raise ValueError("Please enter a reply before continuing.")
        return self._run(
            Command(resume={"answer": answer.strip(), "resolved": resolved})
        )

    def resume(self):
        """Retry the interrupted graph node after a transient model/API error."""
        if self.pending is not None or self.result is not None:
            raise RuntimeError("This diagnosis session is not waiting to resume.")
        if not self._started:
            raise RuntimeError("This diagnosis session has not started.")
        return self._run(None)

    def abandon(self):
        """Discard this unfinished session so the next start for the case begins fresh."""
        if self.result is None:
            close_interactive_thread(
                self.case["case_id"], self.graph_config["configurable"]["thread_id"],
                status="abandoned",
            )
        self.pending = None

    def _interaction_prompt(self):
        args = self.pending["args"]
        if self.pending["tool"] == "ask_user":
            return f"建议您向客户确认：{args['question']}\n\n请把客户的回答录入下方。"
        return (
            f"建议您指导客户执行以下操作：\n\n"
            f"{args['action']}\n\n请把客户操作后的反馈原话录入下方，Agent 会判断问题是否已解决。"
        )
