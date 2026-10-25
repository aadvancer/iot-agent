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
