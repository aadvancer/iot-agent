## Core set (C001-C040)

| System | Root-cause acc | Tier acc | L2 precision | L2 recall | Unneeded / missed escalations | Customer rounds | Usability (1-5) | LLM calls | Tokens | Seconds |
|---|---|---|---|---|---|---|---|---|---|---|
| Vanilla LLM | 85% | 88% | 87% | 81% | 2 / 3 | 0.00 | 3.27 | 1.0 | 884 | 6.5 |
| Vanilla RAG | 85% | 88% | 82% | 88% | 3 / 2 | 0.00 | 3.45 | 1.0 | 1257 | 6.3 |
| Rules only (no LLM) | 92% | 92% | 100% | 81% | 0 / 3 | 0.00 | 2.05 | 0.0 | 0 | 0.0 |
| ReAct (same tools) | 92% | 98% | 94% | 100% | 1 / 0 | 0.72 | 3.05 | 6.5 | 14946 | 19.2 |
| Topology agent (ours) | 100% | 100% | 100% | 100% | 0 / 0 | 1.12 | 3.92 | 6.5 | 17181 | 21.6 |

| System | Acc (easy) | Acc (medium) | Acc (hard) | Tier overrides by R1-R5 |
|---|---|---|---|---|
| Vanilla LLM | 100% | 77% | 92% | 0 |
| Vanilla RAG | 100% | 77% | 92% | 0 |
| Rules only (no LLM) | 100% | 100% | 77% | 0 |
| ReAct (same tools) | 100% | 86% | 100% | 0 |
| Topology agent (ours) | 100% | 100% | 100% | 0 |

## Challenge set (C041-C052, author-written shortcut probes; report separately)

| System | Root-cause acc | Tier acc | L2 precision | L2 recall | Unneeded / missed escalations | Customer rounds | Usability (1-5) | LLM calls | Tokens | Seconds |
|---|---|---|---|---|---|---|---|---|---|---|
| Vanilla LLM | 25% | 50% | 50% | 17% | 1 / 5 | 0.00 | 3.42 | 1.0 | 876 | 6.2 |
| Vanilla RAG | 33% | 58% | 67% | 33% | 1 / 4 | 0.00 | 3.50 | 1.0 | 1228 | 6.7 |
| Rules only (no LLM) | 75% | 75% | 100% | 50% | 0 / 3 | 0.00 | 1.92 | 0.0 | 0 | 0.0 |
| ReAct (same tools) | 92% | 92% | 100% | 83% | 0 / 1 | 0.50 | 3.08 | 5.8 | 12573 | 17.1 |
| Topology agent (ours) | 100% | 100% | 100% | 100% | 0 / 0 | 1.08 | 3.75 | 8.2 | 24513 | 27.5 |

## Statistical check: Core set (C001-C040)

Run 1 of each system. 95% Wilson intervals; exact two-sided McNemar test on paired per-case outcomes vs the topology agent (p < 0.05 = difference unlikely to be chance).

| System | Root-cause acc [95% CI] | Tier acc [95% CI] | Root cause: ours-only / baseline-only correct | p (McNemar) | Tier: ours-only / baseline-only correct | p (McNemar) |
|---|---|---|---|---|---|---|
| Vanilla LLM | 34/40 = 85% [71%, 93%] | 35/40 = 88% [74%, 95%] | 6 / 0 | 0.031 | 5 / 0 | 0.062 |
| Vanilla RAG | 34/40 = 85% [71%, 93%] | 35/40 = 88% [74%, 95%] | 6 / 0 | 0.031 | 5 / 0 | 0.062 |
| Rules only (no LLM) | 37/40 = 92% [80%, 97%] | 37/40 = 92% [80%, 97%] | 3 / 0 | 0.250 | 3 / 0 | 0.250 |
| ReAct (same tools) | 37/40 = 92% [80%, 97%] | 39/40 = 98% [87%, 100%] | 3 / 0 | 0.250 | 1 / 0 | 1.000 |
| Topology agent (ours) | 40/40 = 100% [91%, 100%] | 40/40 = 100% [91%, 100%] | — | — | — | — |

## Repeated runs: Core set (C001-C040)

Identical settings (temperature 0); runs 2+ use a separate LLM cache namespace, so the spread is the run-to-run variation of the model and the simulated customer.

| System | Runs | Root-cause acc per run | Mean ± sd | Tier acc per run | Mean ± sd | Tokens / case (mean) | Cases with unstable root cause |
|---|---|---|---|---|---|---|---|
| ReAct (same tools) | 3 | 92% / 95% / 95% | 94.2% ± 1.4% | 98% / 98% / 95% | 96.7% ± 1.4% | 14800 | C003, C006, C009, C010, C030 |
| Topology agent (ours) | 3 | 100% / 100% / 100% | 100.0% ± 0.0% | 100% / 100% / 98% | 99.2% ± 1.4% | 19062 | none |

