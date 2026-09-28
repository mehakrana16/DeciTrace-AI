# DeciTrace AI

**Evidence-Grounded Business Decision Engine** · `PS-04 — AI Decision Engine for Business Data`

DeciTrace AI turns structured and unstructured business data into **prioritised, explainable, evidence-backed
decisions** for a Sales / Operations Manager. Every recommendation carries a priority, a reason generated from the
computed signal value, citations that resolve to real database rows, a recommended action, and an explicit
**human approval** step.

It is **not** a chatbot. The core product is a business decision engine with a dashboard.

---

## 1. Project structure

```
decitrace/
├── README.md                     ← this file
├── .env.example                  ← every environment variable, all optional
├── backend/
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py               FastAPI app, CORS, timing middleware, error handlers
│   │   ├── config.py             env-driven settings (no hardcoded secrets)
│   │   ├── schemas.py            Pydantic request/response contracts
│   │   ├── data/
│   │   │   ├── db.py             SQLAlchemy engine / session (SQLite ⇄ PostgreSQL)
│   │   │   ├── models.py         customers, sales, usage_records, support_tickets,
│   │   │   │                     business_notes, decisions, decision_evidence,
│   │   │   │                     decision_events, evaluation_runs
│   │   │   └── seed.py           synthetic data generator (9 account archetypes)
│   │   ├── analytics/
│   │   │   └── metrics.py        pandas metric layer — the ONLY source of business numbers
│   │   ├── rag/
│   │   │   ├── embeddings.py     sentence-transformers ⇄ deterministic TF-IDF fallback
│   │   │   ├── index.py          FAISS ⇄ exact numpy cosine vector index
│   │   │   └── retriever.py      retrieval + verification + structured evidence
│   │   ├── decision_engine/
│   │   │   ├── signals.py        6 weighted deterministic signals
│   │   │   └── engine.py         scoring, banding, confidence, persistence
│   │   ├── llm/
│   │   │   └── explainer.py      optional LLM phrasing ⇄ deterministic templates
│   │   ├── evaluation/
│   │   │   ├── harness.py        5 case types, measured metrics
│   │   │   └── __main__.py       CLI entry point
│   │   └── api/
│   │       ├── routes.py         all REST endpoints
│   │       └── ask.py            question → workflow router for Ask DeciTrace
│   └── tests/
│       ├── conftest.py           isolated temp SQLite DB per test session
│       └── test_pipeline.py      31 tests across data, analytics, RAG, engine, API, eval
├── frontend/
│   ├── package.json
│   ├── vite.config.ts            dev + preview proxy /api → :8000
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx               shell, navigation, status bar
│       ├── index.css             Tailwind layers + component classes
│       ├── lib/
│       │   ├── api.ts            typed API client (no mocks)
│       │   └── format.ts         currency/percent/date + priority colour tokens
│       ├── components/
│       │   ├── ui.tsx            cards, KPIs, donut, line chart, bar list, states
│       │   └── DecisionCard.tsx  decision card with working Approve / Reject
│       └── pages/
│           ├── Dashboard.tsx     "what requires attention right now?"
│           ├── Customers.tsx     filterable account book
│           ├── CustomerDetail.tsx KPIs, charts, signals, timeline, tickets, notes
│           ├── Decisions.tsx     review queue
│           ├── Evidence.tsx      evidence trace browser
│           ├── Analytics.tsx     portfolio analytics + evaluation metrics
│           └── Ask.tsx           Ask DeciTrace decision interface
├── scripts/
│   ├── run_all.sh                one-command local launch
│   └── screenshot.py             Playwright screenshot capture
├── docs/
│   ├── API.md                    endpoint reference with request/response examples
│   └── screenshots/              captured application screenshots
└── data/                         SQLite DB, seed manifest, evaluation reports
```

---

## 2. How to run locally

### One command

```bash
bash scripts/run_all.sh
```

Seeds the database, starts the API on **:8000** and the UI on **:5173**, and prints both URLs.

### Manual, step by step

```bash
# ---------- backend ----------
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp ../.env.example ../.env                            # optional; all values have defaults
python -m app.data.seed                               # create + seed the database
python -m uvicorn app.main:app --reload --port 8000

# ---------- frontend (new terminal) ----------
cd frontend
npm install
npm run dev                                           # http://localhost:5173
```

Open **http://localhost:5173** for the application and **http://localhost:8000/docs** for the OpenAPI reference.

