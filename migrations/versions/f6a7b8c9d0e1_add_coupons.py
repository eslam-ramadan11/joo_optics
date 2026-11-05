"""Add coupons table and coupon fields on orders

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-15 09:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'coupons',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('discount_type', sa.String(length=20), nullable=False),
        sa.Column('discount_value', sa.Float(), nullable=False),
        sa.Column('start_date', sa.DateTime(), nullable=True),
        sa.Column('end_date', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('max_total_uses', sa.Integer(), nullable=True),
        sa.Column('max_uses_per_customer', sa.Integer(), nullable=True),
        sa.Column('apply_to', sa.String(length=30), nullable=False),
        sa.Column('apply_to_value', sa.String(length=500), nullable=True),
        sa.Column('min_order_amount', sa.Float(), nullable=True),
        sa.Column('max_discount_amount', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_coupons_code'), 'coupons', ['code'], unique=True)

    # SQLite needs batch mode for adding columns with a foreign key.
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('coupon_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('discount_amount', sa.Float(), nullable=False, server_default='0'))
        batch_op.create_foreign_key('fk_orders_coupon_id', 'coupons', ['coupon_id'], ['id'], ondelete='SET NULL')
        batch_op.create_index(op.f('ix_orders_coupon_id'), ['coupon_id'], unique=False)


def downgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_index(op.f('ix_orders_coupon_id'))
        batch_op.drop_constraint('fk_orders_coupon_id', type_='foreignkey')
        batch_op.drop_column('discount_amount')
        batch_op.drop_column('coupon_id')

    op.drop_index(op.f('ix_coupons_code'), table_name='coupons')
    op.drop_table('coupons')
