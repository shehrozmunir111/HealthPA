# HealthPA

> Multi-tenant healthcare prior-authorization SaaS with grounded, human-reviewed AI medical coding.

HealthPA is a production-ready, multi-tenant healthcare platform built on FastAPI. It provides
hospital-scoped data isolation, a full prior-authorization workflow, asynchronous email
notifications via AWS SES, appointment scheduling with automated reminders, fraud detection, and a
**grounded AI coding layer** (RAG + human-in-the-loop review + evaluation). The codebase ships with
**138 passing tests** on a PostgreSQL-backed suite; the AI tests run fully offline.

**Status:** 138 tests passing · Python 3.11 · FastAPI · PostgreSQL 15 · LangGraph · Pinecone · RAGAS

## Table of Contents

- [Highlights](#highlights)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [Local Development](#local-development)
- [Docker](#docker)
- [API Reference](#api-reference)
- [AI: Grounded Coding, Human Review & Eval](#ai-grounded-coding-human-review--eval)
- [Email Features](#email-features)
- [Testing](#testing)
- [Security Notes](#security-notes)

---

## Highlights

- **Multi-tenant isolation** — every record is scoped by `hospital_id`; cross-hospital access is architecturally impossible
- **JWT authentication** — HS256 tokens with hospital + role claims validated on every request
- **Email verification on signup** — token-based, 24-hour expiry, re-send endpoint included
- **Password reset flow** — secure one-time token, 1-hour expiry, anti-enumeration responses
- **Fraud / lockout detection** — tracks failed login attempts; locks account and emails admin on threshold breach
- **Appointment scheduling** — full CRUD with hospital isolation and status FSM
- **24-hour appointment reminders** — Celery Beat scheduled task; duplicate-safe via `reminder_sent` flag
- **AWS SES email** — all emails dispatched via Celery tasks; API response never blocks on SES
- **Prior authorization workflow** — finite-state machine with strict transition validation
- **OCR upload pipeline** — Celery-backed Tesseract + pdf2image processing
- **Batch CSV import** — patients and PA requests via multipart upload
- **Analytics** — PA summaries, processing times, payer breakdown, daily trends
- **Redis caching** — TTL-based with hospital/patient cache invalidation
- **Rate limiting** — in-memory sliding window (10 req/60s auth, 100 req/60s general)
- **HIPAA audit trail** — every create/read/update/delete logged to `audit_logs`
- **AI grounded coding** — RAG-grounded ICD-10/CPT extraction with citations, human-in-the-loop review (LangGraph `interrupt`/resume), multi-agent routing, and RAGAS evaluation (see below)

---

## Tech Stack

| Component | Technology |
|---|---|
| API | FastAPI 0.109 |
| Language | Python 3.11+ |
| Database | PostgreSQL 15 |
| ORM | SQLAlchemy 2.0 (async) |
| Cache | Redis 7 |
| Task Queue | Celery 5 + Celery Beat |
| Email | AWS SES via boto3 |
| OCR | Tesseract + pdf2image |
| AI orchestration | LangGraph + LangChain (HITL `interrupt`/resume) |
| LLM / embeddings | LM Studio (gemma, nomic) by default; Groq / OpenAI / Anthropic via env |
| Vector store | Pinecone (per-hospital namespaces) |
| Evaluation | RAGAS + deterministic metrics |
| Observability | LangSmith (optional, env-gated) |
| Containers | Docker + Docker Compose |
| Testing | pytest, pytest-asyncio, httpx |

---

## Project Structure

```
HealthPA/
├── app/
│   ├── core/                        # config, database, security, middleware, cache, celery
│   ├── models/                      # hospital, user, patient, pa_request, appointment, audit_log
│   ├── routes/
│   │   ├── auth.py                  # login, email verification, password reset, lockout
│   │   ├── appointments.py
│   │   ├── hospitals.py / patients.py / pa_requests.py
│   │   ├── batch.py / analytics.py
│   │   └── pa_ai.py                 # AI grounded-coding endpoints  (/api/v1/...)
│   ├── schemas/                     # Pydantic models (+ codes.py for the AI layer)
│   ├── services/
│   │   ├── ai_engine.py             # legacy Groq extractor (rule/LLM fallback)
│   │   ├── ocr_service.py / webhook_service.py / audit_service.py
│   │   ├── llm_provider.py          # chat + embeddings factory (LM Studio / Groq / cloud)
│   │   ├── vector_store.py          # Pinecone ↔ in-memory, per-hospital namespaces
│   │   ├── rag_service.py           # ingest / retrieve / grade / rewrite / fingerprint cache
│   │   ├── reranker.py              # lexical + LLM rerank
│   │   ├── grounded_extractor.py    # citation-grounded code extraction (+ rule backstop)
│   │   ├── guardrails.py            # input / output guards
│   │   ├── code_extraction_graph.py # LangGraph HITL (interrupt / resume)
│   │   ├── coding_supervisor.py     # multi-agent router
│   │   ├── coding_agent.py          # ReAct policy-QA agent (+ Tavily)
│   │   └── long_term_memory.py      # per-coder / per-hospital recall
│   ├── eval/                        # evaluators + RAGAS + labelled dataset (cases.json)
│   ├── tasks/email.py               # Celery SES tasks + HTML templates
│   └── main.py
├── scripts/
│   ├── ingest_policies.py           # CLI: ingest policy docs into a hospital's index
│   ├── evaluate.py                  # deterministic + RAGAS eval runner
│   └── verify_live.py               # end-to-end live smoke (LM Studio + Pinecone)
├── tests/                           # 138 passing tests (PostgreSQL-backed; AI tests offline)
├── alembic/versions/                # 0001 SES email features · 0002 AI audit actions
├── data/policies/                   # policy corpus, per-hospital subdirectories
├── .env.example                     # all env vars documented
├── pytest.ini
├── docker-compose.yml               # api · db · redis · celery worker · celery beat
└── requirements.txt
```

---

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

### Required for email features

```env
# AWS SES — the IAM user needs ses:SendEmail on the verified sender domain
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AWS_SES_REGION=us-east-1
SES_SENDER_EMAIL=noreply@yourdomain.com

# Admin receives fraud / lockout alert emails
ADMIN_EMAIL=admin@yourdomain.com

# Used to build clickable links in verification and reset emails
FRONTEND_URL=http://localhost:3000
```

### Full reference

```env
# ── Project ───────────────────────────────────────────────
PROJECT_NAME=HealthPA
VERSION=0.1.0
DEBUG=True

# ── Security ──────────────────────────────────────────────
SECRET_KEY=change-this-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# ── Database ──────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/healthpa
TEST_DATABASE_URL=
TEST_DATABASE_SCHEMA=healthpa_test

# ── Redis ─────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0

# ── AWS SES ───────────────────────────────────────────────
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_SES_REGION=us-east-1
SES_SENDER_EMAIL=
ADMIN_EMAIL=
FAILED_LOGIN_MAX_ATTEMPTS=5
FRONTEND_URL=http://localhost:3000

# ── AI layer (grounded coding / RAG / HITL) ───────────────
AI_ENABLED=True
CHAT_LLM_PROVIDER=openai                     # openai | lmstudio | groq | anthropic
CHAT_LLM_MODEL=google/gemma-4-12b-qat
LLM_BASE_URL=http://localhost:1234/v1        # LM Studio; "" for cloud
GROQ_API_KEY=
EMBEDDING_PROVIDER=openai                     # openai | lmstudio | local (offline hashing)
EMBEDDING_MODEL=text-embedding-nomic-embed-text-v1.5
EMBEDDING_DIM=768
RAG_VECTOR_BACKEND=pinecone                   # pinecone | memory (tests/offline)
PINECONE_API_KEY=
PINECONE_INDEX=healthpa-ai
HITL_CHECKPOINTER=postgres                     # postgres (durable) | memory
ENABLE_WEB_SEARCH=True
TAVILY_API_KEY=
LANGSMITH_TRACING=False
LANGSMITH_API_KEY=

# ── Webhooks ──────────────────────────────────────────────
WEBHOOK_URLS=
```

> **Note:** See `.env.example` for the complete, commented reference. If `AWS_ACCESS_KEY_ID` is empty, email tasks log a warning and skip sending — safe for local development without SES credentials. If the AI provider/Pinecone aren't configured, the AI layer degrades gracefully (rule-based fallback) and the test suite still runs fully offline.

---

## Local Development

### Prerequisites

- Python 3.11+
- PostgreSQL 15
- Redis 7
- Tesseract OCR

### Install

```bash
pip install -r requirements.txt
```

### Database

```bash
python manage_db.py init     # create schema + tables
python manage_db.py seed     # insert sample data
python manage_db.py reset    # drop + recreate
python manage_db.py reset --seed
```

Or run the Alembic migration directly:

```bash
alembic upgrade head
```

### Run locally

```bash
# API server
uvicorn app.main:app --reload

# Celery worker (OCR, AI, email tasks)
celery -A app.core.celery_app worker --loglevel=info

# Celery Beat (appointment reminders — runs every hour)
celery -A app.core.celery_app beat --loglevel=info
```

---

## Docker

```bash
docker compose up --build
```

Services started:

| Container | Port | Role |
|---|---|---|
| `healthpa-api` | 8000 | FastAPI application |
| `healthpa-db` | 5432 | PostgreSQL 15 |
| `healthpa-redis` | 6379 | Redis 7 |
| `healthpa-celery` | — | Celery worker |
| `healthpa-celery-beat` | — | Celery Beat scheduler |

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## API Reference

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/login` | Obtain JWT token |
| `POST` | `/api/auth/register` | Register staff user (sends verification email) |
| `GET` | `/api/auth/verify-email?token=` | Verify email address |
| `POST` | `/api/auth/resend-verification` | Re-send verification email |
| `POST` | `/api/auth/forgot-password` | Request password reset link |
| `POST` | `/api/auth/reset-password` | Complete password reset |

### Appointments

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/appointments/` | List appointments (paginated, filterable by status) |
| `POST` | `/api/appointments/` | Create appointment |
| `GET` | `/api/appointments/{id}` | Get appointment |
| `PATCH` | `/api/appointments/{id}` | Update appointment |
| `DELETE` | `/api/appointments/{id}` | Delete appointment |

### Patients

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/patients/` | List patients |
| `POST` | `/api/patients/` | Create patient |
| `GET` | `/api/patients/{id}` | Get patient |
| `PATCH` | `/api/patients/{id}` | Update patient |
| `DELETE` | `/api/patients/{id}` | Delete patient |

### Prior Authorization

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/pa-requests/` | List PA requests |
| `POST` | `/api/pa-requests/` | Create PA request |
| `GET` | `/api/pa-requests/{id}` | Get PA request |
| `PATCH` | `/api/pa-requests/{id}/status` | Advance FSM status |
| `POST` | `/api/pa-requests/{id}/upload` | Upload clinical document (queues OCR) |

### Other

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/hospitals/` | List hospitals (admin only) |
| `POST` | `/api/batch/patients/csv` | Bulk import patients |
| `POST` | `/api/batch/pa-requests/csv` | Bulk import PA requests |
| `GET` | `/api/analytics/pa-summary` | PA metrics |
| `GET` | `/api/analytics/trends` | Daily trends |
| `GET` | `/health` | Health check |

---

## Email Features

### How it works

All email sending is **non-blocking** — the API enqueues a Celery task and returns immediately. SES is never in the critical path.

```
POST /api/auth/register
    └─▶ create user in DB
    └─▶ send_verification_email.delay(email, name, token)   ← returns instantly
        └─▶ [Celery worker] send_email.delay(...)
            └─▶ [Celery worker] boto3 SES API call
```

### Task inventory (`app/tasks/email.py`)

| Task | Trigger | Recipient |
|---|---|---|
| `send_verification_email` | User registration | New user |
| `send_password_reset_email` | Forgot-password request | User |
| `send_appointment_reminder` | Beat task (hourly) | Patient |
| `send_fraud_alert` | Account lockout | `ADMIN_EMAIL` |
| `send_email` | Called by all above | Configurable |
| `send_appointment_reminders` | Celery Beat (`:00` every hour) | — (orchestrates per-patient sends) |

### Appointment reminder logic

The Beat task runs at the top of every hour. It queries appointments where:
- `scheduled_at` is between **23h55m and 24h05m** from now
- `status = scheduled`
- `reminder_sent = false`

Matching patients with an email address receive a reminder. `reminder_sent` is set to `true` atomically to prevent duplicates.

### Fraud detection

Failed login attempts are tracked on the `User` record. After `FAILED_LOGIN_MAX_ATTEMPTS` (default: 5) consecutive failures:

1. Account is locked for 30 minutes (`locked_until` timestamp set)
2. `send_fraud_alert.delay(...)` fires — admin receives an email with the user email, failure count, source IP, and lock expiry
3. Successful login after lock expiry resets the counter

---

## AI: Grounded Coding, Human Review & Eval

The AI layer turns raw clinical notes into **policy-grounded** ICD-10/CPT codes that a
human signs off on before they're finalized. It never invents codes: every emitted code
must appear in retrieved payer/coding policy and carry a citation, or it is dropped.

### How it works

1. **Ingestion (RAG)** — payer/coding-policy docs (PDF/txt) are chunked, embedded, and
   upserted into a **Pinecone** namespace per `hospital_id` (hard tenant isolation).
   Ingestion is idempotent (stable chunk ids) and fingerprint-cached (no re-embed when
   the corpus is unchanged).
2. **Adaptive retrieval** — retrieve → **grade** relevance (LCEL structured output) →
   if weak, **rewrite** the query and retry → **rerank** (lexical default, optional LLM).
3. **Grounded extraction** — an LLM proposes codes *from the retrieved policy only*,
   with citations; ungrounded codes are dropped. If the LLM/policy is unavailable, a
   deterministic rule-based backstop runs (flagged, for review) so the flow never blocks.
4. **HITL review (LangGraph)** — after extraction the graph `interrupt()`s and pauses
   with the proposed codes; a reviewer resumes via `Command(resume=...)` to
   **approve / reject / edit**. State is persisted by a Postgres checkpointer keyed by
   the PA case id, so a paused review survives a restart.
5. **Agents** — a supervisor routes free-text requests (extract / review / policy-QA);
   the policy-QA path is a ReAct agent with `search_policies` + optional Tavily web
   search (web results are non-authoritative and never assign codes).
6. **Long-term memory** — per-coder/per-hospital corrections are stored and recalled so
   the system learns recurring edits.
7. **Guardrails** — input guard (prompt-injection, length, soft PHI flag) and output
   guard (every code grounded + cited).

### Providers (provider abstraction)

Configured via `.env` — defaults to a local **LM Studio** server (OpenAI-compatible):

- Chat: `CHAT_LLM_PROVIDER=openai`, `CHAT_LLM_MODEL=google/gemma-4-12b-qat`,
  `LLM_BASE_URL=http://localhost:1234/v1` (switch to `groq`/`anthropic` via env)
- Embeddings: `EMBEDDING_PROVIDER=openai`, `text-embedding-nomic-embed-text-v1.5` (768-dim);
  set `EMBEDDING_PROVIDER=local` for offline deterministic hashing embeddings
- Vectors: Pinecone (`PINECONE_API_KEY`, `PINECONE_INDEX`, dim 768/cosine)
- Observability: optional LangSmith (`LANGSMITH_TRACING=true`)

### Endpoints (JWT + `hospital_id` scoped)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/pa/{id}/extract` | RAG + rerank + grounded extraction; pauses for review |
| GET | `/api/v1/pa/{id}/proposed-codes` | Proposed codes + citations (from the paused checkpoint) |
| POST | `/api/v1/pa/{id}/review` | `{decision: approve\|reject\|edit, edited_codes?}` → resume + finalize |
| POST | `/api/v1/pa/{id}/ask` | Coder policy-QA (ReAct/RAG, web search optional) |
| POST | `/api/v1/policies/reindex` | Rebuild the hospital's persistent index (`{force?}`; cached otherwise) |

Audit events `ai_codes_proposed` and `codes_reviewed` (who / when / decision / before→after)
are written to `audit_logs`.

### Ingest policy docs

```bash
python -m scripts.ingest_policies --hospital <HOSPITAL_UUID> \
    --dir data/policies/<HOSPITAL_UUID> --payer Aetna --code-system ICD10
```

### Evaluation (RAGAS + deterministic)

`scripts/evaluate.py` scores a labelled dataset (`app/eval/cases.json`):

- **Deterministic** (offline, no LLM): code precision / recall / F1 vs gold, retrieval recall@k
- **RAGAS** (needs a chat model): faithfulness, answer relevancy, context precision, context recall
- **LLM-as-judge**: citation faithfulness

```bash
python -m scripts.evaluate              # deterministic only (offline)
python -m scripts.evaluate --use-llm    # use the chat model for extraction
python -m scripts.evaluate --ragas      # add RAGAS metrics (LM Studio/Groq must be reachable)
python -m scripts.evaluate --judge      # add LLM-as-judge
```

> Grounded extraction and RAGAS require a reachable chat model (LM Studio running, or a
> Groq key). The full **test suite is fully offline** — fake LLMs, hashing embeddings, an
> in-memory vector backend, and an in-memory checkpointer — and needs neither LM Studio
> nor Pinecone.

---

## Testing

The test suite uses a real PostgreSQL database in an isolated `healthpa_test` schema. No mocking of the database layer.

```bash
# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=app --cov-report=html
```

```
138 passed in ~70s
```

The AI tests are fully offline (fake LLMs, hashing embeddings, in-memory vector store + checkpointer) — no LM Studio or Pinecone required.

### Test layout

| File | Coverage |
|---|---|
| `test_auth.py` | Login, register, JWT validation |
| `test_email_auth.py` | Email verification, password reset, fraud detection, appointments |
| `test_hospitals.py` | Hospital CRUD, admin restriction |
| `test_patients.py` | Patient CRUD, hospital isolation |
| `test_pa_requests.py` | PA workflow, FSM transitions, cross-hospital isolation |
| `test_ai_provider.py` | Provider abstraction, embeddings, vector-store tenant isolation |
| `test_ai_rag.py` | Ingestion, fingerprint cache, retrieval, filters, rerank, grade/rewrite |
| `test_ai_extraction.py` | Grounded extraction, grounding filter, auto-citation, fallback |
| `test_ai_guardrails.py` | Input guard, code grounding, output guard |
| `test_ai_hitl.py` | Interrupt/resume (approve/reject/edit), rewrite loop, tenant fallback |
| `test_ai_agents.py` | Supervisor routing, ReAct agent, long-term memory |
| `test_ai_api.py` | AI endpoints, audit, API-level tenant isolation |
| `test_ai_eval.py` | Deterministic evaluators + harness |
| `test_ai_ragas.py` | RAGAS sample construction + offline skip path |

---

## Security Notes

- Hospital isolation enforced at the dependency layer — every query is scoped by `hospital_id` from the JWT claim
- JWT tokens include `hospital_id` and `role`; mismatched claims are rejected
- Passwords hashed with bcrypt (passlib)
- Password reset and email verification tokens are URL-safe 32-byte random values with configurable TTLs
- Forgot-password and resend-verification endpoints always return `200` to prevent email enumeration
- Rate limiting: 10 req/60s on auth endpoints, 100 req/60s elsewhere
- PA status transitions validated through explicit FSM rules; invalid transitions return `400`
- All data mutations logged to `audit_logs` (HIPAA audit trail)

---

## Test Data

After seeding:

| Email | Password | Role |
|---|---|---|
| `dr.smith@mgh.org` | `password123` | Doctor |
| `nurse.johnson@mgh.org` | `password123` | Nurse |
| `admin@mgh.org` | `admin123` | Admin |

---

## License

Proprietary. Intended for professional clinical workflow environments.
