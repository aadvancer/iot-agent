# Pseudocode for the report

Two algorithms describe the method; they match `agent/workflow.py`,
`agent/planner.py`, `agent/rules.py` and `agent/triage.py`. The LaTeX versions
below use the `algorithm` + `algpseudocode` packages.

## Algorithm 1 — Topology-aware diagnosis

```
Input : complaint c, support console E, knowledge base K, step budget B = 15
Output: root cause y, tier t ∈ {L1, L2}, hand-off document o

M ← empty structured memory(c)
// Phase 1: deterministic evidence collection in topology order
while (q ← NEXTQUERY(M)) ≠ none do                 // S1 → S2 → S3 → S4 → S5
    M.update(q, E.execute(q))                      // skips S2–S5 when the base station is down
// Phase 2: LLM reasoning loop
for step = 1 .. B do
    H ← MATCHCAUSES(M)                             // rule hints from confirmed evidence
    a ← LLM(system prompt, M.snapshot(), H, recent notes, FAISS recall)
    if a = submit_diagnosis(y) then break
    if a is identical to an answered query then
        r ← M.lookup(a)                            // duplicate-query guard
    else if a = search_kb and M.staleKB ≥ 2 then
        r ← "KB exhausted, decide now"             // knowledge-search stop
    else if a = search_kb then
        r ← K.search(a.query); M.update(a, r)
        M.staleKB ← (r has a new snippet) ? 0 : M.staleKB + 1
    else if a = instruct_user(action, cause) then
        r ← customer outcome; (resolved, standardFix) ← JUDGE(r)
        M.addAction(action, cause, resolved, standardFix)
    else
        r ← execute a on E / customer; M.update(a, r)
if no diagnosis then y ← first hint in H (or HW_FAULT_SUSPECTED)
(t, triggers) ← CLASSIFYTIER(M, y)                 // Algorithm 2
o ← (t = L1) ? repair steps + reply template : FAE escalation ticket
return y, t, o
```

## Algorithm 2 — Tier classification with hard escalation rules

```
Input : memory M, diagnosed cause y
Output: tier t, fired rules R

t ← taxonomy[y].tier
R ← ∅
if ≥ 2 bound devices lost within 300 s (or E-610) and base online then R ← R ∪ {R1}
if a device is protocol-incompatible and (OTA failed or no OTA path) then R ← R ∪ {R2}
if t = L1 and the standard fix for y was performed and failed     then R ← R ∪ {R3}
if app binding list ≠ base-station binding table                   then R ← R ∪ {R4}
if customer reports reset ∧ device next to base ∧ still failing    then R ← R ∪ {R5}
if R ≠ ∅ then t ← L2                                               // override only escalates
return t, R
```

## LaTeX

```latex
\begin{algorithm}[t]
\caption{Topology-aware diagnosis}\label{alg:diagnosis}
\begin{algorithmic}[1]
\Require complaint $c$, console $E$, knowledge base $K$, step budget $B=15$
\Ensure root cause $y$, tier $t\in\{\mathrm{L1},\mathrm{L2}\}$, hand-off $o$
\State $M \gets \textsc{Memory}(c)$
\While{$q \gets \textsc{NextQuery}(M)$ exists} \Comment{S1$\to$S2$\to$S3$\to$S4$\to$S5}
  \State $M.\textsc{Update}(q, E(q))$
\EndWhile
\For{$i = 1$ \textbf{to} $B$}
  \State $H \gets \textsc{MatchCauses}(M)$
  \State $a \gets \textsc{LLM}(M.\textsc{Snapshot}(), H, \text{notes}, \text{recall})$
  \If{$a = \textsc{Submit}(y)$} \textbf{break} \EndIf
  \If{$a$ already answered} $r \gets M.\textsc{Lookup}(a)$
  \ElsIf{$a = \textsc{SearchKB} \wedge M.\mathit{staleKB} \ge 2$} $r \gets$ ``KB exhausted''
  \ElsIf{$a = \textsc{SearchKB}$}
    \State $r \gets K(a)$; $M.\textsc{Update}(a, r)$; $M.\mathit{staleKB} \gets$ ($r$ has a new snippet) ? $0$ : $M.\mathit{staleKB}+1$
  \ElsIf{$a = \textsc{Instruct}(\mathit{act}, \mathit{cause})$}
    \State $r \gets$ customer outcome; $M.\textsc{AddAction}(\mathit{act}, \mathit{cause}, \textsc{Judge}(r))$
  \Else\ $r \gets \textsc{Execute}(a)$; $M.\textsc{Update}(a, r)$
  \EndIf
\EndFor
\If{no diagnosis} $y \gets$ first cause in $H$ \EndIf
\State $(t, R) \gets \textsc{ClassifyTier}(M, y)$ \Comment{Algorithm~\ref{alg:tier}}
\State \Return $y, t, o$ (repair steps if $t=\mathrm{L1}$, else FAE ticket)
\end{algorithmic}
\end{algorithm}

\begin{algorithm}[t]
\caption{Tier classification with hard escalation rules}\label{alg:tier}
\begin{algorithmic}[1]
\Require memory $M$, diagnosed cause $y$
\State $t \gets \mathrm{taxonomy}[y].\mathit{tier}$; $R \gets \emptyset$
\If{$\ge 2$ bound devices lost within 300\,s (or E-610) and base online} $R \gets R \cup \{R1\}$ \EndIf
\If{protocol mismatch and (OTA failed or no OTA path)} $R \gets R \cup \{R2\}$ \EndIf
\If{$t=\mathrm{L1}$ and the standard fix for $y$ failed} $R \gets R \cup \{R3\}$ \EndIf
\If{app binding list $\ne$ base binding table} $R \gets R \cup \{R4\}$ \EndIf
\If{customer: reset $\wedge$ next to base $\wedge$ still failing} $R \gets R \cup \{R5\}$ \EndIf
\If{$R \ne \emptyset$} $t \gets \mathrm{L2}$ \EndIf
\State \Return $t, R$
\end{algorithmic}
\end{algorithm}
```