## Cost breakdown: Core set (C001-C040)

| System | Console queries | KB searches | Customer questions | Guided actions | LLM calls | Tokens / LLM call | Tokens / case |
|---|---|---|---|---|---|---|---|
| Vanilla LLM | 0.0 | 0.0 | 0.00 | 0.00 | 1.0 | 884 | 884 |
| Vanilla RAG | 0.0 | 0.0 | 0.00 | 0.00 | 1.0 | 1257 | 1257 |
| Rules only (no LLM) | 4.4 | 0.0 | 0.00 | 0.00 | 0.0 | 0 | 0 |
| ReAct (same tools) | 5.2 | 1.2 | 0.33 | 0.40 | 6.5 | 2299 | 14946 |
| Topology agent (ours) | 4.8 | 1.1 | 0.45 | 0.68 | 6.5 | 2633 | 17181 |

## Error analysis: Core set (C001-C040)

| System | Wrong root cause (pred → truth) | Wrong tier (pred → truth) |
|---|---|---|
| Vanilla LLM | C004: WEAK_SIGNAL → PROTOCOL_CONFLICT<br>C005: WEAK_SIGNAL → BATCH_LINK_FAILURE<br>C018: WEAK_SIGNAL → BATTERY_LOW<br>C021: PROTOCOL_CONFLICT → PERIPHERAL_FW_OUTDATED<br>C023: PROTOCOL_CONFLICT → PERIPHERAL_FW_OUTDATED<br>C027: WEAK_SIGNAL → PROTOCOL_CONFLICT | C004: L1 → L2<br>C005: L1 → L2<br>C021: L2 → L1<br>C023: L2 → L1<br>C027: L1 → L2 |
| Vanilla RAG | C004: BATTERY_LOW → PROTOCOL_CONFLICT<br>C005: WEAK_SIGNAL → BATCH_LINK_FAILURE<br>C011: BINDING_TABLE_CORRUPT → PAIR_TIMEOUT<br>C013: BINDING_TABLE_CORRUPT → CAPACITY_EXCEEDED<br>C019: WEAK_SIGNAL → BATTERY_LOW<br>C023: PROTOCOL_CONFLICT → PERIPHERAL_FW_OUTDATED | C004: L1 → L2<br>C005: L1 → L2<br>C011: L2 → L1<br>C013: L2 → L1<br>C023: L2 → L1 |
| Rules only (no LLM) | C033: BS_NETWORK_DOWN → UPLINK_BLOCKED_PERSIST<br>C034: BS_NETWORK_DOWN → UPLINK_BLOCKED_PERSIST<br>C035: BS_NETWORK_DOWN → UPLINK_BLOCKED_PERSIST | C033: L1 → L2<br>C034: L1 → L2<br>C035: L1 → L2 |
| ReAct (same tools) | C003: PROTOCOL_CONFLICT → PERIPHERAL_FW_OUTDATED<br>C006: UPLINK_BLOCKED_PERSIST → BS_NETWORK_DOWN<br>C009: BINDING_TABLE_CORRUPT → PAIR_TIMEOUT | C009: L2 → L1 |
| Topology agent (ours) | none | none |

## Statistical check: Challenge set (C041-C052, author-written shortcut probes; report separately)

Run 1 of each system. 95% Wilson intervals; exact two-sided McNemar test on paired per-case outcomes vs the topology agent (p < 0.05 = difference unlikely to be chance).

| System | Root-cause acc [95% CI] | Tier acc [95% CI] | Root cause: ours-only / baseline-only correct | p (McNemar) | Tier: ours-only / baseline-only correct | p (McNemar) |
|---|---|---|---|---|---|---|
| Vanilla LLM | 3/12 = 25% [9%, 53%] | 6/12 = 50% [25%, 75%] | 9 / 0 | 0.004 | 6 / 0 | 0.031 |
| Vanilla RAG | 4/12 = 33% [14%, 61%] | 7/12 = 58% [32%, 81%] | 8 / 0 | 0.008 | 5 / 0 | 0.062 |
| Rules only (no LLM) | 9/12 = 75% [47%, 91%] | 9/12 = 75% [47%, 91%] | 3 / 0 | 0.250 | 3 / 0 | 0.250 |
| ReAct (same tools) | 11/12 = 92% [65%, 99%] | 11/12 = 92% [65%, 99%] | 1 / 0 | 1.000 | 1 / 0 | 1.000 |
| Topology agent (ours) | 12/12 = 100% [76%, 100%] | 12/12 = 100% [76%, 100%] | — | — | — | — |

