"""
Pytest configuration backed by PostgreSQL.
"""

import asyncio
from datetime import date
from typing import AsyncGenerator
from unittest.mock import patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.middleware import rate_limiter
from app.core.password import get_password_hash
from app.core.security import create_access_token
from app.main import app
from app.models.hospital import Hospital
from app.models.pa_request import PARequest, PARequestStatus
from app.models.patient import Patient
from app.models.user import User, UserRole


TEST_DATABASE_URL = settings.effective_test_database_url
TEST_DATABASE_SCHEMA = settings.TEST_DATABASE_SCHEMA


# ---------------------------------------------------------------------------
# Cross-cutting autouse fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear the in-memory rate limiter state before and after every test
    so that tests don't bleed request-count state into each other."""
    rate_limiter._requests.clear()
    yield
    rate_limiter._requests.clear()


@pytest.fixture(autouse=True)
def mock_email_tasks():
    """Globally silence all email Celery task .delay() calls so tests never
    attempt a broker connection.  Individual tests can override specific tasks
    with their own @patch if they need to make assertions on the call."""
    with (
        patch("app.tasks.email.send_email.delay"),
        patch("app.tasks.email.send_verification_email.delay"),
        patch("app.tasks.email.send_password_reset_email.delay"),
        patch("app.tasks.email.send_appointment_reminder.delay"),
        patch("app.tasks.email.send_fraud_alert.delay"),
    ):
        yield

# NullPool: each operation gets a fresh connection, no pool state bound to a
# specific event loop. This prevents the asyncpg "attached to a different loop"
# error that occurs when the pool is created in a different loop than the one
# running the test fixtures.
admin_test_engine = create_async_engine(
    TEST_DATABASE_URL, echo=False, future=True, poolclass=NullPool
)
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    future=True,
    poolclass=NullPool,
    connect_args={"server_settings": {"search_path": TEST_DATABASE_SCHEMA}},
)
TestingSessionLocal = sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def _truncate_all_tables() -> None:
    """Clear all PostgreSQL tables between tests."""
    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(
                text(
                    f'TRUNCATE TABLE "{TEST_DATABASE_SCHEMA}"."{table.name}" RESTART IDENTITY CASCADE'
                )
            )


@pytest_asyncio.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def prepare_test_database():
    """Provision PostgreSQL test schema once per session."""
    async with admin_test_engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{TEST_DATABASE_SCHEMA}"'))

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    async with admin_test_engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{TEST_DATABASE_SCHEMA}" CASCADE'))

    await test_engine.dispose()
    await admin_test_engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh PostgreSQL-backed session for each test."""
    await _truncate_all_tables()

    async with TestingSessionLocal() as session:
        yield session
        await session.rollback()

    await _truncate_all_tables()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with overridden dependencies."""

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_hospital(db_session: AsyncSession) -> Hospital:
    """Create a test hospital."""
    hospital = Hospital(
        id=uuid4(),
        name="Test Medical Center",
        code="TMC001",
        address="123 Test Street",
        phone="555-0100",
        email="admin@testmedical.com",
        is_active=True,
    )
    db_session.add(hospital)
    await db_session.commit()
    await db_session.refresh(hospital)
    return hospital


