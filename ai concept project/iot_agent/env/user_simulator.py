"""LLM-played customer. It may only use facts listed in the case
(`user_knowledge`, what the app shows, `action_outcomes`) and must not
volunteer the root cause, so every agent faces the same information limits."""
import json

import config
import llm

SYSTEM_TEMPLATE = """You are role-playing a non-technical customer of a home security system who contacted technical support.

Your original complaint: "{complaint}"

Facts you know (use ONLY these):
{knowledge}

What your phone app shows you (device name -> status):
{app_view}

Rules:
- The "support agent" is a human support staff member relaying questions on behalf of their diagnostic assistant.
- Answer the support agent's question briefly (1-2 sentences), in plain everyday language.
- If the answer is not in your facts or app view, say you don't know or can't tell. Never invent technical values (RSSI, firmware numbers, log lines) unless they are listed above.
- Never guess or name the technical root cause yourself.
- If the agent asks several questions at once, answer each that you can.
"""

PERFORM_TEMPLATE = """The support agent asked you to do this: "{action}"

Possible results you know (action -> what happens):
{outcomes}

Pick the result whose action best matches what you were asked to do and report it in 1-2 plain sentences as if you just did it.
If none of them matches, say you did it and that nothing seems to have changed.
Return JSON: {{"matched_action": "<key or none>", "report": "<what you tell the agent>"}}"""


class UserSimulator:
    def __init__(self, case: dict):
        self.case = case
        app_view = {d["name"]: d["status"] for d in case["hidden_state"]["devices"]}
        self.system = SYSTEM_TEMPLATE.format(
            complaint=case["complaint"],
            knowledge=json.dumps(case["user_knowledge"], indent=2, ensure_ascii=False),
            app_view=json.dumps(app_view, indent=2, ensure_ascii=False),
        )
        self.history = []          # dialogue so far, keeps answers consistent

    def answer(self, question: str) -> str:
        self.history.append({"role": "user", "content": f"Support agent: {question}"})
        out = llm.chat([{"role": "system", "content": self.system}, *self.history],
                       model=config.USER_SIM_MODEL, role="user_sim")
        reply = out["content"].strip()
        self.history.append({"role": "assistant", "content": reply})
        return reply

    def perform(self, action: str) -> str:
        prompt = PERFORM_TEMPLATE.format(
            action=action,
            outcomes=json.dumps(self.case["action_outcomes"], indent=2, ensure_ascii=False))
        res = llm.chat_json([{"role": "system", "content": self.system},
                             *self.history, {"role": "user", "content": prompt}],
                            model=config.USER_SIM_MODEL, role="user_sim")
        report = res.get("report", "I did it, nothing seems to have changed.")
        self.history.append({"role": "user", "content": f"Support agent asks you to: {action}"})
        self.history.append({"role": "assistant", "content": report})
        return report