## Repeated runs: Challenge set (C041-C052, author-written shortcut probes; report separately)

Identical settings (temperature 0); runs 2+ use a separate LLM cache namespace, so the spread is the run-to-run variation of the model and the simulated customer.

| System | Runs | Root-cause acc per run | Mean ± sd | Tier acc per run | Mean ± sd | Tokens / case (mean) | Cases with unstable root cause |
|---|---|---|---|---|---|---|---|
| ReAct (same tools) | 3 | 92% / 92% / 92% | 91.7% ± 0.0% | 92% / 92% / 92% | 91.7% ± 0.0% | 13655 | none |
| Topology agent (ours) | 3 | 100% / 92% / 100% | 97.2% ± 4.8% | 100% / 100% / 100% | 100.0% ± 0.0% | 22749 | C050 |

## Cost breakdown: Challenge set (C041-C052, author-written shortcut probes; report separately)

| System | Console queries | KB searches | Customer questions | Guided actions | LLM calls | Tokens / LLM call | Tokens / case |
|---|---|---|---|---|---|---|---|
| Vanilla LLM | 0.0 | 0.0 | 0.00 | 0.00 | 1.0 | 876 | 876 |
| Vanilla RAG | 0.0 | 0.0 | 0.00 | 0.00 | 1.0 | 1228 | 1228 |
| Rules only (no LLM) | 4.4 | 0.0 | 0.00 | 0.00 | 0.0 | 0 | 0 |
| ReAct (same tools) | 4.9 | 1.0 | 0.25 | 0.25 | 5.8 | 2155 | 12573 |
| Topology agent (ours) | 4.8 | 2.1 | 0.42 | 0.67 | 8.2 | 3002 | 24513 |

## Error analysis: Challenge set (C041-C052, author-written shortcut probes; report separately)

| System | Wrong root cause (pred → truth) | Wrong tier (pred → truth) |
|---|---|---|
| Vanilla LLM | C041: WEAK_SIGNAL → HW_FAULT_SUSPECTED<br>C042: PERIPHERAL_FW_OUTDATED → PROTOCOL_CONFLICT<br>C043: BATTERY_LOW → BS_NETWORK_DOWN<br>C044: BATCH_LINK_FAILURE → BATTERY_LOW<br>C045: CAPACITY_EXCEEDED → BINDING_TABLE_CORRUPT<br>C047: BATTERY_LOW → PERIPHERAL_FW_OUTDATED<br>C048: CAPACITY_EXCEEDED → PAIR_TIMEOUT<br>C050: BATTERY_LOW → HW_FAULT_SUSPECTED<br>C051: BATTERY_LOW → BATCH_LINK_FAILURE | C041: L1 → L2<br>C042: L1 → L2<br>C044: L2 → L1<br>C045: L1 → L2<br>C050: L1 → L2<br>C051: L1 → L2 |
| Vanilla RAG | C041: WEAK_SIGNAL → HW_FAULT_SUSPECTED<br>C042: PERIPHERAL_FW_OUTDATED → PROTOCOL_CONFLICT<br>C043: BATTERY_LOW → BS_NETWORK_DOWN<br>C044: BATCH_LINK_FAILURE → BATTERY_LOW<br>C047: BATTERY_LOW → PERIPHERAL_FW_OUTDATED<br>C048: CAPACITY_EXCEEDED → PAIR_TIMEOUT<br>C050: BATTERY_LOW → HW_FAULT_SUSPECTED<br>C051: BATTERY_LOW → BATCH_LINK_FAILURE | C041: L1 → L2<br>C042: L1 → L2<br>C044: L2 → L1<br>C050: L1 → L2<br>C051: L1 → L2 |
| Rules only (no LLM) | C041: WEAK_SIGNAL → HW_FAULT_SUSPECTED<br>C050: BATTERY_LOW → HW_FAULT_SUSPECTED<br>C052: BS_NETWORK_DOWN → UPLINK_BLOCKED_PERSIST | C041: L1 → L2<br>C050: L1 → L2<br>C052: L1 → L2 |
| ReAct (same tools) | C050: BATTERY_LOW → HW_FAULT_SUSPECTED | C050: L1 → L2 |
| Topology agent (ours) | none | none |

## Hard cases and stability (rule-hard = cases the rules-only baseline gets wrong; both splits pooled, split shown per case)

Rules only is 0% on this subset by construction. Systems with repeated runs report the mean over runs and pass^k (correct in all k runs).

