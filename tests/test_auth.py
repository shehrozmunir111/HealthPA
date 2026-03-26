"""
Authentication Endpoint Tests
"""

import pytest
from httpx import AsyncClient

from app.core.security import get_current_user
from app.models.user import User, UserRole


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test health endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["project"] == "HealthPA"


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    """Test login with invalid credentials."""
    response = await client.post(
        "/api/auth/login",
        data={"username": "invalid@example.com", "password": "wrongpassword"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_user: User):
    """Test login with wrong password."""
    response = await client.post(
        "/api/auth/login",
        data={"username": test_user.email, "password": "wrongpassword"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user: User):
    """Test successful login."""
    response = await client.post(
        "/api/auth/login",
        data={"username": test_user.email, "password": "testpass123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "hospital_id" in data


@pytest.mark.asyncio
async def test_login_inactive_user(client: AsyncClient, db_session, test_hospital):
    """Test login with inactive user."""
    from app.core.password import get_password_hash
    inactive_user = User(
        email="inactive@test.com",
        hashed_password=get_password_hash("password123"),
        first_name="Inactive",
        last_name="User",
        role=UserRole.STAFF,
        is_active=False,
        hospital_id=test_hospital.id
    )
    db_session.add(inactive_user)
    await db_session.commit()
    
    response = await client.post(
        "/api/auth/login",
        data={"username": "inactive@test.com", "password": "password123"}
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient, test_hospital):
    """Test successful user registration."""
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "newuser@test.com",
            "password": "newpass123",
            "first_name": "New",
            "last_name": "User",
            "role": "staff",
            "hospital_id": str(test_hospital.id)
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@test.com"
    assert data["first_name"] == "New"
    assert data["last_name"] == "User"
    assert data["role"] == "staff"
    assert "id" in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, test_user: User):
    """Test registration with duplicate email."""
    response = await client.post(
        "/api/auth/register",
        json={
            "email": test_user.email,
            "password": "newpass123",
            "first_name": "Duplicate",
            "last_name": "User",
            "role": "staff",
            "hospital_id": str(test_user.hospital_id)
        }
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_invalid_email(client: AsyncClient, test_hospital):
    """Test registration with invalid email."""
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "invalid-email",
            "password": "newpass123",
            "first_name": "Test",
            "last_name": "User",
            "role": "staff",
            "hospital_id": str(test_hospital.id)
        }
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_short_password(client: AsyncClient, test_hospital):
    """Test registration with short password."""
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "test@example.com",
            "password": "short",
            "first_name": "Test",
            "last_name": "User",
            "role": "staff",
            "hospital_id": str(test_hospital.id)
        }
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_rejects_token_with_mismatched_hospital_claim(db_session, test_user: User, test_hospital_2):
    """Test that JWT hospital claims must match the user's actual tenant."""
    from app.core.security import create_access_token

    token = create_access_token(
        data={
            "sub": str(test_user.id),
            "hospital_id": str(test_hospital_2.id),
            "role": test_user.role.value,
        }
    )

    with pytest.raises(Exception) as exc_info:
        await get_current_user(token=token, db=db_session)

    assert getattr(exc_info.value, "status_code", None) == 401
