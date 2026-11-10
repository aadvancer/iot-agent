# Slides outline (5-7 min talk + 1-2 min Q&A)

Nine slides, about 40 s each. Every number below comes from
`iot_agent/results/comparison.md` (run 1 unless marked as repeated runs).
Figures are in `iot_agent/results/figures/` and `presentation/architecture.png`.

---

## 1. Title (10 s)
**A Topology-Aware Support Copilot for Gateway-Centric Smart Security Systems**
Name, student ID, COMP5511 Final Project.

## 2. Problem and motivation (45 s)
- Gateway-centric (master-slave) IoT: every camera and sensor works only
  through one base station.
- From the internship: most tickets are **interaction faults** (pairing,
  signal, firmware protocol, uplink), not broken hardware.
- Frontline staff lack a standard procedure, which causes two problems:
  - trivial tickets are escalated to scarce FAE engineers;
  - real protocol and batch faults get buried.
- **Goal:** diagnose the root cause, then either close the ticket at
  frontline (L1) or write a complete FAE ticket (L2).
- **Users:** frontline staff (primary) and FAE engineers (they receive the
  tickets).

> Speaker note: one sentence about what you saw in the internship. It makes the
> problem concrete for the audience.

## 3. Approach: architecture (60 s)
Figure: `architecture.png`
1. **Topology planner.** Collects console evidence in the order S1 base →
   S2 binding → S3 link → S4 firmware → S5 peripheral, and prunes everything
   below the base station when the base is down.
2. **Structured memory.** Typed slots for confirmed facts, a duplicate-query
   guard, and a stop for KB searches that bring nothing new.
3. **LLM reasoning loop** (LangGraph, DeepSeek). Picks one tool per step: a
   console query, a KB search, a question for the customer, a guided action,
   or the final diagnosis.
4. **Triage.** Hard escalation rules R1-R5 from the support policy can only
   raise the tier to L2.

> Speaker note: point out that the LLM never sees the raw transcript, only the
> memory snapshot plus the rule hints.

## 4. Algorithm (30 s)
Show Algorithm 2 (tier classification) from `pseudocode.md`. It is short and
makes the rules concrete. Algorithm 1 goes in the report.

## 5. Data and baselines (40 s)
- 40 core cases + 12 challenge cases (synthetic, labelled with root cause and
  tier). Each household has about 7 devices, with distractor devices and noisy
  logs.
- The challenge set targets shortcuts:
  - stale console data (3 cases);
  - a misleading self-diagnosis in the complaint (9 cases).
- Baselines, each isolating one design choice:
  - Vanilla LLM (complaint only)
  - Vanilla RAG (complaint + 3 KB snippets)
  - Rules only (no LLM)
  - ReAct with the same tools
  - four ablations (no planner, no hints, no memory, no override)

Figure: `results/figures/dataset.png` (small).

## 6. Main results (60 s)
Table, core / challenge:

| System | Root cause | Tier | Tokens/case |
|---|---|---|---|
| Vanilla LLM | 85% / 25% | 88% / 50% | 0.9k |
| Vanilla RAG | 85% / 33% | 88% / 58% | 1.3k |
| Rules only | 92% / 75% | 92% / 75% | 0 |
| ReAct (same tools) | 92% / 92% | 98% / 92% | 15k / 13k |
| **Topology agent** | **100% / 100%** | **100% / 100%** | 17k / 25k |

- vs complaint-only baselines: significant (McNemar p ≤ 0.031 on both sets).
- vs ReAct: higher, but **not significant** on a single run (p = 0.25).
  Be upfront about this.
- Over 3 repeated runs: topology 100% core root-cause accuracy (ReAct 94.2% ± 1.4%);
  ReAct changed its answer on 5 core cases between runs, topology on 0.
- Usability judge (1-5): 3.92 vs 3.05 for ReAct.

## 7. Example: why tools + dialogue matter (C041, 45 s)
- **Complaint:** "Garage camera offline, the signal must be weak, can I buy a
  repeater?"
- **Console:** RSSI -83 dBm. The rules and the complaint-only LLM both say
  WEAK_SIGNAL (L1), which is wrong.
- **Agent:** sees from the log that the RSSI reading is 2 days old, so it asks
  the customer instead of trusting it. The customer reports:
  - the LED goes dark after a reset;
  - the power adapter is firmly connected;
  - re-plugging does not light the LED.

  Diagnosis: HW_FAULT_SUSPECTED, escalated to L2 (correct). A weak signal would
  not make the LED go dark.
- ReAct also gets this case right, but Vanilla LLM and Rules only stay on
  WEAK_SIGNAL.

## 8. Ablations and error analysis (45 s)
Figure: `results/figures/ablation.png`
- **Planner.** Accuracy is barely affected on the core set, but it saves about
  40% of the tokens and LLM calls. Without it, challenge accuracy drops to 83%.
- **Rule hints.** Without them there are 2 unneeded escalations on the core
  set.
- **Failure we fixed (C045).** The agent searched the KB 13 times until its
  budget ran out. After adding the KB search stop, the right hint order and the
  missing KB section, it solves C045 with 1 search and about 10k tokens
  instead of about 31k.
- **Remaining weakness.** R3 trusts an LLM action judge. In one repeated run a
  misjudged action (C008) caused an unneeded escalation.

## 9. Limitations and takeaways (40 s)
- The data is synthetic, and the labels, rules and policy share one author, so
  rule-based parts are favoured. The next step is real anonymised tickets.
- Usability is judged by an LLM; a blind human check is prepared
  (`eval.human_rating`).
- **Takeaway:** domain structure (topology order, typed memory, policy rules)
  makes an LLM agent more accurate, more stable across runs, and auditable for
  escalation decisions, at about 15% more tokens than ReAct on the core set.

---

### Likely Q&A
- **Why not just ReAct?** It has the same tools, but on a single run the
  accuracy gap is not significant. The benefits that hold up are run-to-run
  stability, tier accuracy and fewer missed escalations.
- **Isn't 100% suspicious?** Yes: the data is synthetic and written by the
  same author as the rules, and the 95% CI is [91%, 100%]. That is why the
  challenge set and the statistics are reported.
- **Why LangGraph instead of openJiuwen (from the proposal)?** It runs locally
  and its SQLite checkpointer supports pausing while staff relay a customer
  reply.
- **Cost?** About 17k tokens and 22 s of model time per core case, with
  thinking mode off.
