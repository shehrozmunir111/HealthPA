# HealthPA

HealthPA is a FastAPI-based prior authorization platform for healthcare workflows. It provides hospital-scoped tenant isolation, structured PA request management, document upload/OCR hooks, analytics endpoints, background processing support, and a PostgreSQL-backed test setup.

## Highlights

- Multi-tenant data isolation using `hospital_id`
- JWT authentication with tenant-aware validation
- Prior authorization workflow with finite-state transition rules
- OCR upload pipeline with lazy dependency loading
- Batch CSV import for patients and PA requests
- Analytics endpoints for PA activity and processing trends
- Redis caching and Celery worker support
- PostgreSQL-backed development and test workflows
- Automated test suite with 50 passing tests

## Tech Stack

| Component | Technology |
|-----------|------------|
| API | FastAPI |
| Language | Python 3.11+ |
| Database | PostgreSQL |
| ORM | SQLAlchemy 2.0 Async |
| Cache | Redis |
| Task Queue | Celery |
| OCR | Tesseract, pdf2image |
| AI Client | OpenAI-compatible client for Groq |
| Containers | Docker, Docker Compose |
| Testing | Pytest, pytest-asyncio, httpx |

## Project Structure

```text
HealthPA/
|-- app/
|   |-- core/         # config, database, security, middleware, cache
|   |-- models/       # SQLAlchemy domain models
|   |-- routes/       # FastAPI route modules
|   |-- schemas/      # Pydantic request/response schemas
|   |-- services/     # OCR, webhooks, audit, AI integrations
|   `-- main.py       # FastAPI application entry point
|-- tests/            # PostgreSQL-backed test suite
|-- alembic/          # Migration scaffolding
|-- assets/           # Project screenshots and assets
|-- data/             # Local OCR/upload storage
|-- manage_db.py      # Unified database management CLI
|-- init_db.py        # Backward-compatible init wrapper
|-- seed_data.py      # Backward-compatible seed wrapper
|-- reset_db.py       # Backward-compatible reset wrapper
`-- README.md
```

## Configuration

Create a `.env` file in the project root:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:admin@localhost:5432/healthPA
TEST_DATABASE_URL=postgresql+asyncpg://postgres:admin@localhost:5432/healthPA_test
TEST_DATABASE_SCHEMA=healthpa_test

# Redis
REDIS_URL=redis://localhost:6379/0

# Security
SECRET_KEY=your-secret-key-here
DEBUG=True

# AI
GROQ_API_KEY=your-groq-api-key

# Webhooks
WEBHOOK_URLS=https://example.com/webhook
```

## Local Development

### Prerequisites

- Python 3.11+
- PostgreSQL
- Redis
- Tesseract OCR for document processing

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Database Commands

Primary workflow:

```bash
python manage_db.py init
python manage_db.py seed
python manage_db.py reset
python manage_db.py reset --seed
python manage_db.py drop
```

Backward-compatible wrappers still work:

```bash
python init_db.py
python seed_data.py
python reset_db.py --seed
```

### Run the API

```bash
uvicorn app.main:app --reload
```

### Run the Celery Worker

```bash
celery -A app.core.celery_app worker --loglevel=info
```

## Docker

```bash
docker-compose up --build
```

Available services:

- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`

## API Surface

HealthPA exposes endpoints across these areas:

- Authentication
- Hospitals
- Patients
- PA requests
- Batch operations
- Analytics
- Infrastructure health checks

### Key Routes

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/auth/login` | Authenticate a user |
| POST | `/api/auth/register` | Register a user |
| GET | `/api/patients/` | List patients for the current tenant |
| POST | `/api/patients/` | Create a patient |
| GET | `/api/pa-requests/` | List PA requests |
| POST | `/api/pa-requests/` | Create a PA request |
| PATCH | `/api/pa-requests/{id}/status` | Advance PA workflow status |
| POST | `/api/pa-requests/{id}/upload` | Upload a clinical document |
| POST | `/api/batch/patients/csv` | Import patients from CSV |
| POST | `/api/batch/pa-requests/csv` | Import PA requests from CSV |
| GET | `/api/analytics/pa-summary` | PA summary metrics |
| GET | `/health` | Health check |

## API Documentation Screenshot

A sample Swagger UI view of the available API routes:

![API Endpoints](assets/endpoints.png)

## Test Data

After seeding the database, these sample users are available:

| Email | Password | Role |
|-------|----------|------|
| `dr.smith@mgh.org` | `password123` | Doctor |
| `nurse.johnson@mgh.org` | `password123` | Nurse |
| `admin@mgh.org` | `admin123` | Admin |

## Testing

The automated test suite runs against PostgreSQL.

```bash
pytest tests/ -v
pytest tests/ --cov=app --cov-report=html
```

Current status:

- 50 tests passing

## Security Notes

- Hospital isolation is enforced through authenticated tenant context
- Hospital management routes are admin-restricted
- JWT validation includes tenant claim checks
- Rate limiting is enabled for auth and general API traffic
- Input sanitization is applied to user-controlled fields
- PA status changes are validated through explicit FSM rules

## License

Proprietary. Intended for professional clinical workflow environments.
