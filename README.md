# DeciTrace AI

**Evidence-Grounded Business Decision Engine** · PS-04 — AI Decision Engine for Business Data

DeciTrace AI turns structured and unstructured business data into prioritised, explainable, evidence-backed decisions for a Sales / Operations Manager. Every recommendation carries a priority, a reason generated from the computed signal value, citations that resolve to real database rows, a recommended action, and an explicit human approval step.

It is not a chatbot. The core product is a business decision engine with a dashboard.

## Live demo

| What | Link |
|---|---|
| Application (frontend, Vercel) | https://frontend-two-liard-47.vercel.app |
| API (backend, Render) | https://decitrace-ai.onrender.com |
| API docs (OpenAPI) | https://decitrace-ai.onrender.com/docs |
| Health check | https://decitrace-ai.onrender.com/api/health |

**Suggested walkthrough (about 2 minutes):** Dashboard → Decisions (open *Blue Harbor Partners*) → Evidence → Approve a decision → Ask DeciTrace ("Which customers should the sales team prioritize today and why?") → Analytics (run the evaluation).

> **Note on free hosting.** The backend runs on a free Render instance, which goes to sleep after a period of inactivity. If the first load is slow (30–60 seconds) or shows *"Cannot reach the DeciTrace API"*, wait a minute and refresh. The demo database is re-seeded on every restart, so approvals made in the live demo do not persist across restarts. All data is synthetic.

## Contents

