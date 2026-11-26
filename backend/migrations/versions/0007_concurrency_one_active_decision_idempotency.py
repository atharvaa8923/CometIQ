"""concurrency: one active decision per course and skill, idempotency keys

Revision ID: 0007_concurrency
Revises: 0006_db_hardening
"""
import sqlalchemy as sa
from alembic import op

revision = '0007_concurrency'
down_revision = '0006_db_hardening'
branch_labels = None
depends_on = None

ACTIVE = "status IN ('open', 'drafted', 'implemented')"


def upgrade() -> None:
    # if a race already produced two active decisions, keep the newest and mark the others superseded
    op.execute(f"""
        UPDATE gap_decisions SET status = 'superseded'
        WHERE {ACTIVE} AND EXISTS (
            SELECT 1 FROM gap_decisions newer
            WHERE newer.syllabus_id = gap_decisions.syllabus_id AND newer.skill_id = gap_decisions.skill_id
              AND newer.status IN ('open', 'drafted', 'implemented')
              AND (newer.decided_at > gap_decisions.decided_at
                   OR (newer.decided_at = gap_decisions.decided_at AND newer.id > gap_decisions.id)))""")
    op.create_index('uq_gap_decisions_one_active', 'gap_decisions', ['syllabus_id', 'skill_id'], unique=True,
                    postgresql_where=sa.text(ACTIVE), sqlite_where=sa.text(ACTIVE))
    op.create_table(
        'idempotency_keys',
        sa.Column('key', sa.String(length=120), primary_key=True),
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('method', sa.String(length=10), nullable=False),
        sa.Column('path', sa.String(length=300), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('response_status', sa.Integer(), nullable=True),
        sa.Column('response_body', sa.LargeBinary(), nullable=True),
        sa.Column('response_type', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'done')", name='ck_idempotency_keys_status'),
    )
    op.create_index('ix_idempotency_keys_created_at', 'idempotency_keys', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_idempotency_keys_created_at', table_name='idempotency_keys')
    op.drop_table('idempotency_keys')
    op.drop_index('uq_gap_decisions_one_active', table_name='gap_decisions')
