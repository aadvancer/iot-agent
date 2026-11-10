"""Blind human rating of support responses, to validate the LLM usability judge (v2).

  python -m eval.human_rating export [--cases C005 C015 ...] [--seed 0]
      writes results/human_rating/rating_sheet.xlsx and key.json. The sheet groups the
      three systems' responses to the same case as A / B / C (order shuffled per case,
      system names hidden), shows the console facts and what each agent asked, and asks
      for three 1-5 scores (clarity, actionability, grounding) plus a 1-3 rank per case.
  python -m eval.human_rating agree
      reads the filled sheet: per-system scores and mean rank, pairwise preference of our
      agent over each other system, and agreement with the LLM judge
      (exact / within-1 / Spearman on the mean of the three scores).

v1 (a single 1-5 score per response in a CSV) is kept as sheet_v1.csv / key_v1.json /
agreement_v1.md; it showed ceiling effects, which this design addresses.
"""
import argparse
import json
import random
from statistics import mean

import config
from eval.metrics import _session_record
from eval.report import SYSTEMS, load_rows
from eval.stats import mcnemar_exact

RATED_SYSTEMS = ("topology", "react", "vanilla_rag")
OUT_DIR = config.RESULTS_DIR / "human_rating"
SHEET = OUT_DIR / "rating_sheet.xlsx"
KEY = OUT_DIR / "key.json"
# v1 cases (stratified by split and tier) plus the two rule-hard cases that need dialogue
DEFAULT_CASES = ("C005", "C015", "C016", "C046", "C051", "C041", "C050")
CRITERIA = ("clarity", "actionability", "grounding")
RUBRIC = [
    ("Clarity", "Could a frontline staff member understand the response at once?",
     "1 = confusing or contradictory · 3 = understandable with effort · 5 = immediately clear"),
    ("Actionability", "Does it say exactly what to do next?",
     "1 = no concrete next step · 3 = some steps vague or missing · 5 = complete, concrete repair steps "
     "(L1) or a complete FAE ticket (L2)"),
    ("Grounding", "Is every claim backed by the complaint, the console facts or the customer's replies?",
     "1 = key claims contradict or are absent from the evidence · 3 = mostly supported, some gaps · "
     "5 = every claim is supported; no invented checks or results"),
    ("Rank", "Within each case, rank the three responses (1 = most useful for the staff member).",
     "Use 1, 2 and 3 once each; no ties"),
]


# ------------------------------------------------------------------ rendering
def render_output(output):
    """A response as plain text a rater can read (instead of raw JSON)."""
    if isinstance(output, str):
        return output
    parts = []
    if output.get("repair_steps"):
        parts.append("REPAIR STEPS (frontline, L1)")
        parts += [f"{i}. {step}" for i, step in enumerate(output["repair_steps"], 1)]
    if output.get("symptom_summary") or output.get("suspected_root_cause"):
        parts.append("FAE ESCALATION TICKET (L2)")
        if output.get("symptom_summary"):
            parts.append(f"Symptoms: {output['symptom_summary']}")
        if output.get("suspected_root_cause"):
            parts.append(f"Suspected cause: {output['suspected_root_cause']}")
        for item in output.get("key_abnormal_indicators") or []:
            parts.append(f"- {item}")
        ticket = output.get("ticket") or {}
        for dev in ticket.get("affected_devices") or []:
            parts.append(f"Device {dev.get('id')}: status {dev.get('status')}, RSSI {dev.get('rssi')}, "
                         f"battery {dev.get('battery')}, fw {dev.get('fw')}")
        for rule in ticket.get("escalation_rules") or []:
            # internal rule ids (R1_BATCH ...) would reveal the system to a rater who knows the design
            parts.append(f"Escalation reason: {rule.get('evidence')}")
        for step in ticket.get("steps_performed") or []:
            parts.append(f"Step performed: {step}")
    if output.get("customer_reply"):
        parts += ["", f"REPLY TO CUSTOMER: {output['customer_reply']}"]
    return "\n".join(parts) or json.dumps(output, ensure_ascii=False)


def console_facts(case):
    """What the support console shows for the case (no labels), so grounding can be judged."""
    hs = case["hidden_state"]
    bs = hs["base_station"]
    lines = [f"Base station {bs.get('model')} fw {bs.get('fw')}: online={bs.get('online')}, "
             f"uplink={bs.get('uplink_status')}, storage={bs.get('storage_used_pct')}%, "
             f"error codes={bs.get('error_codes') or 'none'}"]
    for d in hs["devices"]:
        lines.append(f"{d['id']} ({d['model']}, fw {d['fw']}): {d['status']}, RSSI {d['rssi']}, "
                     f"battery {d['battery']}, bound base/app {d['bound_in_base']}/{d['bound_in_app']}")
    lines += [f"log: {line}" for line in hs["logs"]]
    return "\n".join(lines)