| System | Runs | Rule-easy (46) cause acc | Rule-easy pass^k (cause) | Rule-hard (6) cause acc | Rule-hard tier acc | Rule-hard pass^k (cause / tier) |
|---|---|---|---|---|---|---|
| Vanilla LLM | 1 | 71.7% | 33/46 | 66.7% | 66.7% | 4/6 / 4/6 |
| Vanilla RAG | 1 | 73.9% | 34/46 | 66.7% | 66.7% | 4/6 / 4/6 |
| Rules only (no LLM) | 1 | 100.0% | 46/46 | 0.0% | 0.0% | 0/6 / 0/6 |
| ReAct (same tools) | 3 | 94.9% | 41/46 | 83.3% | 83.3% | 5/6 / 5/6 |
| Topology agent (ours) | 3 | 100.0% | 46/46 | 94.4% | 100.0% | 5/6 / 6/6 |

Per-case results on the rule-hard cases (correct runs / runs; ✗ shows the wrong prediction):

| Case | Split | Truth | Vanilla LLM | Vanilla RAG | Rules only (no LLM) | ReAct (same tools) | Topology agent (ours) |
|---|---|---|---|---|---|---|---|
| C033 | core | UPLINK_BLOCKED_PERSIST | ✓ | ✓ | ✗ BS_NETWORK_DOWN | 3/3 | 3/3 |
| C034 | core | UPLINK_BLOCKED_PERSIST | ✓ | ✓ | ✗ BS_NETWORK_DOWN | 3/3 | 3/3 |
| C035 | core | UPLINK_BLOCKED_PERSIST | ✓ | ✓ | ✗ BS_NETWORK_DOWN | 3/3 | 3/3 |
| C041 | challenge | HW_FAULT_SUSPECTED | ✗ WEAK_SIGNAL | ✗ WEAK_SIGNAL | ✗ WEAK_SIGNAL | 3/3 | 3/3 |
| C050 | challenge | HW_FAULT_SUSPECTED | ✗ BATTERY_LOW | ✗ BATTERY_LOW | ✗ BATTERY_LOW | 0/3 | 2/3 |
| C052 | challenge | UPLINK_BLOCKED_PERSIST | ✓ | ✓ | ✗ BS_NETWORK_DOWN | 3/3 | 3/3 |

## Ablation: Core set (C001-C040)

| Variant | Cases | Root-cause acc | Tier acc | L2 precision | L2 recall | Unneeded / missed escalations | Tier overrides | Customer rounds | Repeated queries blocked / executed | LLM calls | Tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Full agent | 40 | 100% | 100% | 100% | 100% | 0 / 0 | 0 | 1.12 | 0.12 / 0.00 | 6.5 | 17181 |
| - topology planner | 40 | 98% | 98% | 100% | 94% | 0 / 1 | 0 | 0.90 | 0.45 / 0.00 | 10.2 | 28592 |
| - rule hints | 40 | 98% | 95% | 89% | 100% | 2 / 0 | 1 | 1.07 | 0.30 / 0.00 | 7.2 | 20391 |
| - structured memory | 40 | 100% | 100% | 100% | 100% | 0 / 0 | 0 | 0.95 | 0.00 / 0.23 | 7.2 | 18005 |
| - rule tier override | 40 | 100% | 100% | 100% | 100% | 0 / 0 | 0 | 1.12 | 0.12 / 0.00 | 6.5 | 17181 |

## Ablation: Challenge set (C041-C052, author-written shortcut probes; report separately)

| Variant | Cases | Root-cause acc | Tier acc | L2 precision | L2 recall | Unneeded / missed escalations | Tier overrides | Customer rounds | Repeated queries blocked / executed | LLM calls | Tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Full agent | 12 | 100% | 100% | 100% | 100% | 0 / 0 | 0 | 1.08 | 0.67 / 0.00 | 8.2 | 24513 |
| - topology planner | 12 | 83% | 100% | 100% | 100% | 0 / 0 | 2 | 0.92 | 0.92 / 0.00 | 11.9 | 35583 |
| - rule hints | 12 | 100% | 100% | 100% | 100% | 0 / 0 | 0 | 1.25 | 1.17 / 0.00 | 9.0 | 26460 |
| - structured memory | 12 | 100% | 100% | 100% | 100% | 0 / 0 | 0 | 1.00 | 0.00 / 0.42 | 8.0 | 21684 |
| - rule tier override | 12 | 100% | 100% | 100% | 100% | 0 / 0 | 0 | 1.08 | 0.67 / 0.00 | 8.2 | 24513 |
