"""Blind human rating of support responses, to validate the LLM usability judge.

  python -m eval.human_rating export [--cases-per-split 3 2] [--seed 0]
      writes results/human_rating/sheet.csv (blind: no system name, no judge score)
      and key.json (item -> system, judge score). Fill the `human_score` column (1-5)
      using the same rubric as the judge: clarity, politeness, actionability, and no
      claims of checks/fixes that the session record does not show.
  python -m eval.human_rating agree
      compares the filled sheet with the judge: exact / within-1 agreement, Spearman
      rank correlation, and mean human vs judge score per system.
"""
import argparse
import csv
import json
import random
from statistics import mean

import config
from eval.metrics import _session_record
from eval.report import SYSTEMS, load_rows

RATED_SYSTEMS = ("topology", "react", "vanilla_rag")
OUT_DIR = config.RESULTS_DIR / "human_rating"
FIELDS = ["item", "case_id", "complaint", "session_record", "response", "human_score", "comment"]


def export(cases_per_split=(3, 2), seed=0):
    rows = load_rows({s: SYSTEMS[s] for s in RATED_SYSTEMS})
    missing = [s for s in RATED_SYSTEMS if s not in rows]
    if missing:
        raise SystemExit(f"No saved results for {missing}; run eval.run_cases first.")
    by_case = {s: {r["case_id"]: r for r in rs} for s, rs in rows.items()}
    shared = set.intersection(*(set(v) for v in by_case.values()))
    rng = random.Random(seed)
    chosen = []
    for split, k in zip(("core", "challenge"), cases_per_split):
        pool = sorted(c for c in shared if by_case["topology"][c]["split"] == split)
        # stratify by tier so frontline replies and escalation tickets are both rated
        for tier in ("L1", "L2"):
            tier_pool = [c for c in pool if by_case["topology"][c]["gt_tier"] == tier]
            chosen += rng.sample(tier_pool, min(len(tier_pool), (k + (tier == "L1")) // 2))
    items = [(c, s) for c in sorted(chosen) for s in RATED_SYSTEMS]
    rng.shuffle(items)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    key = {}
    with (OUT_DIR / "sheet.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        for i, (case_id, system) in enumerate(items, 1):
            row = by_case[system][case_id]
            item = f"H{i:02d}"
            key[item] = {"system": system, "case_id": case_id, "judge_score": row.get("usability_score")}
            w.writerow({"item": item, "case_id": case_id, "complaint": row.get("complaint", ""),
                        "session_record": _session_record(row),
                        "response": json.dumps(row.get("output", {}), ensure_ascii=False, indent=1),
                        "human_score": "", "comment": ""})
    (OUT_DIR / "key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    print(f"[human] {len(items)} items ({len(chosen)} cases x {len(RATED_SYSTEMS)} systems) -> {OUT_DIR / 'sheet.csv'}")


def _ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1   # average rank for ties
        i = j + 1
    return ranks


def spearman(x, y):
    """Spearman rank correlation with tie-averaged ranks (Pearson on ranks)."""
    rx, ry = _ranks(x), _ranks(y)
    mx, my = mean(rx), mean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sx = sum((a - mx) ** 2 for a in rx) ** 0.5
    sy = sum((b - my) ** 2 for b in ry) ** 0.5
    return cov / (sx * sy) if sx and sy else float("nan")


def agreement(pairs):
    """pairs: [(system, human, judge)] -> summary dict."""
    human = [h for _, h, _ in pairs]
    judge = [j for _, _, j in pairs]
    per_system = {}
    for system, h, j in pairs:
        per_system.setdefault(system, []).append((h, j))
    return {
        "items": len(pairs),
        "exact": sum(h == j for h, j in zip(human, judge)) / len(pairs),
        "within_1": sum(abs(h - j) <= 1 for h, j in zip(human, judge)) / len(pairs),
        "spearman": spearman(human, judge),
        "per_system": {s: (mean(h for h, _ in v), mean(j for _, j in v)) for s, v in per_system.items()},
    }


def agree():
    key = json.loads((OUT_DIR / "key.json").read_text(encoding="utf-8"))
    pairs = []
    with (OUT_DIR / "sheet.csv").open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            score = row["human_score"].strip()
            judge = key[row["item"]]["judge_score"]
            if score and judge is not None:
                if score not in {"1", "2", "3", "4", "5"}:
                    raise SystemExit(f"{row['item']}: human_score must be 1-5, got {score!r}")
                pairs.append((key[row["item"]]["system"], int(score), judge))
    if not pairs:
        raise SystemExit("No human scores yet: fill the human_score column of sheet.csv.")
    s = agreement(pairs)
    lines = ["## Human vs LLM-judge usability", "",
             f"{s['items']} blind items. Exact agreement {s['exact']:.0%}, within one point {s['within_1']:.0%}, "
             f"Spearman rho {s['spearman']:.2f}.", "",
             "| System | Human mean | Judge mean |", "|---|---|---|"]
    lines += [f"| {SYSTEMS[sys]} | {h:.2f} | {j:.2f} |" for sys, (h, j) in s["per_system"].items()]
    text = "\n".join(lines) + "\n"
    (OUT_DIR / "agreement.md").write_text(text, encoding="utf-8")
    print(text)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("export")
    ex.add_argument("--cases-per-split", nargs=2, type=int, default=[3, 2], metavar=("CORE", "CHALLENGE"))
    ex.add_argument("--seed", type=int, default=0)
    sub.add_parser("agree")
    a = ap.parse_args()
    if a.cmd == "export":
        export(tuple(a.cases_per_split), a.seed)
    else:
        agree()


if __name__ == "__main__":
    main()