# ------------------------------------------------------------------ export
def export(case_ids=DEFAULT_CASES, seed=0):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.worksheet.datavalidation import DataValidation

    rows = load_rows({s: SYSTEMS[s] for s in RATED_SYSTEMS})
    missing = [s for s in RATED_SYSTEMS if s not in rows]
    if missing:
        raise SystemExit(f"No saved results for {missing}; run eval.run_cases first.")
    by_case = {s: {r["case_id"]: r for r in rs} for s, rs in rows.items()}
    cases = {c: json.loads((config.CASES_DIR / f"{c}.json").read_text(encoding="utf-8")) for c in case_ids}
    rng = random.Random(seed)
    order = list(case_ids)
    rng.shuffle(order)

    wb = Workbook()
    info = wb.active
    info.title = "Instructions"
    info.column_dimensions["A"].width = 16
    info.column_dimensions["B"].width = 60
    info.column_dimensions["C"].width = 90
    info.append(["How to rate"])
    info["A1"].font = Font(bold=True, size=13)
    info.append(["", "You are a frontline support lead. Each case shows the customer's complaint, the console facts "
                     "and three anonymous responses (A, B, C) written for a frontline staff member. Score every "
                     "response on the three criteria, then rank the three responses of the case. Judge usefulness "
                     "for the staff member; do not try to guess which system wrote it."])
    info.append([])
    info.append(["Criterion", "Question", "Scale"])
    for cell in info[4]:
        cell.font = Font(bold=True)
    for row in RUBRIC:
        info.append(list(row))
    for row in info.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    ws = wb.create_sheet("Rating")
    headers = ["Case", "Response", "What the agent asked / had the customer do", "Response text",
               "Clarity (1-5)", "Actionability (1-5)", "Grounding (1-5)", "Rank in case (1-3)", "Comment"]
    widths = [8, 9, 38, 70, 11, 13, 12, 12, 24]
    ws.append(headers)
    for i, w in enumerate(widths):
        ws.column_dimensions[chr(65 + i)].width = w
    bold, wrap = Font(bold=True), Alignment(wrap_text=True, vertical="top")
    head_fill = PatternFill("solid", fgColor="C00000")
    case_fill = PatternFill("solid", fgColor="F4F2F2")
    thin = Side(style="thin", color="D0CECE")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head_fill
        cell.alignment = wrap
    score_dv = DataValidation(type="list", formula1='"1,2,3,4,5"', allow_blank=True)
    rank_dv = DataValidation(type="list", formula1='"1,2,3"', allow_blank=True)
    ws.add_data_validation(score_dv)
    ws.add_data_validation(rank_dv)

    key = {}
    for case_id in order:
        case = cases[case_id]
        ws.append([case_id, "CASE", f"Complaint: {case['complaint']}", f"Console facts:\n{console_facts(case)}"])
        r = ws.max_row
        for cell in ws[r]:
            cell.fill = case_fill
            cell.alignment = wrap
        ws.cell(r, 1).font = bold
        ws.row_dimensions[r].height = 15 * (console_facts(case).count("\n") + 2)
        systems = list(RATED_SYSTEMS)
        rng.shuffle(systems)
        for label, system in zip("ABC", systems):
            row = by_case[system][case_id]
            text = render_output(row.get("output", {}))
            ws.append([case_id, label, _session_record(row), text])
            r = ws.max_row
            for col in range(1, len(headers) + 1):
                ws.cell(r, col).alignment = wrap
                ws.cell(r, col).border = Border(top=thin, bottom=thin, left=thin, right=thin)
            ws.cell(r, 2).font = bold
            for col in (5, 6, 7):
                score_dv.add(ws.cell(r, col))
            rank_dv.add(ws.cell(r, 8))
            ws.row_dimensions[r].height = min(409, 15 * max(text.count("\n") + 1, len(text) // 75 + 1))
            key[f"{case_id}/{label}"] = {"system": system, "case_id": case_id,
                                         "judge_score": row.get("usability_score")}
    ws.freeze_panes = "C2"
    for sheet in (info, ws):                      # print landscape, one page wide
        sheet.page_setup.orientation = "landscape"
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_setup.fitToWidth, sheet.page_setup.fitToHeight = 1, 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    wb.save(SHEET)
    KEY.write_text(json.dumps(key, indent=1), encoding="utf-8")
    print(f"[human] {len(key)} responses ({len(order)} cases x {len(RATED_SYSTEMS)} systems) -> {SHEET}")


# ------------------------------------------------------------------ analysis
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
    """pairs: [(system, human, judge)] -> exact / within-1 agreement, Spearman, per-system means."""
    human = [h for _, h, _ in pairs]
    judge = [j for _, _, j in pairs]
    per_system = {}
    for system, h, j in pairs:
        per_system.setdefault(system, []).append((h, j))
    return {
        "items": len(pairs),
        "exact": sum(round(h) == j for h, j in zip(human, judge)) / len(pairs),
        "within_1": sum(abs(h - j) <= 1 for h, j in zip(human, judge)) / len(pairs),
        "spearman": spearman(human, judge),
        "per_system": {s: (mean(h for h, _ in v), mean(j for _, j in v)) for s, v in per_system.items()},
    }


def read_sheet(path=SHEET):
    """Rated responses as [{case_id, label, clarity, actionability, grounding, rank, comment}]."""
    from openpyxl import load_workbook

    ws = load_workbook(path, data_only=True)["Rating"]
    out = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        case_id, label = row[0], row[1]
        if label not in ("A", "B", "C"):
            continue
        values = row[4:8]
        if all(v in (None, "") for v in values):
            continue
        try:
            scores = [int(v) for v in values]
        except (TypeError, ValueError):
            raise SystemExit(f"{case_id}/{label}: fill all three scores and the rank with whole numbers")
        if any(not 1 <= s <= 5 for s in scores[:3]) or not 1 <= scores[3] <= 3:
            raise SystemExit(f"{case_id}/{label}: scores must be 1-5 and the rank 1-3")
        out.append({"case_id": case_id, "label": label, **dict(zip(CRITERIA, scores[:3])),
                    "rank": scores[3], "comment": row[8] or ""})
    by_case = {}
    for r in out:
        by_case.setdefault(r["case_id"], []).append(r["rank"])
    for case_id, ranks in by_case.items():
        if sorted(ranks) != list(range(1, len(ranks) + 1)):
            raise SystemExit(f"{case_id}: ranks must use 1, 2, 3 once each, got {ranks}")
    return out


def summarize_ratings(ratings, key):
    """Per-system criterion means and mean rank, pairwise preference of topology over each other system."""
    rows = [{**r, **key[f"{r['case_id']}/{r['label']}"]} for r in ratings]
    per_system = {}
    for r in rows:
        per_system.setdefault(r["system"], []).append(r)
    systems = {s: {**{c: mean(x[c] for x in v) for c in CRITERIA},
                   "overall": mean(mean(x[c] for c in CRITERIA) for x in v),
                   "rank": mean(x["rank"] for x in v), "first": sum(x["rank"] == 1 for x in v), "n": len(v)}
               for s, v in per_system.items()}
    rank = {(r["case_id"], r["system"]): r["rank"] for r in rows}
    cases = sorted({r["case_id"] for r in rows})
    pairwise = {}
    for other in systems:
        if other == "topology":
            continue
        both = [c for c in cases if (c, "topology") in rank and (c, other) in rank]
        pairwise[other] = (sum(rank[(c, "topology")] < rank[(c, other)] for c in both), len(both))
    judge_pairs = [(r["system"], mean(r[c] for c in CRITERIA), r["judge_score"]) for r in rows
                   if isinstance(r.get("judge_score"), int)]
    return systems, pairwise, (agreement(judge_pairs) if judge_pairs else None)


def agree():
    if not SHEET.exists():
        raise SystemExit(f"{SHEET} not found; run `python -m eval.human_rating export` first.")
    key = json.loads(KEY.read_text(encoding="utf-8"))
    ratings = read_sheet()
    if not ratings:
        raise SystemExit("No ratings yet: fill the score and rank columns of rating_sheet.xlsx.")
    systems, pairwise, judge = summarize_ratings(ratings, key)
    lines = ["## Human ratings (v2: three criteria + rank per case, blind)", "",
             f"{len(ratings)} responses, {len({r['case_id'] for r in ratings})} cases.", "",
             "| System | Clarity | Actionability | Grounding | Overall (mean) | Mean rank (1 = best) | Ranked first |",
             "|---|---|---|---|---|---|---|"]
    for s, v in systems.items():
        lines.append(f"| {SYSTEMS[s]} | {v['clarity']:.2f} | {v['actionability']:.2f} | {v['grounding']:.2f} | "
                     f"{v['overall']:.2f} | {v['rank']:.2f} | {v['first']}/{v['n']} |")
    # exact two-sided sign test on the per-case preference (= McNemar on the discordant cases)
    lines += ["", "Pairwise: cases where the topology agent was ranked above the other system: " + ", ".join(
        f"{SYSTEMS[o]} {w}/{n} (sign test p = {mcnemar_exact(w, n - w):.3f})" for o, (w, n) in pairwise.items())
        + "."]
    if judge:
        lines += ["", f"LLM judge vs human overall (mean of the three criteria): exact {judge['exact']:.0%}, "
                      f"within one point {judge['within_1']:.0%}, Spearman rho {judge['spearman']:.2f}."]
    text = "\n".join(lines) + "\n"
    (OUT_DIR / "agreement.md").write_text(text, encoding="utf-8")
    print(text)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("export")
    ex.add_argument("--cases", nargs="+", default=list(DEFAULT_CASES))
    ex.add_argument("--seed", type=int, default=0)
    sub.add_parser("agree")
    a = ap.parse_args()
    if a.cmd == "export":
        export(tuple(a.cases), a.seed)
    else:
        agree()


if __name__ == "__main__":
    main()
