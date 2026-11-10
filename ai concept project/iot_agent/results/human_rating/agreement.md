## Human ratings (v2: three criteria + rank per case, blind)

21 responses, 7 cases.

| System | Clarity | Actionability | Grounding | Overall (mean) | Mean rank (1 = best) | Ranked first |
|---|---|---|---|---|---|---|
| Topology agent (ours) | 4.00 | 4.86 | 4.29 | 4.38 | 1.29 | 5/7 |
| Vanilla RAG | 4.57 | 3.71 | 2.57 | 3.62 | 3.00 | 0/7 |
| ReAct (same tools) | 4.86 | 4.71 | 4.43 | 4.67 | 1.71 | 2/7 |

Pairwise: cases where the topology agent was ranked above the other system: Vanilla RAG 7/7 (sign test p = 0.016), ReAct (same tools) 5/7 (sign test p = 0.453).

LLM judge vs human overall (mean of the three criteria): exact 24%, within one point 71%, Spearman rho -0.14.
