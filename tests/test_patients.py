"""
Patient Endpoint Tests
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.asyncio
async def test_list_patients_unauthorized(client: AsyncClient):
    """Test listing patients without authentication."""
    response = await client.get("/api/patients/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_patients_success(auth_client: AsyncClient, test_patient):
    """Test listing patients with authentication."""
    response = await auth_client.get("/api/patients/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["mrn"] == "MRN001"


@pytest.mark.asyncio
async def test_list_patients_isolation(auth_client: AsyncClient, test_patient_2):
    """Test that patients from other hospitals are not visible."""
    response = await auth_client.get("/api/patients/")
    assert response.status_code == 200
    data = response.json()
    mrns = [p["mrn"] for p in data]
    assert "MRN002" not in mrns


@pytest.mark.asyncio
async def test_list_patients_pagination(auth_client: AsyncClient, test_patient):
    """Test listing patients with pagination."""
    response = await auth_client.get("/api/patients/?skip=0&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_create_patient_success(auth_client: AsyncClient):
    """Test creating a new patient."""
    response = await auth_client.post(
        "/api/patients/",
        json={
            "mrn": "NEW-MRN-001",
            "first_name": "New",
            "last_name": "Patient",
            "date_of_birth": "1995-05-15",
            "phone": "555-1111",
            "email": "new@patient.com",
            "address": "123 Patient Lane",
            "insurance_provider": "New Insurance",
            "insurance_policy_number": "NEW-POL-123",
            "insurance_group_number": "NEW-GRP-456"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["mrn"] == "NEW-MRN-001"
    assert data["first_name"] == "New"
    assert data["last_name"] == "Patient"
    assert data["insurance_provider"] == "New Insurance"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_patient_minimal(auth_client: AsyncClient):
    """Test creating a patient with minimal required fields."""
    response = await auth_client.post(
        "/api/patients/",
        json={
            "mrn": "MINIMAL-MRN",
            "first_name": "Minimal",
            "last_name": "Patient",
            "date_of_birth": "2000-01-01"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["mrn"] == "MINIMAL-MRN"


@pytest.mark.asyncio
async def test_create_patient_missing_fields(auth_client: AsyncClient):
    """Test creating patient with missing required fields."""
    response = await auth_client.post(
        "/api/patients/",
        json={
            "mrn": "INCOMPLETE"
        }
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_patient_invalid_email(auth_client: AsyncClient):
    """Test creating patient with invalid email."""
    response = await auth_client.post(
        "/api/patients/",
        json={
            "mrn": "BAD-EMAIL-MRN",
            "first_name": "Bad",
            "last_name": "Email",
            "date_of_birth": "1990-01-01",
            "email": "invalid-email"
        }
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_patient_success(auth_client: AsyncClient, test_patient):
    """Test getting a specific patient."""
    response = await auth_client.get(f"/api/patients/{test_patient.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_patient.id)
    assert data["mrn"] == test_patient.mrn
    assert data["first_name"] == test_patient.first_name


@pytest.mark.asyncio
async def test_get_patient_not_found(auth_client: AsyncClient):
    """Test getting a non-existent patient."""
    response = await auth_client.get(f"/api/patients/{uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_patient_success(auth_client: AsyncClient, test_patient):
    """Test updating a patient."""
    response = await auth_client.patch(
        f"/api/patients/{test_patient.id}",
        json={
            "first_name": "Updated",
            "phone": "555-123-4567",
            "insurance_provider": "Updated Insurance"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["first_name"] == "Updated"
    assert data["phone"] == "555-123-4567"
    assert data["last_name"] == test_patient.last_name


@pytest.mark.asyncio
async def test_update_patient_not_found(auth_client: AsyncClient):
    """Test updating a non-existent patient."""
    response = await auth_client.patch(
        f"/api/patients/{uuid4()}",
        json={"first_name": "Updated"}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_patient_success(auth_client: AsyncClient, db_session, test_hospital):
    """Test deleting a patient."""
    from datetime import date
    from app.models.patient import Patient
    patient = Patient(
        id=uuid4(),
        hospital_id=test_hospital.id,
        mrn="DELETE-MRN",
        first_name="Delete",
        last_name="Me",
        date_of_birth=date(1990, 1, 1)
    )
    db_session.add(patient)
    await db_session.commit()
    
    response = await auth_client.delete(f"/api/patients/{patient.id}")
    assert response.status_code == 204
    
    get_response = await auth_client.get(f"/api/patients/{patient.id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_patient_not_found(auth_client: AsyncClient):
    """Test deleting a non-existent patient."""
    response = await auth_client.delete(f"/api/patients/{uuid4()}")
    assert response.status_code == 404