> The frontend proxies `/api` to `http://127.0.0.1:8000`, so the SPA is served same-origin and no CORS
> configuration is required in development. To point at a different backend, set `VITE_PROXY_TARGET`.
>
> **No API key is required.** Without `LLM_API_KEY` the application runs its deterministic template engine — same
> priority, reasons, evidence and actions; only the sentence phrasing changes.

---

## 3. Environment variables required

All are optional. Copy `.env.example` to `.env` to override.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/decitrace.db` | SQLite by default; point at PostgreSQL for production |
| `DECITRACE_DATA_DIR` | `./data` | Where the DB, seed manifest and evaluation reports are written |
| `EMBEDDING_BACKEND` | `auto` | `auto` \| `sentence-transformers` \| `tfidf` |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Dense embedding model |
| `VECTOR_BACKEND` | `auto` | `auto` \| `faiss` \| `numpy` |
| `RAG_TOP_K` | `5` | Evidence records retrieved per decision |
| `RAG_MIN_SCORE` | `0.05` | Minimum cosine score for a retrieval hit |
| `LLM_PROVIDER` | `auto` | `auto` \| `openai` \| `gemini` \| `ollama` \| `none` |
| `LLM_API_KEY` | *(empty)* | **Absent ⇒ deterministic template mode** |
| `LLM_MODEL` | `gpt-4o-mini` | Model name for the configured provider |
| `LLM_BASE_URL` | *(empty)* | Override for OpenAI-compatible or Ollama endpoints |
| `LLM_TIMEOUT_SECONDS` | `25` | Remote call timeout before falling back |
| `PRIORITY_HIGH_THRESHOLD` | `55` | Score at which a customer becomes HIGH |
| `PRIORITY_MEDIUM_THRESHOLD` | `32` | Score at which a customer becomes MEDIUM |
| `CORS_ORIGINS` | localhost:5173/4173 | Comma-separated allowed origins |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

**Secrets are never hardcoded.** `LLM_API_KEY` is read from the environment only, and the application is fully
functional without it.

---

## 4. Database setup

**SQLite (default — zero configuration).** Nothing to install. The schema is created automatically on API startup
and by the seed script.

```bash
cd backend
python -m app.data.seed          # drop, recreate and seed every table
python -m app.data.seed --keep   # seed only if you want to preserve existing rows
python -m app.data.seed --customers 60
```

**PostgreSQL.** Create the database, then set the URL:

```bash
createdb decitrace
pip install psycopg2-binary
export DATABASE_URL="postgresql+psycopg2://user:password@localhost:5432/decitrace"
cd backend && python -m app.data.seed
```

The models use only portable SQLAlchemy types (`String`, `Float`, `Integer`, `Date`, `DateTime`, `Text`, `JSON`),
so the same code runs on both engines. On SQLite, foreign-key enforcement is switched on via a `PRAGMA` listener.

### Tables

| Table | Key columns |
|---|---|
| `customers` | `customer_id`, `customer_name`, `industry`, `region`, `segment`, `account_value`, `status`, `owner`, `onboarded_on`, `archetype` |
| `sales` | `transaction_id`, `customer_id`, `date`, `amount`, `product`, `quantity`, `channel` |
| `usage_records` | `customer_id`, `date`, `active_users`, `sessions`, `usage_minutes` |
| `support_tickets` | `ticket_id`, `customer_id`, `issue`, `description`, `severity`, `status`, `created_at`, `resolved_at`, `assignee` |
| `business_notes` | `note_id`, `customer_id`, `note_text`, `author_role`, `note_type`, `date` |
| `decisions` | `decision_id`, `customer_id`, `priority`, `priority_score`, `decision_text`, `action_type`, `reasons`, `signals`, `explanation`, `status`, `engine_mode`, `llm_used` |
| `decision_evidence` | `decision_id`, `rank`, `source_table`, `source_id`, `evidence_type`, `title`, `snippet`, `score`, `retrieval_method`, `payload` |
| `decision_events` | `decision_id`, `event_type`, `actor`, `note`, `created_at` |
| `evaluation_runs` | `run_id`, `started_at`, `duration_ms`, `metrics`, `results`, `engine_mode` |

---

## 5. Seed command

```bash
cd backend
python -m app.data.seed
```

Generates a fully synthetic, public-safe world (seeded RNG, reproducible):

```
reference date : 2026-09-26
customers       : 28
sales           : 1729
usage           : 2760
support_tickets : 25
business_notes  : 50
manifest        : ../data/seed_manifest.json
```

Every customer is built from one of nine **archetypes** that define its behaviour and act as the ground truth for
evaluation:

| Archetype | Behaviour | Expected priority |
|---|---|---|
| `healthy` | Steady revenue and adoption, clean support | LOW |
| `growth` | Expanding usage and spend | LOW |
| `low_value` | Small account, mild dip, low materiality | LOW |
| `churn_risk` | Revenue −48%, usage −38%, open critical ticket | HIGH |
| `silent_churn` | Champion departed, usage −52%, no loud signal | HIGH |
| `declining_usage` | Usage −45%, commercial roughly holding | MEDIUM |
| `support_escalation` | Two open critical tickets, metrics unaffected | MEDIUM |
| `seasonal_dip` | Revenue −30%, plausibly seasonal, no other signal | LOW |
| `new_customer` | 24 days of history — not enough to decide | LOW |

---

## 6. API endpoints

Interactive docs: **http://localhost:8000/docs**

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Engine mode, row counts, RAG backend, LLM status |
| `GET` | `/api/dashboard` | KPIs, attention queue, distributions, pipeline, data health |
| `GET` | `/api/customers` | Account list; filters `q`, `priority`, `region`, `status`, `limit` |
| `GET` | `/api/customers/{id}` | Full account: KPIs, signals, series, timeline, tickets, notes |
| `GET` | `/api/decisions` | Decision list; filters `priority`, `status`, `q`, `limit` |
| `GET` | `/api/decisions/{id}` | Full decision with signals, reasons, action and evidence |
| `GET` | `/api/evidence/{decision_id}` | Evidence trace for one decision |
| `GET` | `/api/evaluation` | Latest measured evaluation, or `Evaluation pending` |
| `GET` | `/api/ask/examples` | Suggested questions and the supported workflow intents |
| `POST` | `/api/ask` | Ask DeciTrace — routes the question to a workflow |
| `POST` | `/api/decisions/{id}/approve` | Human approval (persisted) |
| `POST` | `/api/decisions/{id}/reject` | Human rejection (persisted) |
| `POST` | `/api/evaluate` | Execute the evaluation harness |
| `POST` | `/api/admin/regenerate-decisions` | Re-score the whole book |

### Example — verified live output

```bash
curl -X POST http://localhost:8000/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Which customers should the sales team prioritize today and why?","limit":3}'
```

```json
{
  "intent": "priority_overview",
  "intent_label": "Prioritised attention queue",
  "latency_ms": 231.34,
  "analytics": {
    "customers_analyzed": 28,
    "decisions_considered": 28,
    "high_priority": 4,
    "revenue_at_risk_90d": 4660381.67
  },
  "results": [
    { "priority": "HIGH", "priority_score": 84.0, "customer_name": "Blue Harbor Partners" },
    { "priority": "HIGH", "priority_score": 79.7, "customer_name": "Summit Logistics" },
    { "priority": "HIGH", "priority_score": 72.5, "customer_name": "Fairwind Retail" }
  ]
}
```

### Human-in-the-loop

```bash
curl -X POST http://localhost:8000/api/decisions/DEC-260926-0025/approve \
  -H 'Content-Type: application/json' \
  -d '{"actor":"sales.manager@example.com","note":"Approved — escalate today"}'
