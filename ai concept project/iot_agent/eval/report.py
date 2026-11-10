"""Aggregate saved runs into a comparison table and figures for the report.

Usage: python -m eval.report
Reads results/raw/<system>/C*.json (written by eval.run_cases) and writes
  results/comparison.md, results/comparison.csv and results/figures/*.png.
The core set and the author-written challenge set are reported separately;
challenge figures carry a "_challenge" suffix. Saved runs of the ablation variants
(abl_*) are summarised in extra "Ablation" tables and figures/ablation*.png.
Each split also gets a "Statistical check" table (95% Wilson CIs and exact McNemar
tests vs the topology agent, see eval/stats.py), a "Repeated runs" table when
results/repeats/<system>/run<N> exist (eval.run_cases --run N), a "Cost breakdown"
table and an "Error analysis" table that lists every wrong prediction per system.
"""
import csv
import json
from statistics import mean, stdev

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import config  # noqa: E402
from eval.metrics import calculate_metrics  # noqa: E402
from eval.stats import mcnemar_exact, paired_outcomes, wilson_ci  # noqa: E402

REFERENCE = "topology"   # system the significance tests compare every baseline against

# display order and labels; systems without saved results are skipped
SYSTEMS = {
    "vanilla_llm": "Vanilla LLM",
    "vanilla_rag": "Vanilla RAG",
    "rules_only": "Rules only (no LLM)",
    "react": "ReAct (same tools)",
    "topology": "Topology agent (ours)",
}
# topology-agent variants with one component removed (agent/agent.py ABLATIONS)
ABLATIONS = {
    "topology": "Full agent",
    "abl_no_planner": "- topology planner",
    "abl_no_hints": "- rule hints",
    "abl_no_memory": "- structured memory",
    "abl_no_override": "- rule tier override",
}
DIFFICULTIES = ["easy", "medium", "hard"]
SPLITS = {
    "core": "Core set (C001-C040)",
    "challenge": "Challenge set (C041-C052, author-written shortcut probes; report separately)",
}


def _cases():
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in config.CASES_DIR.glob("C*.json")}


