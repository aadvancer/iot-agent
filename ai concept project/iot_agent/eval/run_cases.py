"""Run a system on a set of cases and print a per-case summary.
Usage: python -m eval.run_cases [--system topology] [--cases C001 C002 ...]"""
import argparse
import json
import time

import config
import llm
from agent.agent import TopologyAgent
from env.case_env import CaseEnv, load_case
from eval.baselines import VanillaLLM, VanillaRAG
from eval.metrics import calculate_metrics, judge_usability

SYSTEMS = {
    "topology": TopologyAgent,
    "vanilla_llm": VanillaLLM,
    "vanilla_rag": VanillaRAG,
}


def run_one(system, case_id):
    case = load_case(case_id)
    env = CaseEnv(case)
    before = (llm.USAGE.calls, llm.USAGE.prompt_tokens, llm.USAGE.completion_tokens)
    t0 = time.time()
    res = system.run(env)
    res["wall_seconds"] = round(time.time() - t0, 1)
    res["llm_calls"] = llm.USAGE.calls - before[0]
    res["tokens"] = (llm.USAGE.prompt_tokens - before[1]) + (llm.USAGE.completion_tokens - before[2])
    res["gt_root_cause"], res["gt_tier"] = case["gt_root_cause"], case["gt_tier"]
    res["complaint"] = case["complaint"]
    res["user_turns"] = sum(t["tool"] in ("ask_user", "instruct_user") for t in env.trace)
    res["console_calls"] = sum(t["tool"] not in ("ask_user", "instruct_user", "search_kb") for t in env.trace)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", default="topology", choices=list(SYSTEMS))
    ap.add_argument("--cases", nargs="*")
    ap.add_argument("--judge-usability", action="store_true",
                    help="Use the configured judge model to score each response from 1 to 5.")
    a = ap.parse_args()
    case_ids = a.cases or sorted(p.stem for p in config.CASES_DIR.glob("*.json"))
    system = SYSTEMS[a.system]()

    out_dir = config.RESULTS_DIR / "raw" / a.system
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for cid in case_ids:
        r = run_one(system, cid)
        if a.judge_usability:
            judged = judge_usability(r)
            r["usability_score"] = judged["score"]
            r["usability_reason"] = judged["reason"]
        (out_dir / f"{cid}.json").write_text(json.dumps(r, indent=1, ensure_ascii=False), encoding="utf-8")
        rows.append(r)
        print(f"{cid}: pred {r['pred_root_cause']}/{r['pred_tier']}  gt {r['gt_root_cause']}/{r['gt_tier']}  "
              f"cause {'OK' if r['pred_root_cause'] == r['gt_root_cause'] else 'XX'}  "
              f"tier {'OK' if r['pred_tier'] == r['gt_tier'] else 'XX'}  "
              f"| user turns {r['user_turns']}  console {r['console_calls']}  dedup {r['dedup_hits']}  "
              f"| llm {r['llm_calls']} calls {r['tokens']} tok {r['wall_seconds']}s"
              f"{'  [override ' + ','.join(t['rule'] for t in r['triggers']) + ']' if r['tier_overridden'] else ''}")

    metrics = calculate_metrics(rows)
    summary = {
        "system": a.system,
        **metrics,
        "average_tokens": sum(r["tokens"] for r in rows) / len(rows),
    }
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    usability = (
        f"{metrics['support_usability_score']:.2f}/5"
        if metrics["support_usability_score"] is not None else "not scored"
    )
    print(
        f"\n[{a.system}] n={metrics['case_count']}  "
        f"diagnosis success {metrics['diagnosis_success_rate']:.0%}  "
        f"tier accuracy {metrics['fault_classification_accuracy']:.0%}  "
        f"avg interaction rounds {metrics['average_interaction_rounds']:.1f}  "
        f"redundant inquiry rate {metrics['redundant_inquiry_rate']:.0%}  "
        f"usability {usability}  avg tokens {summary['average_tokens']:.0f}"
    )
    print(f"[metrics] saved to {summary_path}")


if __name__ == "__main__":
    main()