```

Stores `status = approved`, appends a `decision_events` audit row, and returns the AI recommendation, the human
decision and the timestamp. Re-reviewing the same decision returns **409 Conflict** rather than silently
double-writing.

---

## 7. Test commands

```bash
cd backend
pytest -q                                   # full suite (31 tests)
pytest tests/test_pipeline.py -v            # verbose, per test
pytest -k "rag or evidence" -v              # retrieval / non-fabrication tests only
pytest -k "approve" -v                      # human-in-the-loop tests
```

Current status — **31 passed**:

| Area | What is asserted |
|---|---|
| Data | All five synthetic datasets exist; `reference_date` derives from the data |
| Analytics | Metric deltas recompute exactly; revenue shares sum to 100% ± 0.5 |
| Signals | Weights sum to 100; every reason string carries its own numeric value; scoring is deterministic |
| Banding | 55/32 thresholds behave exactly at the boundary |
| RAG | Index builds; a customer-scoped search returns only that customer's rows |
| **Non-fabrication** | **Every retrieved citation resolves to a real `business_notes` / `support_tickets` primary key** |
| Decision engine | Complete explainable bundle; confidence falls when data is missing; priority mix is non-flat |
| API | Every documented GET answers 200; 404s on unknown ids; empty question → 422 |
| Human-in-the-loop | Approve persists, re-approve → 409, status visible on read, reject path works |
| Ask DeciTrace | Different questions route to different workflows; named-customer explanation resolves correctly |
| Evaluation | Metrics are internally consistent; run is retrievable afterwards |

---

## 8. Evaluation command

```bash
cd backend
python -m app.evaluation.harness
```

or `POST /api/evaluate`, or the **Run evaluation** button on the Analytics page.

Five synthetic case types are executed **through the real decision pipeline** — normal, high-risk, multi-signal,
ambiguous, insufficient-evidence. Ground truth is the archetype the generator used to build each account.

If the harness has never run, the API returns `status: "Evaluation pending"` with **no metrics at all**, and the UI
renders an "Evaluation pending" panel. Metrics are only ever displayed after an actual execution.

### Measured results (this build, 28 cases)

```
DeciTrace AI — evaluation harness
  run id                 : EVAL-260926-062859-4ee8
  cases executed         : 28
  decision accuracy      : 85.7%
  adjacent accuracy      : 96.4%
  evidence hit rate      : 100.0%
  evidence verification  : 100.0%
  avg response           : 0.58 ms
  p95 response           : 0.76 ms
  escalation failure rate: 3.6%
  insufficient-evidence  : 0.0%

  by case type:
    normal                 n=10  accuracy= 90.0%  evidence_hit=100.0%
    high_risk              n=6   accuracy= 66.7%  evidence_hit=100.0%
    multi_signal           n=7   accuracy=100.0%  evidence_hit=100.0%
    ambiguous              n=2   accuracy= 50.0%  evidence_hit=100.0%
    insufficient_evidence  n=3   accuracy=100.0%  evidence_hit=100.0%