def load_rows_from(directory, cases=None):
    """Saved per-case results in one directory, tagged with the case's difficulty and split."""
    cases = cases if cases is not None else _cases()
    rows = []
    for path in sorted(directory.glob("C*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        case = cases.get(row["case_id"], {})
        row["difficulty"] = case.get("difficulty", "")
        row["split"] = case.get("split", "core")
        rows.append(row)
    return rows


def load_rows(systems=SYSTEMS):
    cases = _cases()
    out = {}
    for system in systems:
        rows = load_rows_from(config.RESULTS_DIR / "raw" / system, cases)
        if rows:
            out[system] = rows
    return out


def escalation_scores(rows):
    """L2 = escalate to FAE. Precision: escalations that were needed; recall: needed ones caught."""
    tp = sum(r["pred_tier"] == "L2" and r["gt_tier"] == "L2" for r in rows)
    fp = sum(r["pred_tier"] == "L2" and r["gt_tier"] == "L1" for r in rows)
    fn = sum(r["pred_tier"] == "L1" and r["gt_tier"] == "L2" for r in rows)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return precision, recall, fp, fn


def executed_repeats(row):
    """Console queries / questions that were sent again with identical arguments."""
    seen, repeats = set(), 0
    for event in row.get("trace", []):
        if event.get("tool") == "instruct_user":
            continue
        key = (event.get("tool"), json.dumps(event.get("args", {}), sort_keys=True).casefold())
        repeats += key in seen
        seen.add(key)
    return repeats


def summarize(rows):
    m = calculate_metrics(rows)
    precision, recall, fp, fn = escalation_scores(rows)
    n = len(rows)
    by_diff = {}
    for d in DIFFICULTIES:
        sub = [r for r in rows if r["difficulty"] == d]
        by_diff[d] = sum(r["pred_root_cause"] == r["gt_root_cause"] for r in sub) / len(sub) if sub else None
    return {
        "cases": n,
        "root_cause_acc": m["diagnosis_success_rate"],
        "tier_acc": m["fault_classification_accuracy"],
        "l2_precision": precision,
        "l2_recall": recall,
        "unneeded_escalations": fp,
        "missed_escalations": fn,
        "avg_customer_rounds": m["average_interaction_rounds"],
        "redundant_inquiry_rate": m["redundant_inquiry_rate"],
        "avg_repeated_tool_calls": sum(r.get("dedup_hits", 0) for r in rows) / n,
        "usability": m["support_usability_score"],
        "avg_llm_calls": sum(r.get("llm_calls", 0) for r in rows) / n,
        "avg_tokens": sum(r.get("tokens", 0) for r in rows) / n,
        "avg_seconds": sum(r.get("llm_seconds", r.get("wall_seconds", 0)) for r in rows) / n,
        "tier_overrides": sum(bool(r.get("tier_overridden")) for r in rows),
        **{f"acc_{d}": v for d, v in by_diff.items()},
    }


def _pct(v):
    return "—" if v is None else f"{v:.0%}"


def _cause_ok(r):
    return r["pred_root_cause"] == r["gt_root_cause"]


def _tier_ok(r):
    return r["pred_tier"] == r["gt_tier"]


def _ci_cell(rows, key):
    k, n = sum(key(r) for r in rows), len(rows)
    lo, hi = wilson_ci(k, n)
    return f"{k}/{n} = {k / n:.0%} [{lo:.0%}, {hi:.0%}]"


def significance_table(rows_by_system):
    """Accuracy with 95% Wilson CI, and exact McNemar tests of our agent vs each other system."""
    lines = ["| System | Root-cause acc [95% CI] | Tier acc [95% CI] "
             "| Root cause: ours-only / baseline-only correct | p (McNemar) "
             "| Tier: ours-only / baseline-only correct | p (McNemar) |",
             "|---|---|---|---|---|---|---|"]
    ref = rows_by_system.get(REFERENCE)
    for system, rows in rows_by_system.items():
        cells = [SYSTEMS[system], _ci_cell(rows, _cause_ok), _ci_cell(rows, _tier_ok)]
        for key in (_cause_ok, _tier_ok):
            if ref is None or system == REFERENCE:
                cells += ["—", "—"]
                continue
            ours, theirs = paired_outcomes(ref, rows, key)
            cells += [f"{ours} / {theirs}", f"{mcnemar_exact(ours, theirs):.3f}"]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def error_table(rows_by_system):
    """Every misdiagnosed or mis-tiered case per system, as `case: predicted -> truth`."""
    lines = ["| System | Wrong root cause (pred → truth) | Wrong tier (pred → truth) |", "|---|---|---|"]
    for system, rows in rows_by_system.items():
        rows = sorted(rows, key=lambda r: r["case_id"])
        causes = [f"{r['case_id']}: {r['pred_root_cause']} → {r['gt_root_cause']}"
                  for r in rows if not _cause_ok(r)]
        tiers = [f"{r['case_id']}: {r['pred_tier']} → {r['gt_tier']}" for r in rows if not _tier_ok(r)]
        lines.append(f"| {SYSTEMS[system]} | {'<br>'.join(causes) or 'none'} | {'<br>'.join(tiers) or 'none'} |")
    return lines


def cost_breakdown_table(rows_by_system):
    """Where the tokens go: mean tool usage per case and prompt size per LLM call."""
    lines = ["| System | Console queries | KB searches | Customer questions | Guided actions "
             "| LLM calls | Tokens / LLM call | Tokens / case |",
             "|---|---|---|---|---|---|---|---|"]
    for system, rows in rows_by_system.items():
        n = len(rows)

        def per_case(tools):
            return sum(t.get("tool") in tools for r in rows for t in r.get("trace", [])) / n

        calls = sum(r.get("llm_calls", 0) for r in rows)
        tokens = sum(r.get("tokens", 0) for r in rows)
        lines.append(
            f"| {SYSTEMS.get(system, ABLATIONS.get(system, system))} | "
            f"{per_case({'get_base_status', 'get_topology', 'get_device_info', 'check_firmware_compat', 'get_logs'}):.1f} | "
            f"{per_case({'search_kb'}):.1f} | {per_case({'ask_user'}):.2f} | {per_case({'instruct_user'}):.2f} | "
            f"{calls / n:.1f} | {tokens / calls if calls else 0:.0f} | {tokens / n:.0f} |")
    return lines


def load_repeats():
    """{system: {run_index: rows}}; run 1 is results/raw, later runs results/repeats/<system>/run<N>."""
    base = config.RESULTS_DIR / "repeats"
    out = {}
    for system_dir in sorted(p for p in base.glob("*") if p.is_dir()) if base.exists() else []:
        runs = {}
        for run_dir in sorted(system_dir.glob("run*")):
            rows = load_rows_from(run_dir)
            if rows:
                runs[int(run_dir.name[3:])] = rows
        first = load_rows_from(config.RESULTS_DIR / "raw" / system_dir.name)
        if runs and first:
            out[system_dir.name] = {1: first, **runs}
    return out


def repeat_table(runs_by_system, split):
    """Mean ± sample sd over repeated runs, and cases whose prediction changed between runs."""
    lines = ["| System | Runs | Root-cause acc per run | Mean ± sd | Tier acc per run | Mean ± sd "
             "| Tokens / case (mean) | Cases with unstable root cause |",
             "|---|---|---|---|---|---|---|---|"]
    for system, runs in runs_by_system.items():
        split_runs = {i: [r for r in rows if r["split"] == split] for i, rows in sorted(runs.items())}
        split_runs = {i: rows for i, rows in split_runs.items() if rows}
        if len(split_runs) < 2:
            continue
        cause = [sum(map(_cause_ok, rows)) / len(rows) for rows in split_runs.values()]
        tier = [sum(map(_tier_ok, rows)) / len(rows) for rows in split_runs.values()]
        tokens = mean(sum(r.get("tokens", 0) for r in rows) / len(rows) for rows in split_runs.values())
        preds = {}
        for rows in split_runs.values():
            for r in rows:
                preds.setdefault(r["case_id"], set()).add(r["pred_root_cause"])
        unstable = sorted(c for c, p in preds.items() if len(p) > 1)
        lines.append(
            f"| {SYSTEMS[system]} | {len(split_runs)} | {' / '.join(_pct(v) for v in cause)} | "
            f"{mean(cause):.1%} ± {stdev(cause):.1%} | {' / '.join(_pct(v) for v in tier)} | "
            f"{mean(tier):.1%} ± {stdev(tier):.1%} | {tokens:.0f} | {', '.join(unstable) or 'none'} |")
    return lines if len(lines) > 2 else []


def analysis_sections(rows_by_split):
    """Significance and error-analysis sections for comparison.md (one block per split)."""
    lines = []
    repeats = load_repeats()
    for split, rows_by_system in rows_by_split.items():
        lines += ["", f"## Statistical check: {SPLITS[split]}", "",
                  "Run 1 of each system. 95% Wilson intervals; exact two-sided McNemar test on paired "
                  "per-case outcomes vs the topology agent (p < 0.05 = difference unlikely to be chance).", ""]
        lines += significance_table(rows_by_system)
        rep = repeat_table(repeats, split)
        if rep:
            lines += ["", f"## Repeated runs: {SPLITS[split]}", "",
                      "Identical settings (temperature 0); runs 2+ use a separate LLM cache namespace, so the spread "
                      "is the run-to-run variation of the model and the simulated customer.", ""] + rep
        lines += ["", f"## Cost breakdown: {SPLITS[split]}", ""] + cost_breakdown_table(rows_by_system)
        lines += ["", f"## Error analysis: {SPLITS[split]}", ""] + error_table(rows_by_system)
    return lines


def write_tables(summaries, rows_by_split=None):
    out = config.RESULTS_DIR
    cols = list(next(iter(next(iter(summaries.values())).values())))
    with (out / "comparison.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["split", "system", *cols])
        for split, summary in summaries.items():
            for system, s in summary.items():
                w.writerow([split, system, *[s[c] if s[c] is None else round(s[c], 4) for c in cols]])

    lines = []
    for split, summary in summaries.items():
        if lines:
            lines.append("")
        lines += [f"## {SPLITS[split]}", ""] + _split_table(summary)
    if rows_by_split:
        lines += analysis_sections(rows_by_split)
    (out / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def ablation_table(rows_by_variant):
    lines = ["| Variant | Cases | Root-cause acc | Tier acc | L2 precision | L2 recall | Unneeded / missed escalations "
             "| Tier overrides | Customer rounds | Repeated queries blocked / executed | LLM calls | Tokens |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for variant, rows in rows_by_variant.items():
        s = summarize(rows)
        blocked = sum(r.get("dedup_hits", 0) for r in rows) / len(rows)
        executed = sum(executed_repeats(r) for r in rows) / len(rows)
        lines.append(
            f"| {ABLATIONS[variant]} | {s['cases']} | {_pct(s['root_cause_acc'])} | {_pct(s['tier_acc'])} | "
            f"{_pct(s['l2_precision'])} | {_pct(s['l2_recall'])} | "
            f"{s['unneeded_escalations']} / {s['missed_escalations']} | {s['tier_overrides']} | "
            f"{s['avg_customer_rounds']:.2f} | {blocked:.2f} / {executed:.2f} | "
            f"{s['avg_llm_calls']:.1f} | {s['avg_tokens']:.0f} |")
    return lines


def write_ablation_figure(rows_by_variant, suffix=""):
    names = [ABLATIONS[v] for v in rows_by_variant]
    summary = {v: summarize(rows) for v, rows in rows_by_variant.items()}
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))
    _bar(axes[0], names, [summary[v]["root_cause_acc"] for v in summary], "Root-cause accuracy", ylim=(0, 1.12))
    _bar(axes[1], names, [summary[v]["tier_acc"] for v in summary], "L1/L2 tier accuracy", ylim=(0, 1.12))
    _bar(axes[2], names, [summary[v]["avg_tokens"] for v in summary], "Tokens per case", "{:.0f}")
    for bars in (axes[0].patches, axes[1].patches, axes[2].patches):
        for i, bar in enumerate(bars):
            bar.set_color("#d1495b" if i == 0 else "#9aa5b1")
    fig.tight_layout()
    fig.savefig(config.RESULTS_DIR / "figures" / f"ablation{suffix}.png", dpi=160)
    plt.close(fig)


def _split_table(summary):
    lines = ["| System | Root-cause acc | Tier acc | L2 precision | L2 recall | Unneeded / missed escalations "
             "| Customer rounds | Usability (1-5) | LLM calls | Tokens | Seconds |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for system, s in summary.items():
        usability = "—" if s["usability"] is None else f"{s['usability']:.2f}"
        lines.append(
            f"| {SYSTEMS[system]} | {_pct(s['root_cause_acc'])} | {_pct(s['tier_acc'])} | "
            f"{_pct(s['l2_precision'])} | {_pct(s['l2_recall'])} | "
            f"{s['unneeded_escalations']} / {s['missed_escalations']} | {s['avg_customer_rounds']:.2f} | "
            f"{usability} | {s['avg_llm_calls']:.1f} | {s['avg_tokens']:.0f} | {s['avg_seconds']:.1f} |")
    diffs = [d for d in DIFFICULTIES if any(s[f"acc_{d}"] is not None for s in summary.values())]
    if len(diffs) < 2:
        return lines
    lines += ["", "| System | " + " | ".join(f"Acc ({d})" for d in diffs) + " | Tier overrides by R1-R5 |",
              "|---|" + "---|" * (len(diffs) + 1)]
    for system, s in summary.items():
        lines.append(f"| {SYSTEMS[system]} | " + " | ".join(_pct(s[f'acc_{d}']) for d in diffs)
                     + f" | {s['tier_overrides']} |")
    return lines


def _bar(ax, labels, values, title, fmt="{:.0%}", ylim=None):
    bars = ax.bar(labels, values, color=["#9aa5b1"] * (len(labels) - 1) + ["#d1495b"])
    ax.set_title(title, fontsize=10)
    if ylim:
        ax.set_ylim(*ylim)
    for b, v in zip(bars, values):
        ax.annotate(fmt.format(v), (b.get_x() + b.get_width() / 2, b.get_height()),
                    ha="center", va="bottom", fontsize=8)
    ax.tick_params(axis="x", labelrotation=25, labelsize=8)


def write_figures(summary, rows_by_system, suffix=""):
    fig_dir = config.RESULTS_DIR / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    names = [SYSTEMS[s] for s in summary]

    fig, axes = plt.subplots(1, 4, figsize=(15, 3.8))
    for ax, key, title in zip(axes, ["root_cause_acc", "tier_acc", "l2_precision", "l2_recall"],
                              ["Root-cause accuracy", "L1/L2 tier accuracy",
                               "Escalation precision (L2)", "Escalation recall (L2)"]):
        _bar(ax, names, [summary[s][key] for s in summary], title, ylim=(0, 1.12))
    fig.tight_layout()
    fig.savefig(fig_dir / f"accuracy{suffix}.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
    _bar(axes[0], names, [summary[s]["avg_llm_calls"] for s in summary], "LLM calls per case", "{:.1f}")
    _bar(axes[1], names, [summary[s]["avg_tokens"] for s in summary], "Tokens per case", "{:.0f}")
    _bar(axes[2], names, [summary[s]["avg_seconds"] for s in summary], "Model seconds per case", "{:.1f}")
    fig.tight_layout()
    fig.savefig(fig_dir / f"cost{suffix}.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))
    _bar(axes[0], names, [summary[s]["usability"] or 0 for s in summary],
         "Support usability (judge, 1-5)", "{:.2f}", ylim=(0, 5.4))
    _bar(axes[1], names, [summary[s]["avg_customer_rounds"] for s in summary],
         "Customer interaction rounds per case", "{:.2f}")
    fig.tight_layout()
    fig.savefig(fig_dir / f"usability_interaction{suffix}.png", dpi=160)
    plt.close(fig)

    diffs = [d for d in DIFFICULTIES if any(summary[s][f"acc_{d}"] is not None for s in summary)]
    if len(diffs) >= 2:
        fig, ax = plt.subplots(figsize=(7, 3.8))
        width = 0.8 / len(summary)
        for i, system in enumerate(summary):
            vals = [summary[system][f"acc_{d}"] or 0 for d in diffs]
            ax.bar([x + i * width for x in range(len(diffs))], vals, width, label=SYSTEMS[system])
        ax.set_xticks([x + width * (len(summary) - 1) / 2 for x in range(len(diffs))], diffs)
        ax.set_ylim(0, 1.1)
        ax.set_title("Root-cause accuracy by case difficulty", fontsize=10)
        ax.legend(fontsize=7, loc="lower left")
        fig.tight_layout()
        fig.savefig(fig_dir / f"accuracy_by_difficulty{suffix}.png", dpi=160)
        plt.close(fig)

    causes = sorted({r["gt_root_cause"] for rows in rows_by_system.values() for r in rows})
    fig, ax = plt.subplots(figsize=(9, 0.42 * len(causes) + 1.2))
    grid = []
    for cause in causes:
        row = []
        for system in summary:
            sub = [r for r in rows_by_system[system] if r["gt_root_cause"] == cause]
            row.append(sum(r["pred_root_cause"] == cause for r in sub) / len(sub) if sub else float("nan"))
        grid.append(row)
    im = ax.imshow(grid, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(summary)), names, rotation=25, ha="right", fontsize=8)
    ax.set_yticks(range(len(causes)), causes, fontsize=8)
    for i, row in enumerate(grid):
        for j, v in enumerate(row):
            ax.text(j, i, f"{v:.0%}", ha="center", va="center", fontsize=7)
    ax.set_title("Root-cause accuracy per label", fontsize=10)
    fig.colorbar(im, ax=ax, fraction=0.03)
    fig.tight_layout()
    fig.savefig(fig_dir / f"accuracy_by_cause{suffix}.png", dpi=160)
    plt.close(fig)


def main():
    rows_by_system = load_rows()
    if not rows_by_system:
        raise SystemExit("No saved results. Run python -m eval.run_cases --system <name> first.")
    summaries, rows_by_split = {}, {}
    for split in SPLITS:
        split_rows = {s: [r for r in rows if r["split"] == split] for s, rows in rows_by_system.items()}
        split_rows = {s: rows for s, rows in split_rows.items() if rows}
        if not split_rows:
            continue
        summary = {s: summarize(rows) for s, rows in split_rows.items()}
        sizes = {s: v["cases"] for s, v in summary.items()}
        if len(set(sizes.values())) > 1:
            print(f"[warning] {split}: systems were run on different numbers of cases: {sizes}")
        summaries[split] = summary
        rows_by_split[split] = split_rows
        write_figures(summary, split_rows, "" if split == "core" else f"_{split}")
    write_tables(summaries, rows_by_split)

    variants = load_rows(ABLATIONS)
    if len(variants) > 1:
        lines = []
        for split in SPLITS:
            split_rows = {v: [r for r in rows if r["split"] == split] for v, rows in variants.items()}
            split_rows = {v: rows for v, rows in split_rows.items() if rows}
            if len(split_rows) < 2:
                continue
            lines += ["", f"## Ablation: {SPLITS[split]}", ""] + ablation_table(split_rows)
            write_ablation_figure(split_rows, "" if split == "core" else f"_{split}")
        with (config.RESULTS_DIR / "comparison.md").open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    print((config.RESULTS_DIR / "comparison.md").read_text(encoding="utf-8"))
    print(f"[report] figures in {config.RESULTS_DIR / 'figures'}")


if __name__ == "__main__":
    main()
