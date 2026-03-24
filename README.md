# HealthPA - AI-Powered Prior Authorization System

**HealthPA** is a multi-tenant clinical workflow engine designed to automate the **Prior Authorization (PA)** process for healthcare facilities. It uses a combination of OCR, NLP, and Finite State Machines (FSM) to streamline medical insurance approval requests.

---

## 🚀 Key Features

-   **Multi-Tenancy Isolation**: Strict `hospital_id` based data separation for HIPAA compliance.
-   **AI Extraction Engine**: Clinical code (ICD-10/CPT) extraction using OpenRouter-based LLMs.
-   **Background OCR**: Asynchronous image processing for clinical documents using Celery & Tesseract.
-   **Clinical FSM**: Advanced workflow management for PA status transitions (Draft -> Review -> Approved).
-   **Professional Observability**: Structured logging, request-ID tracing, and process-time monitoring.
-   **Audit Trail**: Deep HIPAA-ready event logging for every clinical action.

---

## 🏗️ Technical Architecture

### Tech Stack
-   **Backend**: FastAPI (Python 3.11+)
-   **Database**: PostgreSQL (SQLAlchemy 2.0 Async)
-   **Caching/Broker**: Redis
-   **Task Queue**: Celery (Background workers)
-   **AI Engine**: OpenRouter (Claude-3-Sonnet)
-   **OCR**: Tesseract OCR
-   **Infrastructure**: Docker & Docker Compose

### Folder Structure
```text
/HealthPA
├── app/
│   ├── api/v1/         # Professional Versioned API
│   ├── core/           # Security, Auth, Logging, Dependencies
│   ├── models/         # SQLAlchemy 2.0 Base Models
│   ├── schemas/        # Pydantic v2 Contract Layers
│   ├── services/       # Clinical Logic (OCR, AI, Audit)
│   └── main.py         # App Entry Point
├── alembic/            # DB Migration Management
├── data/               # Local clinical storage (Ignored via .gitignore)
├── logs/               # Structured application logs
├── tests/              # Pytest suite
└── docker-compose.yml  # Local stack orchestration
```

---

## 🛠️ Setup & Installation

### 1. Requirements
Ensure you have the following installed:
-   Docker & Docker Compose
-   Python 3.11 (for local development)
-   Tesseract-OCR (if running without Docker)

### 2. Configuration
Create a `.env` file in the root directory:
```bash
OPENROUTER_API_KEY=sk-or-v1-...
SECRET_KEY=yoursecretkeyhere
DEBUG=True
```

### 3. Running with Docker (Recommended)
```bash
# Start the entire stack (API, DB, Redis, Celery)
docker-compose up --build
```
The API will be available at [http://localhost:8000/docs](http://localhost:8000/docs).

### 4. Database Migrations
```bash
# Apply migrations to local DB
alembic upgrade head
```

---

## 🔒 Security & HIPAA Compliance
-   **Tenant Isolation**: Every database table is filtered by `hospital_id` via a custom FastAPI dependency.
-   **RBAC**: Role-based access control (Doctor, Nurse, Admin, Reviewer).
-   **Audit Logs**: All clinical data reads are logged with User-Email and Request-ID.

---

## 📝 License
Proprietary - Developed for Professional Clinical Environments.