```

`adjacent accuracy` (96.4%) is the tolerance-aware measure. `escalation failure rate` (3.6% — 1 of 28 cases) is the
commercially important one: a HIGH-expectation account scored LOW. Reports are written to
`data/evaluation_<run_id>.json` and `data/evaluation_latest.json`.

---

## 9. Known limitations

**Retrieval quality.** This build runs the deterministic TF-IDF + signed-hashing embedding backend (the sandbox had
no `sentence-transformers` wheel available), with FAISS doing the exact inner-product search. Retrieval is real and
every hit is verified, but dense semantic ranking needs `pip install sentence-transformers` — set
`EMBEDDING_BACKEND=sentence-transformers` to require it, or leave `auto` to use it whenever importable.

**Evaluation ground truth is synthetic.** Accuracy is measured against the archetype the generator used, not against
a human-annotated label set. It validates the pipeline end-to-end; it is not an external benchmark. `high_risk`
accuracy is 66.7% and `ambiguous` 50.0% — the ambiguous archetype is *designed* to be undecidable without more
signals, so a 50% result there is the intended behaviour, not a defect.

**The `revenue_materiality` signal is double-edged by design.** A very large account can accumulate enough
materiality points to reach MEDIUM on size alone. This is deliberate (a large stable account is worth a check-in)
but it means size and distress are not fully orthogonal. `reasons` always names which signals drove the score, so
the distinction is visible.

**Scoring weights are hand-tuned.** The six weights (22/24/20/12/12/10) are reasoned, not fitted. There is no
labelled outcome data to optimise against, so they are documented in the UI and in `signals.py` rather than
presented as learned parameters.

**Approval identity is not authenticated.** The reviewer is a free-text `actor` field defaulting to
`sales.manager@example.com`. There is no login, role model or signature — the audit trail records *what was
decided*, not a verified *who*.

**Synthetic data only.** All names, companies, tickets and notes are invented by a seeded generator. No real
personal or customer data is present anywhere in this project.

**Concurrency.** Procedure at demo scale: decisions are regenerated by dropping and rewriting the `decisions`
tables inside one transaction, so a regenerate request during heavy concurrent traffic is not supported.

---

## Architecture: how a decision is produced

```
business rows (SQLite / PostgreSQL)
      ↓  pandas 30d / 14d / 90d windows
structured analytics                     ← the only source of business numbers
      ↓
6 weighted deterministic signals         ← 22 + 24 + 20 + 12 + 12 + 10 = 100 points
      ↓
RAG evidence retrieval                   ← vector search over notes + tickets
      ↓
verification layer                       ← every citation must resolve to a real primary key
      ↓
signal fusion → score → HIGH / MEDIUM / LOW + confidence
      ↓
priority · reason · evidence trace · recommended action
      ↓
LLM phrasing (optional)                  ← may rephrase the sentence, never the metric
      ↓
HUMAN APPROVAL  [ APPROVE ] [ REJECT ]   ← persisted with an audit trail
```

The LLM never sets a priority, computes a metric, or invents a citation. With no API key the deterministic
template writer produces the same structure from the same computed values.
