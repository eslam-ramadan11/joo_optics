"""Make order_items.prescription_id nullable (plain frames/sunglasses don't need a prescription)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-30 09:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    # SQLite can't ALTER COLUMN directly - use batch mode, which recreates
    # the table under the hood. Existing rows keep their current
    # prescription_id values; only the NOT NULL constraint is relaxed.
    with op.batch_alter_table('order_items', schema=None) as batch_op:
        batch_op.alter_column(
            'prescription_id',
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade():
    # NOTE: if any order_items rows have prescription_id=NULL at this
    # point, downgrading will fail (NOT NULL can't be re-applied over NULLs).
    # Backfill or delete those rows first if you need to actually roll back.
    with op.batch_alter_table('order_items', schema=None) as batch_op:
        batch_op.alter_column(
            'prescription_id',
            existing_type=sa.Integer(),
            nullable=False,
        )
