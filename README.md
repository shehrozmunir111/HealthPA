# HealthPA

HealthPA is a production-ready, multi-tenant healthcare SaaS built on FastAPI. It provides hospital-scoped data isolation, a full prior-authorization workflow, asynchronous email notifications via AWS SES, appointment scheduling with automated reminders, fraud detection, and a PostgreSQL-backed test suite with 80 passing tests.

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
| AI | Groq (Llama 3.1) |
| Containers | Docker + Docker Compose |
| Testing | pytest, pytest-asyncio, httpx |

---

## Project Structure

```
HealthPA/
├── app/
│   ├── core/               # config, database, security, middleware, cache
│   ├── models/             # SQLAlchemy domain models
│   │   ├── hospital.py
│   │   ├── user.py         # + verification/reset/lockout fields
│   │   ├── patient.py
│   │   ├── pa_request.py
│   │   ├── appointment.py  # NEW
│   │   └── audit_log.py
│   ├── routes/
│   │   ├── auth.py         # + verify-email, forgot/reset-password, lockout
│   │   ├── appointments.py # NEW
│   │   ├── hospitals.py
│   │   ├── patients.py
│   │   ├── pa_requests.py
│   │   ├── batch.py
│   │   └── analytics.py
│   ├── schemas/
│   ├── services/           # OCR, webhooks, audit, AI
│   ├── tasks/
│   │   └── email.py        # NEW — Celery SES tasks + HTML templates
│   └── main.py
├── tests/                  # 80 passing tests (PostgreSQL-backed)
├── alembic/
│   └── versions/
│       └── 0001_add_ses_email_features.py   # NEW
├── data/
├── .env.example            # NEW — all env vars documented
├── pytest.ini              # NEW
├── docker-compose.yml      # + celery_beat service
├── manage_db.py
└── requirements.txt        # + boto3
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
DATABASE_URL=postgresql+asyncpg://postgres:admin@localhost:5432/healthpa
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

# ── AI / Groq ─────────────────────────────────────────────
GROQ_API_KEY=

# ── Webhooks ──────────────────────────────────────────────
WEBHOOK_URLS=
```

> **Note:** If `AWS_ACCESS_KEY_ID` is empty, email tasks log a warning and skip sending — safe for local development without SES credentials.

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

## Testing

The test suite uses a real PostgreSQL database in an isolated `healthpa_test` schema. No mocking of the database layer.

```bash
# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=app --cov-report=html
```

```
80 passed in ~32s
```

### Test layout

| File | Coverage |
|---|---|
| `test_auth.py` | Login, register, JWT validation |
| `test_email_auth.py` | Email verification, password reset, fraud detection, appointments |
| `test_hospitals.py` | Hospital CRUD, admin restriction |
| `test_patients.py` | Patient CRUD, hospital isolation |
| `test_pa_requests.py` | PA workflow, FSM transitions, cross-hospital isolation |

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
