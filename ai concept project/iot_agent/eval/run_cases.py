"""Run a system on a set of cases and print a per-case summary.
Usage: python -m eval.run_cases [--system topology] [--cases C001 C002 ...]"""
import argparse
import json
import time

import config
import llm
from agent.agent import TopologyAgent
from env.case_env import CaseEnv, load_case

SYSTEMS = {"topology": TopologyAgent}


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
    res["user_turns"] = sum(t["tool"] in ("ask_user", "instruct_user") for t in env.trace)
    res["console_calls"] = sum(t["tool"] not in ("ask_user", "instruct_user", "search_kb") for t in env.trace)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", default="topology", choices=list(SYSTEMS))
    ap.add_argument("--cases", nargs="*")
    a = ap.parse_args()
    case_ids = a.cases or sorted(p.stem for p in config.CASES_DIR.glob("*.json"))
    system = SYSTEMS[a.system]()

    out_dir = config.RESULTS_DIR / "raw" / a.system
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for cid in case_ids:
        r = run_one(system, cid)
        (out_dir / f"{cid}.json").write_text(json.dumps(r, indent=1, ensure_ascii=False), encoding="utf-8")
        rows.append(r)
        print(f"{cid}: pred {r['pred_root_cause']}/{r['pred_tier']}  gt {r['gt_root_cause']}/{r['gt_tier']}  "
              f"cause {'OK' if r['pred_root_cause'] == r['gt_root_cause'] else 'XX'}  "
              f"tier {'OK' if r['pred_tier'] == r['gt_tier'] else 'XX'}  "
              f"| user turns {r['user_turns']}  console {r['console_calls']}  dedup {r['dedup_hits']}  "
              f"| llm {r['llm_calls']} calls {r['tokens']} tok {r['wall_seconds']}s"
              f"{'  [override ' + ','.join(t['rule'] for t in r['triggers']) + ']' if r['tier_overridden'] else ''}")

    n = len(rows)
    acc_c = sum(r["pred_root_cause"] == r["gt_root_cause"] for r in rows) / n
    acc_t = sum(r["pred_tier"] == r["gt_tier"] for r in rows) / n
    print(f"\n[{a.system}] n={n}  root-cause acc {acc_c:.0%}  tier acc {acc_t:.0%}  "
          f"avg user turns {sum(r['user_turns'] for r in rows) / n:.1f}  "
          f"avg tokens {sum(r['tokens'] for r in rows) / n:.0f}")


if __name__ == "__main__":
    main()
