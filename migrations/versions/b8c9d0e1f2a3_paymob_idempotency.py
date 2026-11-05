"""Add Paymob idempotency fields and make paymob_order_id unique

Adds paymob_iframe_url and paymob_token_issued_at to payments, so a
duplicate/concurrent initiate request can be served the same cached
Paymob session instead of registering a new order with Paymob every
time (see PaymentService.initiate_paymob_payment).

Also makes paymob_order_id UNIQUE at the database level - it was
previously indexed but not unique, so nothing stopped two different
Payment rows from ever ending up pointing at the same Paymob order.
NULL values (payments never sent to Paymob, e.g. cash on delivery)
are unaffected - standard SQL treats NULLs as distinct for uniqueness.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-18 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('payments', sa.Column('paymob_iframe_url', sa.Text(), nullable=True))
    op.add_column('payments', sa.Column('paymob_token_issued_at', sa.DateTime(), nullable=True))

    # Replace the old non-unique index with a unique one - can't alter
    # uniqueness in place, so drop and recreate.
    op.drop_index(op.f('ix_payments_paymob_order_id'), table_name='payments')
    op.create_index(op.f('ix_payments_paymob_order_id'), 'payments', ['paymob_order_id'], unique=True)


def downgrade():
    op.drop_index(op.f('ix_payments_paymob_order_id'), table_name='payments')
    op.create_index(op.f('ix_payments_paymob_order_id'), 'payments', ['paymob_order_id'], unique=False)

    op.drop_column('payments', 'paymob_token_issued_at')
    op.drop_column('payments', 'paymob_iframe_url')