1. [What it does](#1-what-it-does)
2. [Architecture](#2-architecture-how-a-decision-is-produced)
3. [Screenshots](#3-screenshots)
4. [Project structure](#4-project-structure)
5. [Run locally](#5-run-locally)
6. [Environment variables](#6-environment-variables)
7. [Database setup](#7-database-setup)
8. [Seed command](#8-seed-command)
9. [API endpoints](#9-api-endpoints)
10. [Tests](#10-test-commands)
11. [Evaluation](#11-evaluation)
12. [Deployment (Render + Vercel)](#12-deployment-render--vercel)
13. [Troubleshooting](#13-troubleshooting)
14. [Known limitations](#14-known-limitations)
15. [Roadmap](#15-roadmap)
16. [Credits and AI disclosure](#16-credits-and-ai-disclosure)

---

## 1. What it does

Sales and operations teams ask the same question every morning: *which customers should we prioritise today, and why?* Most tools return a score with no proof. DeciTrace returns a ranked list where every decision is explained and auditable.

- **Five datasets** in a SQL database: customers, sales, product usage, support tickets, business notes.
- **Six weighted deterministic signals** (weights 22 / 24 / 20 / 12 / 12 / 10 = 100) produce a 0–100 priority score, banded into HIGH / MEDIUM / LOW with a confidence value.
- **Evidence retrieval (RAG)** over support tickets and business notes, with a verification layer: every citation must resolve to a real primary key.
- **Human in the loop:** a manager approves or rejects each decision; the action is stored with an audit event.
- **Ask DeciTrace:** plain-language questions are routed to analytics + retrieval workflows.
- **Evaluation harness:** five case types executed through the real pipeline with measured metrics.
- **Optional LLM** that only rephrases the explanation. Without an API key the deterministic template engine produces the same priority, reasons, evidence and actions.

The LLM never sets a priority, computes a metric, or invents a citation.

## 2. Architecture: how a decision is produced

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

**Stack:** FastAPI · SQLAlchemy · pandas · FAISS (TF-IDF embeddings by default, Sentence Transformers optional) · React · TypeScript · Tailwind · Vite · pytest.

## 3. Screenshots

Screenshots are in `docs/screenshots/`.

| Dashboard | Customers |
|---|---|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Customers](docs/screenshots/customers.png) |

| Decisions | Approved decision card |
|---|---|
| ![Decisions](docs/screenshots/decisions.png) | ![Approved decision](docs/screenshots/decision_card_approved.png) |

| Evidence trace | Ask DeciTrace |
|---|---|
| ![Evidence](docs/screenshots/evidence.png) | ![Ask](docs/screenshots/ask.png) |

| Analytics and evaluation |
|---|
| ![Analytics](docs/screenshots/analytics.png) |

## 4. Project structure

```
decitrace/
├── README.md
├── .env.example                  every environment variable, all optional
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
│   │   │   └── metrics.py        pandas metric layer, the ONLY source of business numbers
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
│   ├── vercel.json               production rewrite /api → Render backend
│   ├── tailwind.config.js · postcss.config.js · tsconfig.json · index.html
│   └── src/
│       ├── main.tsx · App.tsx · index.css
│       ├── lib/                  api.ts (typed client, no mocks) · format.ts
│       ├── components/           ui.tsx · DecisionCard.tsx
│       └── pages/                Dashboard · Customers · CustomerDetail ·
│                                 Decisions · Evidence · Analytics · Ask
├── scripts/                      run_all.sh · screenshot.py · serve_built.py
├── docs/                         API.md · screenshots/
└── data/                         SQLite DB, seed manifest, evaluation reports
```

## 5. Run locally

**Requirements:** Python 3.10+, Node.js 18+ and npm. No API key and no database server are needed.

### One command (macOS / Linux / Git Bash)

```bash
bash scripts/run_all.sh
```

Seeds the database, starts the API on `:8000` and the UI on `:5173`, and prints both URLs.

### Windows (Command Prompt), two terminals

Use a folder path **without** special characters such as `&` or `'`. Paths like `Hackathon's  & internship` break npm scripts on Windows.

Terminal 1, backend:

```
cd decitrace\backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy ..\.env.example ..\.env
python -m app.data.seed
python -m uvicorn app.main:app --reload --port 8000
```

Terminal 2, frontend:

```
cd decitrace\frontend
npm install
npm run dev
```

### macOS / Linux, manual

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env          # optional; all values have defaults
python -m app.data.seed             # create + seed the database
python -m uvicorn app.main:app --reload --port 8000

# frontend (new terminal)
cd frontend
npm install
npm run dev                         # http://localhost:5173
```

Open **http://localhost:5173** for the application and **http://localhost:8000/docs** for the OpenAPI reference.

The frontend proxies `/api` to `http://127.0.0.1:8000`, so the SPA is served same-origin and no CORS configuration is needed in development. To point at a different backend, set `VITE_PROXY_TARGET`.

### Lightweight install (without sentence-transformers)

`sentence-transformers` pulls in PyTorch (about 1–2 GB). It is optional: without it the app uses the TF-IDF embedder over the same FAISS index. To install without it:

```
findstr /v /i "sentence-transformers" requirements.txt > req-lite.txt
pip install -r req-lite.txt
```

(macOS / Linux: `grep -vi sentence-transformers requirements.txt > req-lite.txt`)

No API key is required. Without `LLM_API_KEY` the application runs its deterministic template engine: same priority, reasons, evidence and actions; only the sentence phrasing changes.

## 6. Environment variables

All are optional. Copy `.env.example` to `.env` to override.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/decitrace.db` | SQLite by default; PostgreSQL for production |
| `DECITRACE_DATA_DIR` | `./data` | DB, seed manifest, evaluation reports |
| `EMBEDDING_BACKEND` | `auto` | `auto` \| `sentence-transformers` \| `tfidf` |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Dense embedding model |
| `VECTOR_BACKEND` | `auto` | `auto` \| `faiss` \| `numpy` |
| `RAG_TOP_K` | `5` | Evidence records retrieved per decision |
| `RAG_MIN_SCORE` | `0.05` | Minimum cosine score for a retrieval hit |
| `LLM_PROVIDER` | `auto` | `auto` \| `openai` \| `gemini` \| `ollama` \| `none` |
| `LLM_API_KEY` | *(empty)* | Absent ⇒ deterministic template mode |
| `LLM_MODEL` | `gpt-4o-mini` | Model name for the configured provider |
| `LLM_BASE_URL` | *(empty)* | Override for OpenAI-compatible or Ollama endpoints |
| `LLM_TIMEOUT_SECONDS` | `25` | Remote call timeout before falling back |
| `PRIORITY_HIGH_THRESHOLD` | `55` | Score at which a customer becomes HIGH |
| `PRIORITY_MEDIUM_THRESHOLD` | `32` | Score at which a customer becomes MEDIUM |
| `CORS_ORIGINS` | `localhost:5173/4173` | Comma-separated allowed origins |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `VITE_PROXY_TARGET` | `http://127.0.0.1:8000` | Frontend dev-server proxy target |

Secrets are never hardcoded. `LLM_API_KEY` is read from the environment only, and `.env` is git-ignored.

**Example: enable an LLM (optional)**

```
LLM_PROVIDER=gemini
LLM_API_KEY=<your key>
LLM_MODEL=<a current Gemini model name>
```

or any OpenAI-compatible provider:

```
LLM_PROVIDER=openai
LLM_API_KEY=<your key>
LLM_MODEL=<model name>
LLM_BASE_URL=<provider's OpenAI-compatible URL>
```

If the key is missing, invalid or out of quota, the app falls back to deterministic mode automatically.

## 7. Database setup

**SQLite (default, zero configuration).** Nothing to install. The schema is created automatically on API startup and by the seed script.

```bash
cd backend
python -m app.data.seed          # drop, recreate and seed every table
python -m app.data.seed --keep   # preserve existing rows
python -m app.data.seed --customers 60
```

**PostgreSQL.** Create the database, then set the URL:

```bash
createdb decitrace
pip install psycopg2-binary
export DATABASE_URL="postgresql+psycopg2://user:password@localhost:5432/decitrace"
cd backend && python -m app.data.seed
```

The models use only portable SQLAlchemy types (`String`, `Float`, `Integer`, `Date`, `DateTime`, `Text`, `JSON`), so the same code is designed to run on both engines. On SQLite, foreign-key enforcement is switched on via a PRAGMA listener. The automated tests and the deployed demo run on SQLite.

### Tables (nine)

| Table | Key columns |
|---|---|
| `customers` | customer_id, customer_name, industry, region, segment, account_value, status, owner, onboarded_on, archetype |
| `sales` | transaction_id, customer_id, date, amount, product, quantity, channel |
| `usage_records` | customer_id, date, active_users, sessions, usage_minutes |
| `support_tickets` | ticket_id, customer_id, issue, description, severity, status, created_at, resolved_at, assignee |
| `business_notes` | note_id, customer_id, note_text, author_role, note_type, date |
| `decisions` | decision_id, customer_id, priority, priority_score, decision_text, action_type, reasons, signals, explanation, status, engine_mode, llm_used |
| `decision_evidence` | decision_id, rank, source_table, source_id, evidence_type, title, snippet, score, retrieval_method, payload |
| `decision_events` | decision_id, event_type, actor, note, created_at |
| `evaluation_runs` | run_id, started_at, duration_ms, metrics, results, engine_mode |

## 8. Seed command

```bash
cd backend
python -m app.data.seed
```

Generates a fully synthetic, public-safe dataset (seeded RNG, reproducible):

```
customers       : 28
sales           : 1729
usage           : 2760
support_tickets : 25
business_notes  : 50
manifest        : ../data/seed_manifest.json
```

The *reference date* is derived from the generated data, so exact dates and a few computed values can differ slightly between seed runs.

Every customer is built from one of nine archetypes that define its behaviour and act as the ground truth for evaluation:

| Archetype | Behaviour | Expected priority |
|---|---|---|
| healthy | Steady revenue and adoption, clean support | LOW |
| growth | Expanding usage and spend | LOW |
| low_value | Small account, mild dip, low materiality | LOW |
| churn_risk | Revenue −48%, usage −38%, open critical ticket | HIGH |
| silent_churn | Champion departed, usage −52%, no loud signal | HIGH |
| declining_usage | Usage −45%, commercial roughly holding | MEDIUM |
| support_escalation | Two open critical tickets, metrics unaffected | MEDIUM |
| seasonal_dip | Revenue −30%, plausibly seasonal, no other signal | LOW |
| new_customer | 24 days of history, not enough to decide | LOW |

## 9. API endpoints

Interactive docs: `http://localhost:8000/docs` locally, or https://decitrace-ai.onrender.com/docs on the live demo. Full examples are in `docs/API.md`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Engine mode, row counts, RAG backend, LLM status |
| GET | `/api/dashboard` | KPIs, attention queue, distributions, pipeline, data health |
| GET | `/api/customers` | Account list; filters `q`, `priority`, `region`, `status`, `limit` |
| GET | `/api/customers/{id}` | Full account: KPIs, signals, series, timeline, tickets, notes |
| GET | `/api/decisions` | Decision list; filters `priority`, `status`, `q`, `limit` |
| GET | `/api/decisions/{id}` | Full decision with signals, reasons, action and evidence |
| GET | `/api/evidence/{decision_id}` | Evidence trace for one decision |
| GET | `/api/evaluation` | Latest measured evaluation, or *Evaluation pending* |
| GET | `/api/ask/examples` | Suggested questions and supported workflow intents |
| POST | `/api/ask` | Ask DeciTrace: routes the question to a workflow |
| POST | `/api/decisions/{id}/approve` | Human approval (persisted) |
| POST | `/api/decisions/{id}/reject` | Human rejection (persisted) |
| POST | `/api/evaluate` | Execute the evaluation harness |
| POST | `/api/admin/regenerate-decisions` | Re-score the whole book |

### Example: Ask DeciTrace

```bash
curl -X POST http://localhost:8000/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Which customers should the sales team prioritize today and why?","limit":3}'
```

Abridged example output (exact values vary slightly by seed run):

```json
{
  "intent": "priority_overview",
  "intent_label": "Prioritised attention queue",
  "latency_ms": 392,
  "analytics": {
    "customers_analyzed": 28,
    "decisions_considered": 28,
    "high_priority": 4,
    "revenue_at_risk_90d": 4646896
  },
  "results": [
    { "priority": "HIGH", "priority_score": 84.0, "customer_name": "Blue Harbor Partners" },
    { "priority": "HIGH", "priority_score": 80.9, "customer_name": "Summit Logistics" },
    { "priority": "HIGH", "priority_score": 72.5, "customer_name": "Fairwind Retail" }
  ]
}
```

### Example: human approval

```bash
curl -X POST http://localhost:8000/api/decisions/<DECISION_ID>/approve \
  -H 'Content-Type: application/json' \
  -d '{"actor":"sales.manager@example.com","note":"Approved: escalate today"}'
```

Stores `status = approved`, appends a `decision_events` audit row, and returns the AI recommendation, the human decision and the timestamp. Re-reviewing the same decision returns `409 Conflict` instead of silently double-writing.

## 10. Test commands

```bash
cd backend
python -m pytest -q                         # full suite (31 tests)
python -m pytest tests/test_pipeline.py -v  # verbose, per test
python -m pytest -k "rag or evidence" -v    # retrieval / non-fabrication tests
python -m pytest -k "approve" -v            # human-in-the-loop tests
```

`python -m pytest` is recommended, especially on Windows, because it puts the current folder on the import path (plain `pytest` can fail with `No module named 'app'`).

**Current status: 31 passed.**

| Area | What is asserted |
|---|---|
| Data | All five synthetic datasets exist; `reference_date` derives from the data |
| Analytics | Metric deltas recompute exactly; revenue shares sum to 100% ± 0.5 |
| Signals | Weights sum to 100; every reason string carries its own numeric value; scoring is deterministic |
| Banding | 55 / 32 thresholds behave exactly at the boundary |
| RAG | Index builds; a customer-scoped search returns only that customer's rows |
| Non-fabrication | Every retrieved citation resolves to a real `business_notes` / `support_tickets` primary key |
| Decision engine | Complete explainable bundle; confidence falls when data is missing; priority mix is non-flat |
| API | Every documented GET answers 200; 404 on unknown ids; empty question → 422 |
| Human-in-the-loop | Approve persists, re-approve → 409, status visible on read, reject path works |
| Ask DeciTrace | Different questions route to different workflows; named-customer explanation resolves correctly |
| Evaluation | Metrics are internally consistent; run is retrievable afterwards |

## 11. Evaluation

```bash
cd backend
python -m app.evaluation.harness
```

or `POST /api/evaluate`, or the **Run evaluation** button on the Analytics page.

Five synthetic case types are executed through the real decision pipeline: normal, high-risk, multi-signal, ambiguous, insufficient-evidence. Ground truth is the archetype the generator used to build each account.

If the harness has never run, the API returns `status: "Evaluation pending"` with no metrics at all, and the UI shows an *Evaluation pending* panel. Metrics are only displayed after an actual execution.

### Measured results (28 cases, local run on the TF-IDF backend)

```
DeciTrace AI: evaluation harness
  run id                 : EVAL-261001-145515-4288
  cases executed         : 28
  decision accuracy      : 89.3%
  adjacent accuracy      : 96.4%
  evidence hit rate      : 100.0%
  evidence verification  : 100.0%
  avg response           : 0 ms
  p95 response           : 1 ms
  escalation failure rate: 3.6%
  insufficient-evidence  : 0.0%

  by case type:
    normal                 n=10  accuracy=100.0%  evidence_hit=100.0%
    high_risk              n=6   accuracy= 66.7%  evidence_hit=100.0%
    multi_signal           n=7   accuracy=100.0%  evidence_hit=100.0%
    ambiguous              n=2   accuracy= 50.0%  evidence_hit=100.0%
    insufficient_evidence  n=3   accuracy=100.0%  evidence_hit=100.0%
```

- **Adjacent accuracy** (96.4%) is the tolerance-aware measure: a prediction within one priority band counts.
- **Escalation failure rate** (3.6%, 1 of 28 cases) is the commercially important one: a HIGH-expectation account scored LOW.
- **Response time** in this table is the in-process engine time per case, not end-to-end API latency. A full `/api/ask` request takes a few hundred milliseconds.
- Results can differ slightly between runs because the reference date and some generated values depend on the seed run (an earlier build measured 85.7% decision accuracy).

Reports are written to `data/evaluation_<run_id>.json` and `data/evaluation_latest.json`.

## 12. Deployment (Render + Vercel)

The live demo is split into a Python API on Render and a static React app on Vercel. Both run on free tiers.

### Backend on Render

Create a **Web Service** from this repository with:

| Setting | Value |
|---|---|
| Root Directory | `backend` |
| Runtime | Python 3 |
| Build Command | `sed '/sentence-transformers/Id' requirements.txt > r-deploy.txt && pip install -r r-deploy.txt` |
| Start Command | `python -m app.data.seed && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Plan | Free |
| Environment variables | none required |

Notes:

- `sentence-transformers` (PyTorch) is excluded from the deploy build because it does not fit the free instance memory. The deployed API therefore uses the TF-IDF embedder with FAISS, and runs in deterministic template mode (no LLM key).
- The start command re-seeds the database on every start. Render's free tier has no persistent disk, so demo data resets on restart. This is intentional for a reproducible demo.
- Free instances sleep after inactivity; the first request after a sleep can take 30–60 seconds. An uptime monitor that calls `/api/health` every 5 minutes keeps the instance awake.

### Frontend on Vercel

The frontend calls relative `/api/...` paths. In production, `frontend/vercel.json` rewrites them to the Render backend and serves the SPA for all other routes:

```json
{
  "rewrites": [
    { "source": "/api/(.*)", "destination": "https://decitrace-ai.onrender.com/api/$1" },
    { "source": "/((?!api/).*)", "destination": "/index.html" }
  ]
}
```

Deploy from the `frontend` folder:

```bash
cd frontend
npx vercel login
npx vercel --prod
```

Vercel auto-detects Vite (`npm run build`, output `dist`). If you deploy your own backend, change the `destination` URL in `vercel.json`.

### Docker

Docker files are not included yet; see the [Roadmap](#15-roadmap).

## 13. Troubleshooting

| Problem | Fix |
|---|---|
| `npm run dev` fails with `'...\node_modules\.bin\' is not recognized` | The project folder path contains `&` or `'`. Move the project to a simple path such as `D:\decitrace`, delete `node_modules`, and run `npm install` again. |
| `pip install` fails with `No space left on device` | Free disk space on the system drive, or set `TEMP` and `TMP` to another drive. Skip `sentence-transformers` (see *Lightweight install*). |
| `pip install` fails on `faiss-cpu` | Remove the `faiss-cpu` line; the app falls back to an exact numpy cosine index (`VECTOR_BACKEND=auto`). |
| `.venv\Scripts\activate` blocked in PowerShell | Run `Set-ExecutionPolicy -Scope Process Bypass`, or use Command Prompt. |
| `pytest` says `No module named 'app'` | Run `python -m pytest -q` from the `backend` folder. |
| UI shows *Cannot reach the DeciTrace API* | The backend is not running (locally) or is waking up (Render). Start it or wait a minute and refresh. |
| Analytics shows *Evaluation pending* | Click **Run evaluation** or run `python -m app.evaluation.harness`. |
| Copied project does not start | Recreate `.venv` and `node_modules` in the new location; virtual environments contain absolute paths. |
| Need a fresh database | Delete `data/decitrace.db` and run `python -m app.data.seed`. |

## 14. Known limitations

- **Retrieval quality.** The default backend is a deterministic TF-IDF + signed-hashing embedder, with FAISS doing exact inner-product search. Retrieval is real and every hit is verified, but dense semantic ranking needs `pip install sentence-transformers`. Set `EMBEDDING_BACKEND=sentence-transformers` to require it, or leave `auto` to use it whenever importable. The live demo uses the TF-IDF backend.
- **Evaluation ground truth is synthetic.** Accuracy is measured against the archetype used by the generator, not against human-annotated labels. It validates the pipeline end to end; it is not an external benchmark. `high_risk` accuracy is 66.7% and `ambiguous` 50.0%; the ambiguous archetype is designed to be undecidable without more signals, so 50% there is the intended behaviour.
- **`revenue_materiality` is double-edged by design.** A very large stable account can reach MEDIUM on size alone. This is deliberate (a large account is worth a check-in), but it means size and distress are not fully orthogonal. `reasons` always names the signals that drove the score.
- **Scoring weights are hand-tuned**, not fitted (22 / 24 / 20 / 12 / 12 / 10). There is no labelled outcome data to optimise against, so the weights are documented in the UI and in `signals.py` rather than presented as learned parameters.
- **Approval identity is not authenticated.** The reviewer is a free-text `actor` field. There is no login or role model; the audit trail records what was decided, not a verified who.
- **Synthetic data only.** All names, companies, tickets and notes are invented by a seeded generator. No real personal or customer data is present.
- **Concurrency.** Decisions are regenerated by dropping and rewriting the decisions tables inside one transaction. This is fine at demo scale but not designed for simultaneous heavy traffic, and it discards previous decision history.
- **Demo hosting.** The live demo runs on free tiers: the API can sleep when idle, and the demo database is re-seeded on restart.

## 15. Roadmap

Planned improvements, not yet implemented:

1. **Security:** authentication and role-based access (JWT), verified approver identity, admin-only regenerate/evaluate endpoints.
2. **Data layer:** PostgreSQL in production with Alembic migrations; append-only decision versioning instead of drop-and-rewrite.
3. **Packaging and CI:** Dockerfiles and `docker-compose`, pinned dependencies, GitHub Actions running `pytest` and `npm run build` on every push.
4. **Observability:** structured logging, error tracking, health/uptime monitoring, drift and quality tracking for decisions.
5. **Retrieval:** dense embeddings in the deployed build, hybrid (keyword + vector) search, reranking.
6. **Real data:** CSV upload and CRM connectors in place of the synthetic generator; fit and validate signal weights against real outcomes (for example churn).
7. **Operations:** scheduled nightly re-scoring and a feedback loop that measures approval accuracy over time.

## 16. Credits and AI disclosure

- **Team:** Mehak Rana (team lead), Nikhil Dagar.
- **AI assistance:** this project was built with the help of an AI coding agent. The team defined the problem and requirements, ran, tested and verified the system, and handled deployment and documentation. The measured numbers in this README come from real runs of the test suite and the evaluation harness.
- **Problem statement:** PS-04, AI Decision Engine for Business Data.
- **Data:** fully synthetic and public-safe.
