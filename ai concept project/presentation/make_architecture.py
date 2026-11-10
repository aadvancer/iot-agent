"""Draw the agent architecture figure for the slides and report.

Usage (from the iot_agent directory): python ../presentation/make_architecture.py
Writes presentation/architecture.png. No API key needed.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

OUT = Path(__file__).resolve().parent / "architecture.png"
GREY, RED, BLUE, GREEN, AMBER = "#e9ecef", "#f4c7cc", "#cfe2f3", "#d9ead3", "#fde9c4"


def box(ax, x, y, w, h, title, body="", color=GREY):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                fc=color, ec="#495057", lw=1.1))
    ax.text(x + w / 2, y + h - 0.16, title, ha="center", va="top", fontsize=9.5, weight="bold")
    if body:
        ax.text(x + w / 2, y + h - 0.48, body, ha="center", va="top", fontsize=7.6, linespacing=1.35)


def arrow(ax, a, b, text="", rad=0.0):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=11, lw=1.1, color="#343a40",
                                 connectionstyle=f"arc3,rad={rad}"))
    if text and a[0] == b[0]:   # vertical arrow: label to the right
        ax.text(a[0] + 0.08, (a[1] + b[1]) / 2, text, ha="left", va="center", fontsize=7, style="italic")
    elif text:
        ax.text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + 0.1, text, ha="center", fontsize=7, style="italic")


def path(ax, points, text=""):
    """Polyline arrow along free corridors; the label sits on the longest segment."""
    xs, ys = zip(*points)
    ax.plot(xs[:-1], ys[:-1], color="#343a40", lw=1.1)
    arrow(ax, points[-2], points[-1])
    if text:
        (x0, y0), (x1, y1) = max(zip(points, points[1:]), key=lambda s: abs(s[0][0] - s[1][0]))
        ax.text((x0 + x1) / 2, y0 + 0.08, text, ha="center", fontsize=7.5, style="italic")


def main():
    fig, ax = plt.subplots(figsize=(13, 6.6))
    ax.set_xlim(0, 13)
    ax.set_ylim(0.1, 6.6)
    ax.axis("off")

    box(ax, 0.2, 4.3, 2.3, 1.6, "Frontline staff", "relays the customer's\ncomplaint, answers and\naction results", AMBER)
    box(ax, 0.2, 2.1, 2.3, 1.6, "Support console\n(simulated)", "base status, binding table,\ndevice info, firmware\ncompat, event log")
    box(ax, 0.2, 0.75, 2.3, 1.0, "Knowledge base", "ChromaDB + TF-IDF hybrid")

    box(ax, 3.3, 3.7, 2.7, 2.2, "1  Topology planner",
        "S1 base station\n→ S2 binding / capacity\n→ S3 link quality\n→ S4 firmware / protocol\n→ S5 peripheral\n"
        "(skips S2-S5 if master down)", BLUE)
    box(ax, 3.3, 0.75, 2.7, 2.35, "2  Structured memory",
        "typed slots per stage,\ncustomer answers, fix attempts\nduplicate-query guard\nKB 'no new knowledge' stop\n"
        "FAISS recall of earlier steps", BLUE)

    box(ax, 6.8, 2.5, 2.8, 3.4, "3  LLM reasoning loop\n(LangGraph)",
        "input: memory snapshot +\nrule hints + recent notes\n\nchooses ONE tool per step:\nconsole query, search_kb,\n"
        "ask_user, instruct_user,\nsubmit_diagnosis\n\nvalidated calls, 15-step budget", RED)
    box(ax, 6.8, 0.75, 2.8, 1.3, "Rule matcher", "evidence → candidate causes\n(rule hints)", GREEN)

    box(ax, 10.4, 3.2, 2.4, 2.7, "4  Triage",
        "tier from taxonomy\n+ hard rules override to L2:\nR1 batch failure\nR2 protocol after OTA\nR3 standard fix failed\n"
        "R4 app / base mismatch\nR5 fails next to base", GREEN)
    box(ax, 10.4, 0.75, 2.4, 2.0, "Output to staff",
        "L1: repair steps +\ncustomer reply template\nL2: FAE escalation ticket\n(evidence + steps tried)", AMBER)

    arrow(ax, (2.5, 5.1), (3.3, 5.1), "complaint")
    arrow(ax, (2.5, 2.9), (3.3, 4.0), "S1-S5 queries")
    arrow(ax, (4.65, 3.7), (4.65, 3.1))
    arrow(ax, (6.0, 2.6), (6.8, 3.4), "snapshot")
    arrow(ax, (8.2, 2.05), (8.2, 2.5), "hints")
    arrow(ax, (6.0, 1.4), (6.8, 1.4))
    arrow(ax, (9.6, 4.5), (10.4, 4.5), "diagnosis")
    arrow(ax, (11.6, 3.2), (11.6, 2.75), "tier")
    # routed through the free corridors above and below the boxes
    path(ax, [(8.2, 5.9), (8.2, 6.25), (1.35, 6.25), (1.35, 5.9)], "ask_user / instruct_user (staff relays to customer)")
    path(ax, [(6.8, 2.75), (6.4, 2.75), (6.4, 0.4), (1.35, 0.4), (1.35, 0.75)], "search_kb")
    ax.set_title("Topology-aware frontline-support copilot", fontsize=12, weight="bold")
    fig.tight_layout()
    fig.savefig(OUT, dpi=170)
    plt.close(fig)
    print(f"[architecture] {OUT}")


if __name__ == "__main__":
    main()
