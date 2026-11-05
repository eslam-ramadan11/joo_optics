"""Add paymob_order_id to payments

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-24 08:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('payments', sa.Column('paymob_order_id', sa.String(length=50), nullable=True))
    op.create_index(op.f('ix_payments_paymob_order_id'), 'payments', ['paymob_order_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_payments_paymob_order_id'), table_name='payments')
    op.drop_column('payments', 'paymob_order_id')
