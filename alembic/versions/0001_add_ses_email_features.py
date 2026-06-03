"""Add SES email features: user verification/reset/lockout fields + appointments table

Revision ID: 0001_ses_email
Revises:
Create Date: 2026-06-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_ses_email"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users table: add email-verification, password-reset, and lockout columns ──
    op.add_column("users", sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("verification_token", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("verification_token_expires", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("reset_token", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("reset_token_expires", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_users_verification_token", "users", ["verification_token"])
    op.create_index("ix_users_reset_token", "users", ["reset_token"])

    # ── appointments table ────────────────────────────────────────────────────────
    appointment_status = postgresql.ENUM(
        "scheduled", "confirmed", "cancelled", "completed",
        name="appointmentstatus",
    )
    appointment_status.create(op.get_bind())

    op.create_table(
        "appointments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "hospital_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("hospitals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider_name", sa.String(200), nullable=False),
        sa.Column("appointment_type", sa.String(100), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("scheduled", "confirmed", "cancelled", "completed", name="appointmentstatus", create_type=False),
            nullable=False,
            server_default="scheduled",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("reminder_sent", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_index("ix_appointments_hospital_id", "appointments", ["hospital_id"])
    op.create_index("ix_appointments_patient_id", "appointments", ["patient_id"])
    op.create_index("ix_appointments_scheduled_at", "appointments", ["scheduled_at"])
    op.create_index("ix_appointments_status", "appointments", ["status"])


def downgrade() -> None:
    op.drop_table("appointments")

    appointment_status = postgresql.ENUM(name="appointmentstatus")
    appointment_status.drop(op.get_bind())

    op.drop_index("ix_users_reset_token", table_name="users")
    op.drop_index("ix_users_verification_token", table_name="users")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_attempts")
    op.drop_column("users", "reset_token_expires")
    op.drop_column("users", "reset_token")
    op.drop_column("users", "verification_token_expires")
    op.drop_column("users", "verification_token")
    op.drop_column("users", "is_verified")