@pytest_asyncio.fixture
async def test_hospital_2(db_session: AsyncSession) -> Hospital:
    """Create a second test hospital for isolation testing."""
    hospital = Hospital(
        id=uuid4(),
        name="Second Hospital",
        code="SH001",
        address="456 Second Street",
        phone="555-0200",
        email="admin@second.com",
        is_active=True,
    )
    db_session.add(hospital)
    await db_session.commit()
    await db_session.refresh(hospital)
    return hospital


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession, test_hospital: Hospital) -> User:
    """Create a test user."""
    user = User(
        id=uuid4(),
        email="doctor@test.com",
        hashed_password=get_password_hash("testpass123"),
        first_name="John",
        last_name="Doctor",
        role=UserRole.DOCTOR,
        is_active=True,
        hospital_id=test_hospital.id,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession, test_hospital: Hospital) -> User:
    """Create an admin user."""
    user = User(
        id=uuid4(),
        email="admin@test.com",
        hashed_password=get_password_hash("adminpass123"),
        first_name="Admin",
        last_name="User",
        role=UserRole.ADMIN,
        is_active=True,
        hospital_id=test_hospital.id,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_user_2(db_session: AsyncSession, test_hospital_2: Hospital) -> User:
    """Create a test user in hospital 2."""
    user = User(
        id=uuid4(),
        email="doctor@second.com",
        hashed_password=get_password_hash("testpass123"),
        first_name="Jane",
        last_name="Doctor",
        role=UserRole.DOCTOR,
        is_active=True,
        hospital_id=test_hospital_2.id,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_patient(db_session: AsyncSession, test_hospital: Hospital) -> Patient:
    """Create a test patient."""
    patient = Patient(
        id=uuid4(),
        hospital_id=test_hospital.id,
        mrn="MRN001",
        first_name="Test",
        last_name="Patient",
        date_of_birth=date(1990, 1, 15),
        phone="555-1234",
        email="patient@test.com",
        address="789 Patient Lane",
        insurance_provider="Test Insurance",
        insurance_policy_number="POL123",
        insurance_group_number="GRP456",
    )
    db_session.add(patient)
    await db_session.commit()
    await db_session.refresh(patient)
    return patient


@pytest_asyncio.fixture
async def test_patient_2(db_session: AsyncSession, test_hospital_2: Hospital) -> Patient:
    """Create a test patient in hospital 2."""
    patient = Patient(
        id=uuid4(),
        hospital_id=test_hospital_2.id,
        mrn="MRN002",
        first_name="Second",
        last_name="Patient",
        date_of_birth=date(1985, 5, 20),
        phone="555-5678",
        email="patient@second.com",
        insurance_provider="Second Insurance",
        insurance_policy_number="POL789",
    )
    db_session.add(patient)
    await db_session.commit()
    await db_session.refresh(patient)
    return patient


@pytest_asyncio.fixture
async def test_pa_request(
    db_session: AsyncSession,
    test_hospital: Hospital,
    test_patient: Patient,
    test_user: User,
) -> PARequest:
    """Create a test PA request."""
    pa_request = PARequest(
        id=uuid4(),
        hospital_id=test_hospital.id,
        patient_id=test_patient.id,
        created_by_id=test_user.id,
        request_number="PA-001",
        diagnosis_codes=["J06.9", "R05"],
        procedure_codes=["99213", "87880"],
        clinical_notes="Test clinical notes",
        payer_name="Test Payer",
        payer_id="PAY001",
        is_urgent=False,
        status=PARequestStatus.DRAFT,
        requested_date=date(2024, 1, 15),
    )
    db_session.add(pa_request)
    await db_session.commit()
    await db_session.refresh(pa_request)
    return pa_request


@pytest.fixture
def user_token(test_user: User, test_hospital: Hospital) -> str:
    """Generate a JWT token for test_user."""
    return create_access_token(
        data={
            "sub": str(test_user.id),
            "hospital_id": str(test_hospital.id),
            "role": test_user.role.value,
        }
    )


@pytest.fixture
def admin_token(admin_user: User, test_hospital: Hospital) -> str:
    """Generate a JWT token for admin_user."""
    return create_access_token(
        data={
            "sub": str(admin_user.id),
            "hospital_id": str(test_hospital.id),
            "role": admin_user.role.value,
        }
    )


@pytest.fixture
def user_2_token(test_user_2: User, test_hospital_2: Hospital) -> str:
    """Generate a JWT token for test_user_2 in hospital 2."""
    return create_access_token(
        data={
            "sub": str(test_user_2.id),
            "hospital_id": str(test_hospital_2.id),
            "role": test_user_2.role.value,
        }
    )


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient, user_token: str) -> AsyncClient:
    """Create an authenticated client with user token."""
    client.headers["Authorization"] = f"Bearer {user_token}"
    return client


@pytest_asyncio.fixture
async def admin_client(client: AsyncClient, admin_token: str) -> AsyncClient:
    """Create an authenticated client with admin token."""
    client.headers["Authorization"] = f"Bearer {admin_token}"
    return client
