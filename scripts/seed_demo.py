"""Seed a self-contained, fully working demo into the app database.

Creates a demo hospital, a login user, patients, and PA cases whose clinical
notes match the sample policies — then ingests those policies into the demo
hospital's vector namespace. After running, log in and click "Run extraction"
on any case to see real LLM-grounded codes.

    python -m scripts.seed_demo            # create (idempotent)

Login:  demo@healthpa.local  /  demo12345

Prereqs: the app database in DATABASE_URL is reachable, LM Studio is running
(for nomic embeddings during ingestion), and Pinecone is reachable.
"""

import asyncio
import os
import sys
import uuid
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.core.password import get_password_hash  # noqa: E402
from app.models.hospital import Hospital  # noqa: E402
from app.models.patient import Patient  # noqa: E402
from app.models.pa_request import PARequest, PARequestStatus  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.services.rag_service import rag_service  # noqa: E402

# Stable IDs so re-running is idempotent (no duplicates).
HOSPITAL_ID = uuid.UUID("d3000000-0000-4000-8000-000000000001")
USER_ID = uuid.UUID("d3000000-0000-4000-8000-000000000010")
LOGIN_EMAIL = "demo@healthpa.local"
LOGIN_PASSWORD = "demo12345"

# Each case's note matches one policy doc; payer matches the ingested policy tag.
CASES = [
    {
        "pid": "d3000000-0000-4000-8000-000000000101",
        "patient": ("John", "Carter", "DEMO-P001", date(1968, 3, 12)),
        "pa": "d3000000-0000-4000-8000-000000000201",
        "number": "DEMO-2026-001",
        "payer": "Aetna",
        "status": PARequestStatus.PENDING,
        "notes": (
            "Adult patient with productive cough, fever, and right basal crackles on exam. "
            "Assessment: pneumonia, unspecified organism. A two-view chest x-ray was performed "
            "to evaluate for consolidation."
        ),
    },
    {
        "pid": "d3000000-0000-4000-8000-000000000102",
        "patient": ("Maria", "Gomez", "DEMO-P002", date(1975, 7, 22)),
        "pa": "d3000000-0000-4000-8000-000000000202",
        "number": "DEMO-2026-002",
        "payer": "Cigna",
        "status": PARequestStatus.PENDING,
        "notes": (
            "Chronic right knee pain and stiffness; exam and imaging consistent with primary "
            "osteoarthritis. MRI of the right knee without contrast requested after six weeks "
            "of failed conservative therapy."
        ),
    },
    {
        "pid": "d3000000-0000-4000-8000-000000000103",
        "patient": ("Wei", "Zhang", "DEMO-P003", date(1959, 11, 2)),
        "pa": "d3000000-0000-4000-8000-000000000203",
        "number": "DEMO-2026-003",
        "payer": "UnitedHealthcare",
        "status": PARequestStatus.PENDING,
        "notes": (
            "Type 2 diabetes mellitus without complications, routine follow-up. Hemoglobin A1c "
            "laboratory test ordered for glycemic monitoring."
        ),
    },
    {
        "pid": "d3000000-0000-4000-8000-000000000104",
        "patient": ("David", "Lee", "DEMO-P004", date(1982, 5, 18)),
        "pa": "d3000000-0000-4000-8000-000000000204",
        "number": "DEMO-2026-004",
        "payer": "UnitedHealthcare",
        "status": PARequestStatus.PENDING,
        "notes": (
            "Patient with chronic low back pain. Physical therapy evaluation and treatment "
            "requested. Conservative management has failed."
        ),
    },
    {
        "pid": "d3000000-0000-4000-8000-000000000105",
        "patient": ("Sarah", "Patel", "DEMO-P005", date(1990, 1, 15)),
        "pa": "d3000000-0000-4000-8000-000000000205",
        "number": "DEMO-2026-005",
        "payer": "Aetna",
        "status": PARequestStatus.PENDING,
        "notes": (
            "Acute bronchitis, unspecified, with persistent cough. Symptomatic management; "
            "a single-view chest x-ray is considered if symptoms persist."
        ),
    },
]

# Policy file -> payer tag (must match the case payer for the retrieval filter).
POLICY_FILES = [
    ("aetna_respiratory.txt", "Aetna"),
    ("cigna_msk.txt", "Cigna"),
    ("uhc_diabetes.txt", "UnitedHealthcare"),
    ("uhc_physical_therapy.txt", "UnitedHealthcare"),
]


async def seed_db():
    async with AsyncSessionLocal() as db:
        if not await db.get(Hospital, HOSPITAL_ID):
            db.add(
                Hospital(
                    id=HOSPITAL_ID,
                    name="HealthPA Demo Clinic",
                    code="DEMO01",
                    address="1 Demo Way",
                    phone="555-0100",
                    email="ops@healthpa.local",
                    is_active=True,
                )
            )

        if not await db.get(User, USER_ID):
            db.add(
                User(
                    id=USER_ID,
                    hospital_id=HOSPITAL_ID,
                    email=LOGIN_EMAIL,
                    hashed_password=get_password_hash(LOGIN_PASSWORD),
                    first_name="Dana",
                    last_name="Reviewer",
                    role=UserRole.REVIEWER,
                    is_active=True,
                    is_verified=True,
                )
            )

        for c in CASES:
            pid = uuid.UUID(c["pid"])
            if not await db.get(Patient, pid):
                fn, ln, mrn, dob = c["patient"]
                db.add(
                    Patient(
                        id=pid,
                        hospital_id=HOSPITAL_ID,
                        mrn=mrn,
                        first_name=fn,
                        last_name=ln,
                        date_of_birth=dob,
                        insurance_provider=c["payer"],
                    )
                )

            pa_id = uuid.UUID(c["pa"])
            if not await db.get(PARequest, pa_id):
                db.add(
                    PARequest(
                        id=pa_id,
                        hospital_id=HOSPITAL_ID,
                        patient_id=pid,
                        created_by_id=USER_ID,
                        request_number=c["number"],
                        diagnosis_codes=[],
                        procedure_codes=[],
                        clinical_notes=c["notes"],
                        payer_name=c["payer"],
                        status=c["status"],
                        is_urgent=False,
                        requested_date=date.today(),
                    )
                )

        await db.commit()
    print(f"DB seeded: hospital={HOSPITAL_ID} user={LOGIN_EMAIL} cases={len(CASES)}")


def ingest_policies():
    sample_dir = os.path.join(os.path.dirname(__file__), "..", "samples", "policies")
    items = [
        {"path": os.path.join(sample_dir, name), "source_doc": name, "payer": payer}
        for name, payer in POLICY_FILES
    ]
    result = rag_service.ingest_paths(str(HOSPITAL_ID), items, force=True)
    print(f"Policies ingested into namespace {HOSPITAL_ID}: {result}")


def main():
    print(f"Seeding demo into {settings.DATABASE_URL.rsplit('@', 1)[-1]} ...")
    asyncio.run(seed_db())
    print("Ingesting policies (needs LM Studio + Pinecone reachable) ...")
    ingest_policies()
    print(
        "\nDone. Log in at the frontend with:\n"
        f"  email:    {LOGIN_EMAIL}\n"
        f"  password: {LOGIN_PASSWORD}\n"
        "Open any case and click 'Run extraction'."
    )


if __name__ == "__main__":
    main()
