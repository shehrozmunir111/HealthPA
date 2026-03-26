# HealthPA - AI-Powered Prior Authorization System

**HealthPA** is a multi-tenant clinical workflow engine designed to automate the **Prior Authorization (PA)** process for healthcare facilities. It uses AI for clinical code extraction, OCR for document processing, and Finite State Machines for workflow management.

---

## Key Features

- **Multi-Tenancy Isolation**: Strict `hospital_id` based data separation for HIPAA compliance
- **AI Extraction Engine**: Clinical code (ICD-10/CPT) extraction using Groq API (Llama 3.1)
- **PDF & Image OCR**: Async document processing with pdf2image and Tesseract
- **Webhook Notifications**: Real-time status change notifications to external systems
- **FSM Workflow**: Advanced PA status transitions (Draft → Pending → Approved/Denied)
- **Rate Limiting**: Built-in abuse prevention
- **Redis Caching**: Smart caching for frequently accessed data
- **Batch Processing**: CSV bulk import for PA requests and patients
- **Analytics Dashboard**: Reporting endpoints for PA metrics and trends
- **Audit Trail**: HIPAA-ready event logging
- **Comprehensive Testing**: 48 unit tests covering all endpoints

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI (Python 3.11+) |
| Database | PostgreSQL (SQLAlchemy 2.0 Async) |
| Caching | Redis |
| Task Queue | Celery |
| AI Engine | Groq API (Llama 3.1) |
| OCR | Tesseract + pdf2image |
| Infrastructure | Docker & Docker Compose |

---

## Project Structure

```
HealthPA/
├── app/
│   ├── core/          # config, database, security, middleware, cache, sanitization
│   ├── models/        # SQLAlchemy models (Hospital, User, Patient, PARequest, AuditLog)
│   ├── schemas/       # Pydantic schemas for validation
│   ├── services/      # ai_engine, ocr_service, webhook_service, audit_service
│   ├── routes/        # API endpoints (auth, hospitals, patients, pa_requests, batch, analytics)
│   └── main.py        # FastAPI application entry point
├── tests/             # Pytest test suite (48 tests)
├── alembic/           # Database migrations
├── assets/            # Screenshots and images
├── data/              # Local file storage (gitignored)
├── .env               # Environment variables (gitignored)
├── requirements.txt    # Python dependencies
├── docker-compose.yml  # Docker orchestration
├── Dockerfile         # Container configuration
└── README.md
```

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- PostgreSQL
- Redis
- Python 3.11+ (for local development)
- Tesseract-OCR (for OCR functionality)

### Configuration

Create a `.env` file:
```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:admin@localhost:5432/healthPA
TEST_DATABASE_URL=postgresql+asyncpg://postgres:admin@localhost:5432/healthPA_test

# Redis
REDIS_URL=redis://localhost:6379/0

# Security
SECRET_KEY=your-secret-key-here
DEBUG=True

# AI (Groq)
GROQ_API_KEY=your-groq-api-key

# Webhooks (comma-separated URLs)
WEBHOOK_URLS=https://example.com/webhook
```

### Running with Docker

```bash
# Start all services (API, DB, Redis, Celery)
docker-compose up --build

# API available at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

### Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Unified database CLI
python manage_db.py init
python manage_db.py seed
python manage_db.py reset
python manage_db.py reset --seed
python manage_db.py drop

# Backward-compatible shortcuts still work
python init_db.py
python seed_data.py
python reset_db.py --seed

# Start API server
uvicorn app.main:app --reload

# Start Celery worker (separate terminal)
celery -A app.core.celery_app worker --loglevel=info
```

---

## API Endpoints

**23 endpoints** covering Authentication, Hospitals, Patients, PA Workflow, Batch Operations, and Analytics.

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/login` | User login |
| POST | `/api/auth/register` | User registration |

### Hospitals
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/hospitals/` | List hospitals |
| POST | `/api/hospitals/` | Create hospital |
| GET | `/api/hospitals/{id}` | Get hospital |
| PATCH | `/api/hospitals/{id}` | Update hospital |

### Patients
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/patients/` | List patients |
| POST | `/api/patients/` | Create patient |
| GET | `/api/patients/{id}` | Get patient |
| PATCH | `/api/patients/{id}` | Update patient |
| DELETE | `/api/patients/{id}` | Delete patient |

### PA Workflow
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/pa-requests/` | List PA requests |
| POST | `/api/pa-requests/` | Create PA request |
| GET | `/api/pa-requests/{id}` | Get PA request |
| PATCH | `/api/pa-requests/{id}/status` | Update PA status |
| POST | `/api/pa-requests/{id}/upload` | Upload document |

### Batch Operations
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/batch/pa-requests/csv` | Bulk import PA requests |
| POST | `/api/batch/patients/csv` | Bulk import patients |

### Analytics
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/analytics/pa-summary` | PA statistics |
| GET | `/api/analytics/processing-time` | Processing time metrics |
| GET | `/api/analytics/payer-breakdown` | Payer statistics |
| GET | `/api/analytics/trends` | Daily trends |
| GET | `/api/analytics/patient-stats` | Patient statistics |

### Infrastructure
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |

---

## API Documentation Screenshot

![API Endpoints](assets/endpoints.png)

---

## Test Credentials

After seeding the database:

| Email | Password | Role |
|-------|----------|------|
| `dr.smith@mgh.org` | `password123` | Doctor |
| `nurse.johnson@mgh.org` | `password123` | Nurse |
| `admin@mgh.org` | `admin123` | Admin |

---

## Security

- **Tenant Isolation**: All data filtered by `hospital_id`
- **RBAC**: Role-based access control (Doctor, Nurse, Admin, Reviewer)
- **Rate Limiting**: 100 req/min default, 10 req/min for auth
- **Input Sanitization**: XSS/injection prevention
- **FSM Validation**: Invalid state transitions rejected

---

## Running Tests

```bash
# Run all tests against PostgreSQL test database
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html
```

---

## License

Proprietary - Developed for Professional Clinical Environments.
