import argparse
import asyncio
from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal, Base, engine
from app.core.password import get_password_hash
from app.models.audit_log import AuditLog
from app.models.hospital import Hospital
from app.models.pa_request import PARequest, PARequestStatus
from app.models.patient import Patient
from app.models.user import User


async def init_database() -> None:
    """Create all database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print(f"Database tables created successfully for: {settings.DATABASE_URL}")


async def seed_database() -> None:
    """Populate PostgreSQL with sample development data."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Hospital))
        if result.scalars().first():
            print("Database already seeded. Skipping...")
            return

        print("Seeding database...")

        hospitals = [
            Hospital(
                id=uuid4(),
                name="Memorial General Hospital",
                code="MGH001",
                address="123 Medical Center Dr, Boston, MA 02101",
                phone="(617) 555-0100",
                email="admin@mgh.org",
                is_active=True,
            ),
            Hospital(
                id=uuid4(),
                name="St. Mary's Medical Center",
                code="SMC002",
                address="456 Healthcare Ave, New York, NY 10001",
                phone="(212) 555-0200",
                email="admin@stmarys.org",
                is_active=True,
            ),
            Hospital(
                id=uuid4(),
                name="Regional Health System",
                code="RHS003",
                address="789 Wellness Blvd, Chicago, IL 60601",
                phone="(312) 555-0300",
                email="admin@rhs.org",
                is_active=True,
            ),
        ]
        session.add_all(hospitals)
        await session.flush()

        users = [
            User(
                id=uuid4(),
                hospital_id=hospitals[0].id,
                email="dr.smith@mgh.org",
                hashed_password=get_password_hash("password123"),
                first_name="John",
                last_name="Smith",
                role="doctor",
                is_active=True,
            ),
            User(
                id=uuid4(),
                hospital_id=hospitals[0].id,
                email="nurse.johnson@mgh.org",
                hashed_password=get_password_hash("password123"),
                first_name="Sarah",
                last_name="Johnson",
                role="nurse",
                is_active=True,
            ),
            User(
                id=uuid4(),
                hospital_id=hospitals[0].id,
                email="admin@mgh.org",
                hashed_password=get_password_hash("admin123"),
                first_name="Michael",
                last_name="Brown",
                role="admin",
                is_active=True,
            ),
            User(
                id=uuid4(),
                hospital_id=hospitals[1].id,
                email="dr.chen@stmarys.org",
                hashed_password=get_password_hash("password123"),
                first_name="Emily",
                last_name="Chen",
                role="doctor",
                is_active=True,
            ),
            User(
                id=uuid4(),
                hospital_id=hospitals[1].id,
                email="reviewer@stmarys.org",
                hashed_password=get_password_hash("password123"),
                first_name="Robert",
                last_name="Williams",
                role="reviewer",
                is_active=True,
            ),
        ]
        session.add_all(users)
        await session.flush()

        patients = [
            Patient(
                id=uuid4(),
                hospital_id=hospitals[0].id,
                mrn="MRN001",
                first_name="James",
                last_name="Wilson",
                date_of_birth=date(1985, 3, 15),
                phone="(617) 555-1001",
                email="james.wilson@email.com",
                address="101 Oak Street, Boston, MA 02102",
                insurance_provider="Blue Cross Blue Shield",
                insurance_policy_number="BCBS-123456789",
                insurance_group_number="GRP-001",
            ),
            Patient(
                id=uuid4(),
                hospital_id=hospitals[0].id,
                mrn="MRN002",
                first_name="Maria",
                last_name="Garcia",
                date_of_birth=date(1992, 7, 22),
                phone="(617) 555-1002",
                email="maria.garcia@email.com",
                address="202 Pine Avenue, Cambridge, MA 02139",
                insurance_provider="Aetna",
                insurance_policy_number="AET-987654321",
                insurance_group_number="GRP-002",
            ),
            Patient(
                id=uuid4(),
                hospital_id=hospitals[0].id,
                mrn="MRN003",
                first_name="David",
                last_name="Lee",
                date_of_birth=date(1978, 11, 8),
                phone="(617) 555-1003",
                email="david.lee@email.com",
                address="303 Maple Road, Somerville, MA 02143",
                insurance_provider="United Healthcare",
                insurance_policy_number="UHC-456789123",
                insurance_group_number="GRP-003",
            ),
            Patient(
                id=uuid4(),
                hospital_id=hospitals[1].id,
                mrn="SMC-MRN001",
                first_name="Jennifer",
                last_name="Taylor",
                date_of_birth=date(1990, 5, 30),
                phone="(212) 555-2001",
                email="jennifer.taylor@email.com",
                address="404 Fifth Avenue, New York, NY 10018",
                insurance_provider="Cigna",
                insurance_policy_number="CIG-111222333",
                insurance_group_number="GRP-SMC-001",
            ),
            Patient(
                id=uuid4(),
                hospital_id=hospitals[1].id,
                mrn="SMC-MRN002",
                first_name="Michael",
                last_name="Anderson",
                date_of_birth=date(1965, 9, 12),
                phone="(212) 555-2002",
                email="michael.anderson@email.com",
                address="505 Broadway, New York, NY 10012",
                insurance_provider="Medicare",
                insurance_policy_number="MCR-444555666",
                insurance_group_number="N/A",
            ),
        ]
        session.add_all(patients)
        await session.flush()

        now = datetime.now(timezone.utc)
        today = date.today()
        pa_requests = [
            PARequest(
                id=uuid4(),
                hospital_id=hospitals[0].id,
                patient_id=patients[0].id,
                created_by_id=users[0].id,
                request_number="PA-2024-001",
                diagnosis_codes=["J44.0", "R05.9"],
                procedure_codes=["99215"],
                clinical_notes="Patient presents with severe COPD exacerbation requiring oxygen therapy and nebulizer treatments. Patient has history of 3+ hospitalizations in past year for respiratory issues.",
                status=PARequestStatus.PENDING,
                requested_date=today,
                payer_name="Blue Cross Blue Shield",
                payer_id="BCBS-123456789",
                status_history=[
                    {"status": "draft", "timestamp": now.isoformat(), "user": "dr.smith@mgh.org"},
                    {"status": "pending", "timestamp": now.isoformat(), "user": "dr.smith@mgh.org"},
                ],
            ),
            PARequest(
                id=uuid4(),
                hospital_id=hospitals[0].id,
                patient_id=patients[1].id,
                created_by_id=users[1].id,
                request_number="PA-2024-002",
                diagnosis_codes=["E11.9"],
                procedure_codes=["83036", "80053"],
                clinical_notes="Routine diabetes management. Patient requires HbA1c testing and metabolic panel to assess glycemic control.",
                status=PARequestStatus.DRAFT,
                requested_date=today,
                payer_name="Aetna",
                payer_id="AET-987654321",
                status_history=[
                    {"status": "draft", "timestamp": now.isoformat(), "user": "nurse.johnson@mgh.org"},
                ],
            ),
            PARequest(
                id=uuid4(),
                hospital_id=hospitals[0].id,
                patient_id=patients[2].id,
                created_by_id=users[0].id,
                request_number="PA-2024-003",
                diagnosis_codes=["M54.5", "M79.3"],
                procedure_codes=["97140", "99214"],
                clinical_notes="Patient with chronic low back pain. Physical therapy evaluation and treatment requested. Conservative management has failed.",
                status=PARequestStatus.APPROVED,
                requested_date=today,
                payer_name="United Healthcare",
                payer_id="UHC-456789123",
                decision_notes="Approved for 12 sessions of physical therapy.",
                decision_date=now,
                decision_by=users[0].email,
                status_history=[
                    {"status": "draft", "timestamp": now.isoformat(), "user": "dr.smith@mgh.org"},
                    {"status": "pending", "timestamp": now.isoformat(), "user": "dr.smith@mgh.org"},
                    {"status": "approved", "timestamp": now.isoformat(), "user": "dr.smith@mgh.org"},
                ],
            ),
            PARequest(
                id=uuid4(),
                hospital_id=hospitals[1].id,
                patient_id=patients[3].id,
                created_by_id=users[3].id,
                request_number="PA-2024-SMC-001",
                diagnosis_codes=["I10", "E78.5"],
                procedure_codes=["99213", "80061"],
                clinical_notes="Hypertension and hyperlipidemia management. Patient requires routine monitoring and lab work.",
                status=PARequestStatus.PENDING,
                requested_date=today,
                payer_name="Cigna",
                payer_id="CIG-111222333",
                status_history=[
                    {"status": "draft", "timestamp": now.isoformat(), "user": "dr.chen@stmarys.org"},
                    {"status": "pending", "timestamp": now.isoformat(), "user": "dr.chen@stmarys.org"},
                ],
            ),
            PARequest(
                id=uuid4(),
                hospital_id=hospitals[1].id,
                patient_id=patients[4].id,
                created_by_id=users[3].id,
                request_number="PA-2024-SMC-002",
                diagnosis_codes=["J44.1"],
                procedure_codes=["94010", "94640"],
                clinical_notes="COPD patient with acute exacerbation. Requires pulmonary function testing and nebulizer treatments.",
                status=PARequestStatus.DENIED,
                requested_date=today,
                payer_name="Medicare",
                payer_id="MCR-444555666",
                decision_notes="Prior authorization not required for Medicare patients. Services can proceed.",
                decision_date=now,
                decision_by=users[4].email,
                status_history=[
                    {"status": "draft", "timestamp": now.isoformat(), "user": "dr.chen@stmarys.org"},
                    {"status": "pending", "timestamp": now.isoformat(), "user": "dr.chen@stmarys.org"},
                    {"status": "denied", "timestamp": now.isoformat(), "user": "reviewer@stmarys.org"},
                ],
            ),
        ]
        session.add_all(pa_requests)

        await session.commit()
        print("Database seeded successfully!")
        print(f"  - {len(hospitals)} hospitals")
        print(f"  - {len(users)} users")
        print(f"  - {len(patients)} patients")
        print(f"  - {len(pa_requests)} PA requests")


async def reset_database(seed: bool = False) -> None:
    """Drop and recreate the public schema, then rebuild all tables."""
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("GRANT ALL ON SCHEMA public TO postgres"))
        await conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
        await conn.run_sync(Base.metadata.create_all)

    print(f"Database reset complete for: {settings.DATABASE_URL}")

    if seed:
        await seed_database()


async def drop_database() -> None:
    """Drop all managed tables without recreating them."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    print(f"Database tables dropped for: {settings.DATABASE_URL}")


async def main(command: str, seed: bool) -> None:
    try:
        if command == "init":
            await init_database()
        elif command == "seed":
            await seed_database()
        elif command == "reset":
            await reset_database(seed=seed)
        elif command == "drop":
            await drop_database()
    finally:
        await engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manage the HealthPA PostgreSQL database lifecycle."
    )
    parser.add_argument(
        "command",
        choices=["init", "seed", "reset", "drop"],
        help="Database action to run.",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Seed sample data after reset.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(command=args.command, seed=args.seed))
