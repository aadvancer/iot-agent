# AI Agent for Smart Security IoT Systems

This repository contains a prototype support agent for a fictional, gateway-based
smart-security system. It diagnoses cases using topology-ordered console checks,
structured session memory, deterministic escalation rules, and a searchable
knowledge base. The product data and support cases are synthetic.

## Intended users and positioning

The agent is a **copilot for frontline support staff**, not a customer-facing
chatbot.

- **Primary user: frontline support staff.** They have the support console and
  talk to the customer. The agent reads console data, suggests which questions
  to ask the customer and which actions to walk them through, and hands back
  repair steps, a customer reply template, or an escalation ticket. It never
  talks to the customer directly.
- **Secondary beneficiary: FAE engineers.** They receive fewer trivial tickets
  and standardized L2 tickets with the troubleshooting trace.
- **Indirect beneficiary: end customers**, who get faster and less repetitive
  support.

In code, the `ask_user` / `instruct_user` tools mean "suggest this question /
action to the staff member, who relays it to the customer and reports back".
In evaluation and in the dashboard a simulated customer answers those
relayed questions. "Interaction rounds" therefore counts customer questions
and actions relayed through staff.

## Project files

The implementation is in [`ai concept project/iot_agent`](./ai%20concept%20project/iot_agent).
It currently includes the topology-aware agent, Vanilla LLM and Vanilla RAG
comparison systems, 40 labeled synthetic cases, and an evaluation runner. The
original five cases are hand-authored; C006-C040 are reproducibly generated
template-based scenarios and should be reviewed before using them as an
independent research benchmark.

Every case carries a complexity layer: a multi-sentence customer narrative that
often contains a wrong self-diagnosis (for example blaming batteries, a Wi-Fi
router or a faulty device), a household of 5-9 devices including healthy
distractor devices (one with a low-but-fine battery or borderline RSSI), 4-12 log
lines with routine noise around the decisive entries, extra customer facts, and
several ineffective customer-side actions besides the real fix. Distractors
never change the label evidence. `python -m eval.generate_cases --force`
regenerates C006-C040 and `--enrich-core` adds the same layer to C001-C005
(idempotent). After changing cases, saved results under `results/raw/` are
stale and should be regenerated.

## Setup

Use Python 3.10 or newer, install the dependencies, and provide the API settings
in `ai concept project/iot_agent/.env` (copy `.env.example` to `.env` and fill in
your key; `.env` is git-ignored). The dashboard's interactive page and all
evaluations need a valid key:

```dotenv
DEEPSEEK_API_KEY=your-api-key
# Optional:
DEEPSEEK_BASE_URL=https://api.deepseek.com
AGENT_MODEL=deepseek-v4-pro
USER_SIM_MODEL=deepseek-flash
JUDGE_MODEL=deepseek-flash
```

```bash
cd "ai concept project/iot_agent"
python -m pip install -r requirements.txt
```

## Run an evaluation

Run the topology-aware agent or either baseline against all available cases:

```bash
python -m eval.run_cases --system topology
python -m eval.run_cases --system vanilla_llm
python -m eval.run_cases --system vanilla_rag
```

Select cases with `--cases C001 C003`. Add `--judge-usability` to request a
separate model-judged support-usability score (1-5); this adds API calls. The
runner writes per-case results and `summary.json` under
`results/raw/<system>/`.

## Visual dashboard

After installing dependencies, start the Streamlit dashboard from the project
directory:

```bash
streamlit run app.py
```

The **交互诊断** page is a frontline-staff workbench: you select a synthetic case
and act as the support staff member relaying the customer's replies. The agent
checks the simulated support-console data, pauses to suggest a question to ask
the customer or an action to guide them through, then resumes after you enter
the customer's reply. It finishes with repair steps, a customer reply template
or an FAE escalation ticket. Enter a DeepSeek-compatible API key in `.env`
before starting a conversation. This is
not a connection to physical IoT devices; the console facts are read from the
selected case. The dashboard also browses labeled cases and displays saved run
metrics, predictions, support output, and tool traces.

Recreate the additional template-based cases with
`python -m eval.generate_cases`. This refuses to overwrite existing generated
cases unless `--force` is supplied.

Reported metrics are root-cause diagnosis success rate, average customer
interaction rounds, repeated-question rate, L1/L2 ticket classification
accuracy, and (when enabled) average model-judged usability. The repeated-
question rate counts exact duplicate customer questions after whitespace and
case normalization. A zero rate with no questions means no duplicate questions
were observed; usability is left unscored unless explicitly requested.

## Tests

The metric tests use only the Python standard library and can run without an
API key:

```bash
python -m unittest discover -s tests
```