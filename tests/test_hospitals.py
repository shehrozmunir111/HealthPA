"""
Hospital Endpoint Tests
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_hospitals_unauthorized(client: AsyncClient):
    """Test listing hospitals without authentication."""
    response = await client.get("/api/hospitals/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_hospitals_success(auth_client: AsyncClient, test_hospital):
    """Test listing hospitals with authentication."""
    response = await auth_client.get("/api/hospitals/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_list_hospitals_pagination(auth_client: AsyncClient, test_hospital):
    """Test listing hospitals with pagination."""
    response = await auth_client.get("/api/hospitals/?skip=0&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_create_hospital_success(admin_client: AsyncClient):
    """Test creating a new hospital."""
    response = await admin_client.post(
        "/api/hospitals/",
        json={
            "name": "New Test Hospital",
            "code": "NTH001",
            "address": "123 New Hospital Road",
            "phone": "555-9999",
            "email": "admin@newhospital.com"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "New Test Hospital"
    assert data["code"] == "NTH001"
    assert data["address"] == "123 New Hospital Road"
    assert "id" in data
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_hospital_duplicate_code(admin_client: AsyncClient, test_hospital):
    """Test creating hospital with duplicate code."""
    response = await admin_client.post(
        "/api/hospitals/",
        json={
            "name": "Another Hospital",
            "code": test_hospital.code,
            "address": "456 Duplicate Road"
        }
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_hospital_missing_fields(admin_client: AsyncClient):
    """Test creating hospital with missing required fields."""
    response = await admin_client.post(
        "/api/hospitals/",
        json={
            "name": "Incomplete Hospital"
        }
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_hospital_success(auth_client: AsyncClient, test_hospital):
    """Test getting a specific hospital."""
    response = await auth_client.get(f"/api/hospitals/{test_hospital.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_hospital.id)
    assert data["name"] == test_hospital.name
    assert data["code"] == test_hospital.code


@pytest.mark.asyncio
async def test_get_hospital_not_found(auth_client: AsyncClient):
    """Test getting a non-existent hospital."""
    from uuid import uuid4
    response = await auth_client.get(f"/api/hospitals/{uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_hospital_success(admin_client: AsyncClient, test_hospital):
    """Test updating a hospital."""
    response = await admin_client.patch(
        f"/api/hospitals/{test_hospital.id}",
        json={
            "name": "Updated Hospital Name",
            "phone": "555-UPDATED"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Hospital Name"
    assert data["phone"] == "555-UPDATED"
    assert data["code"] == test_hospital.code


@pytest.mark.asyncio
async def test_update_hospital_not_found(admin_client: AsyncClient):
    """Test updating a non-existent hospital."""
    from uuid import uuid4
    response = await admin_client.patch(
        f"/api/hospitals/{uuid4()}",
        json={"name": "Updated Name"}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_hospital_partial(admin_client: AsyncClient, test_hospital):
    """Test partial update of a hospital."""
    response = await admin_client.patch(
        f"/api/hospitals/{test_hospital.id}",
        json={"is_active": False}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_active"] is False
