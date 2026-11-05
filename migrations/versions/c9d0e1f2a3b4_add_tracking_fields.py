"""Add marketing attribution and purchase-tracking idempotency fields to orders

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-08-19 09:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('orders', sa.Column('utm_source', sa.String(length=255), nullable=True))
    op.add_column('orders', sa.Column('utm_medium', sa.String(length=255), nullable=True))
    op.add_column('orders', sa.Column('utm_campaign', sa.String(length=255), nullable=True))
    op.add_column('orders', sa.Column('utm_content', sa.String(length=255), nullable=True))
    op.add_column('orders', sa.Column('utm_term', sa.String(length=255), nullable=True))
    op.add_column('orders', sa.Column('fbp', sa.String(length=255), nullable=True))
    op.add_column('orders', sa.Column('fbc', sa.String(length=255), nullable=True))
    op.add_column('orders', sa.Column('ga4_client_id', sa.String(length=255), nullable=True))
    op.add_column('orders', sa.Column('purchase_tracked_at', sa.DateTime(), nullable=True))
    op.add_column('orders', sa.Column('purchase_client_notified_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('orders', 'purchase_client_notified_at')
    op.drop_column('orders', 'purchase_tracked_at')
    op.drop_column('orders', 'ga4_client_id')
    op.drop_column('orders', 'fbc')
    op.drop_column('orders', 'fbp')
    op.drop_column('orders', 'utm_term')
    op.drop_column('orders', 'utm_content')
    op.drop_column('orders', 'utm_campaign')
    op.drop_column('orders', 'utm_medium')
    op.drop_column('orders', 'utm_source')
