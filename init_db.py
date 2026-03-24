"""
Initialize database tables
"""

import asyncio
from app.core.database import engine, Base
from app.models.hospital import Hospital
from app.models.user import User
from app.models.patient import Patient
from app.models.pa_request import PARequest
from app.models.audit_log import AuditLog


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables created successfully!")


if __name__ == "__main__":
    asyncio.run(init_db())
