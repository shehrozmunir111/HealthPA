"""
PA Request Endpoint Tests
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.asyncio
async def test_list_pa_requests_unauthorized(client: AsyncClient):
    """Test listing PA requests without authentication."""
    response = await client.get("/api/pa-requests/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_pa_requests_success(auth_client: AsyncClient, test_pa_request):
    """Test listing PA requests with authentication."""
    response = await auth_client.get("/api/pa-requests/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["request_number"] == "PA-001"


@pytest.mark.asyncio
async def test_list_pa_requests_filter_by_status(auth_client: AsyncClient, test_pa_request):
    """Test listing PA requests filtered by status."""
    response = await auth_client.get("/api/pa-requests/?status=draft")
    assert response.status_code == 200
    data = response.json()
    assert all(p["status"] == "draft" for p in data)


@pytest.mark.asyncio
async def test_list_pa_requests_pagination(auth_client: AsyncClient, test_pa_request):
    """Test listing PA requests with pagination."""
    response = await auth_client.get("/api/pa-requests/?skip=0&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_create_pa_request_success(auth_client: AsyncClient, test_patient):
    """Test creating a new PA request."""
    response = await auth_client.post(
        "/api/pa-requests/",
        json={
            "patient_id": str(test_patient.id),
            "request_number": "PA-NEW-001",
            "diagnosis_codes": ["J20.9"],
            "procedure_codes": ["99201"],
            "clinical_notes": "Test clinical notes",
            "payer_name": "New Test Payer",
            "payer_id": "NEW-PAYER-001",
            "is_urgent": True
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["request_number"] == "PA-NEW-001"
    assert data["patient_id"] == str(test_patient.id)
    assert data["payer_name"] == "New Test Payer"
    assert data["is_urgent"] is True
    assert data["status"] == "draft"


@pytest.mark.asyncio
async def test_create_pa_request_patient_not_found(auth_client: AsyncClient):
    """Test creating PA request with non-existent patient."""
    response = await auth_client.post(
        "/api/pa-requests/",
        json={
            "patient_id": str(uuid4()),
            "request_number": "PA-orphan",
            "payer_name": "Test Payer"
        }
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_pa_request_missing_fields(auth_client: AsyncClient, test_patient):
    """Test creating PA request with missing required fields."""
    response = await auth_client.post(
        "/api/pa-requests/",
        json={
            "patient_id": str(test_patient.id)
        }
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_pa_request_success(auth_client: AsyncClient, test_pa_request):
    """Test getting a specific PA request."""
    response = await auth_client.get(f"/api/pa-requests/{test_pa_request.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_pa_request.id)
    assert data["request_number"] == test_pa_request.request_number


@pytest.mark.asyncio
async def test_get_pa_request_not_found(auth_client: AsyncClient):
    """Test getting a non-existent PA request."""
    response = await auth_client.get(f"/api/pa-requests/{uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_pa_status_draft_to_pending(auth_client: AsyncClient, test_pa_request):
    """Test transitioning PA request from draft to pending."""
    response = await auth_client.patch(
        f"/api/pa-requests/{test_pa_request.id}/status",
        json={
            "status": "pending",
            "notes": "Submitting for review"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert data["submitted_at"] is not None


@pytest.mark.asyncio
async def test_update_pa_status_to_approved(auth_client: AsyncClient, db_session, test_hospital, test_patient, test_user):
    """Test transitioning PA request to approved (requires DRAFT -> PENDING -> APPROVED)."""
    from datetime import date
    from app.models.pa_request import PARequest, PARequestStatus
    
    pa_request = PARequest(
        id=uuid4(),
        hospital_id=test_hospital.id,
        patient_id=test_patient.id,
        created_by_id=test_user.id,
        request_number="PA-APPROVE-001",
        payer_name="Test Payer",
        status=PARequestStatus.DRAFT,
        requested_date=date(2024, 1, 15)
    )
    db_session.add(pa_request)
    await db_session.commit()
    await db_session.refresh(pa_request)
    
    # First transition: DRAFT -> PENDING
    response = await auth_client.patch(
        f"/api/pa-requests/{pa_request.id}/status",
        json={"status": "pending", "notes": "Submitting for review"}
    )
    assert response.status_code == 200
    
    # Second transition: PENDING -> APPROVED
    response = await auth_client.patch(
        f"/api/pa-requests/{pa_request.id}/status",
        json={
            "status": "approved",
            "notes": "Approved by reviewer"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["decision_notes"] == "Approved by reviewer"
    assert data["decision_date"] is not None


@pytest.mark.asyncio
async def test_update_pa_status_invalid_transition(auth_client: AsyncClient, test_pa_request):
    """Test that invalid FSM transitions are rejected (e.g., DRAFT -> COMPLETED)."""
    response = await auth_client.patch(
        f"/api/pa-requests/{test_pa_request.id}/status",
        json={
            "status": "completed"
        }
    )
    assert response.status_code == 400
    error_detail = response.json().get("detail", response.json().get("message", ""))
    assert "Invalid transition" in error_detail


@pytest.mark.asyncio
async def test_pa_request_status_history(auth_client: AsyncClient, test_pa_request):
    """Test that status history is recorded."""
    response = await auth_client.patch(
        f"/api/pa-requests/{test_pa_request.id}/status",
        json={
            "status": "pending",
            "notes": "Test transition"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "status_history" in data
    assert len(data["status_history"]) >= 1
    assert data["status_history"][-1]["to"] == "pending"


@pytest.mark.asyncio
async def test_pa_request_cross_hospital_isolation(auth_client: AsyncClient, test_patient_2):
    """Test that PA requests from other hospitals are not accessible."""
    from app.models.pa_request import PARequest
    
    response = await auth_client.post(
        "/api/pa-requests/",
        json={
            "patient_id": str(test_patient_2.id),
            "request_number": "PA-OTHER-HOSP",
            "payer_name": "Other Hospital Payer"
        }
    )
    assert response.status_code == 403
