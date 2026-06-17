"""AI grounded-coding layer: add audit actions (ai_codes_proposed, codes_reviewed)

The AI layer otherwise reuses existing columns (pa_requests.ai_extracted_codes,
diagnosis_codes, procedure_codes) and stores no new tables here: the LangGraph
HITL checkpointer creates its own tables at runtime via PostgresSaver.setup(),
and vectors live in Pinecone (external). This migration only extends the
`auditaction` enum with the two new AI audit actions.

Revision ID: 0002_ai_audit_actions
Revises: 0001_ses_email
Create Date: 2026-06-17 00:00:00.000000
"""

from alembic import op

revision = "0002_ai_audit_actions"
down_revision = "0001_ses_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL 12+ allows ADD VALUE inside a transaction; IF NOT EXISTS makes
    # this idempotent if the enum already has these members. Guard on the type
    # existing so a fresh DB (base schema not yet created) doesn't error here.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'auditaction') THEN
                ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'ai_codes_proposed';
                ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'codes_reviewed';
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    # PostgreSQL cannot drop a value from an enum type without recreating it;
    # leaving the (unused) values in place is safe and intentional.
    pass
