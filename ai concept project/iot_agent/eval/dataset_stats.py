"""Key statistics of the evaluation cases (for the report's Data section).

Usage: python -m eval.dataset_stats
Writes results/dataset_stats.md and results/figures/dataset.png. No API key needed.
The core set (C001-C040) and the challenge set (C041-C052) are always kept apart.
"""
import json
from collections import Counter
from statistics import mean

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import config  # noqa: E402

SPLIT_NAMES = {"core": "Core (C001-C040)", "challenge": "Challenge (C041-C052)"}


def load_cases():
    cases = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(config.CASES_DIR.glob("C*.json"))]
    for case in cases:
        case.setdefault("split", "core")
    return cases


def split_stats(cases):
    """Per-split counts and average scenario size (what the agent has to sift through)."""
    tiers = Counter(c["gt_tier"] for c in cases)
    diffs = Counter(c["difficulty"] for c in cases)
    return {
        "cases": len(cases),
        "root_cause_labels": len({c["gt_root_cause"] for c in cases}),
        "L1": tiers.get("L1", 0),
        "L2": tiers.get("L2", 0),
        "easy": diffs.get("easy", 0),
        "medium": diffs.get("medium", 0),
        "hard": diffs.get("hard", 0),
        "requires_interaction": sum(bool(c.get("requires_interaction")) for c in cases),
        "avg_complaint_words": mean(len(c["complaint"].split()) for c in cases),
        "avg_devices": mean(len(c["hidden_state"]["devices"]) for c in cases),
        "avg_log_lines": mean(len(c["hidden_state"]["logs"]) for c in cases),
        "avg_customer_facts": mean(len(c.get("user_knowledge", {})) for c in cases),
        "avg_action_outcomes": mean(len(c.get("action_outcomes", {})) for c in cases),
        "avg_key_checks": mean(len(c.get("gt_key_checks", [])) for c in cases),
    }


def stats_markdown(cases):
    by_split = {s: [c for c in cases if c["split"] == s] for s in SPLIT_NAMES}
    by_split = {s: rows for s, rows in by_split.items() if rows}
    stats = {s: split_stats(rows) for s, rows in by_split.items()}
    rows = [
        ("Cases", "cases", "{:d}"), ("Distinct root-cause labels", "root_cause_labels", "{:d}"),
        ("L1 (frontline) / L2 (FAE)", None, None),
        ("Easy / medium / hard", None, None),
        ("Requires customer interaction", "requires_interaction", "{:d}"),
        ("Complaint length (words, mean)", "avg_complaint_words", "{:.1f}"),
        ("Devices per household (mean)", "avg_devices", "{:.1f}"),
        ("Log lines per case (mean)", "avg_log_lines", "{:.1f}"),
        ("Customer facts per case (mean)", "avg_customer_facts", "{:.1f}"),
        ("Scripted action outcomes per case (mean)", "avg_action_outcomes", "{:.1f}"),
        ("Ground-truth key checks per case (mean)", "avg_key_checks", "{:.1f}"),
    ]
    lines = ["## Case statistics", "", "| Statistic | " + " | ".join(SPLIT_NAMES[s] for s in stats) + " |",
             "|---|" + "---|" * len(stats)]
    for label, key, fmt in rows:
        if label.startswith("L1"):
            cells = [f"{v['L1']} / {v['L2']}" for v in stats.values()]
        elif label.startswith("Easy"):
            cells = [f"{v['easy']} / {v['medium']} / {v['hard']}" for v in stats.values()]
        else:
            cells = [fmt.format(v[key]) for v in stats.values()]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")

    causes = sorted({c["gt_root_cause"] for c in cases})
    tier_of = {c["gt_root_cause"]: c["gt_tier"] for c in cases if c["split"] == "core"}
    lines += ["", "## Root-cause label distribution", "",
              "| Root cause | Core tier | " + " | ".join(SPLIT_NAMES[s] for s in by_split) + " |",
              "|---|---|" + "---|" * len(by_split)]
    for cause in causes:
        counts = [sum(c["gt_root_cause"] == cause for c in by_split[s]) for s in by_split]
        lines.append(f"| {cause} | {tier_of.get(cause, '—')} | " + " | ".join(map(str, counts)) + " |")
    return "\n".join(lines) + "\n", by_split


def write_figure(by_split):
    causes = sorted({c["gt_root_cause"] for rows in by_split.values() for c in rows})
    fig, ax = plt.subplots(figsize=(9, 0.38 * len(causes) + 1.2))
    left = [0] * len(causes)
    for split, color in zip(by_split, ["#9aa5b1", "#d1495b"]):
        counts = [sum(c["gt_root_cause"] == cause for c in by_split[split]) for cause in causes]
        ax.barh(causes, counts, left=left, color=color, label=SPLIT_NAMES[split])
        left = [a + b for a, b in zip(left, counts)]
    ax.invert_yaxis()
    ax.set_xlabel("Cases")
    ax.set_title("Root-cause label distribution", fontsize=10)
    ax.legend(fontsize=8)
    ax.tick_params(axis="y", labelsize=8)
    fig.tight_layout()
    fig_dir = config.RESULTS_DIR / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(fig_dir / "dataset.png", dpi=160)
    plt.close(fig)


def main():
    cases = load_cases()
    if not cases:
        raise SystemExit(f"No cases found in {config.CASES_DIR}")
    text, by_split = stats_markdown(cases)
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (config.RESULTS_DIR / "dataset_stats.md").write_text(text, encoding="utf-8")
    write_figure(by_split)
    print(text)
    print(f"[dataset] wrote {config.RESULTS_DIR / 'dataset_stats.md'} and figures/dataset.png")


if __name__ == "__main__":
    main()
