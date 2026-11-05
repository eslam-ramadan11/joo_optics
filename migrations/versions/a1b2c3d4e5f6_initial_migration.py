"""Initial migration - create all tables

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-07-23 07:00:00.000000

NOTE: hand-written to match app/models/models.py exactly, since Alembic/
Flask-Migrate could not be run in the environment that produced this file
(no network access to install them). Structurally, this is what
`flask db init && flask db migrate -m "Initial migration"` would generate
against a fresh, empty database with these models. Please review it and
run `flask db upgrade` yourself to confirm it applies cleanly - if your
database already has these tables (e.g. from the old site.db), see the
note at the bottom of this file before running it.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # --- users ---
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=80), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('password_hash', sa.String(length=256), nullable=False),
        sa.Column('is_admin', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # --- products ---
    op.create_table(
        'products',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('old_price', sa.Float(), nullable=True),
        sa.Column('category', sa.String(length=80), nullable=False),
        sa.Column('image_file', sa.String(length=255), nullable=False),
        sa.Column('discount_badge', sa.String(length=50), nullable=True),
        sa.Column('colors', sa.String(length=500), nullable=False),
        sa.Column('stock_quantity', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # --- shipping_addresses ---
    op.create_table(
        'shipping_addresses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('city', sa.String(length=100), nullable=False),
        sa.Column('full_address', sa.String(length=255), nullable=False),
        sa.Column('phone_number', sa.String(length=20), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_shipping_addresses_user_id'), 'shipping_addresses', ['user_id'], unique=False
    )

    # --- prescriptions ---
    op.create_table(
        'prescriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('image_file', sa.String(length=255), nullable=False),
        sa.Column('sph_r', sa.Float(), nullable=False),
        sa.Column('cyl_r', sa.Float(), nullable=False),
        sa.Column('axis_r', sa.Integer(), nullable=False),
        sa.Column('sph_l', sa.Float(), nullable=False),
        sa.Column('cyl_l', sa.Float(), nullable=False),
        sa.Column('axis_l', sa.Integer(), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_prescriptions_user_id'), 'prescriptions', ['user_id'], unique=False
    )

    # --- orders ---
    op.create_table(
        'orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('address_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('total_amount', sa.Float(), nullable=False),
        sa.Column('date_posted', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['address_id'], ['shipping_addresses.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_orders_user_id'), 'orders', ['user_id'], unique=False)
    op.create_index(op.f('ix_orders_address_id'), 'orders', ['address_id'], unique=False)

    # --- order_items ---
    op.create_table(
        'order_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('prescription_id', sa.Integer(), nullable=False),
        sa.Column('lens_type', sa.String(length=80), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('item_price', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id']),
        sa.ForeignKeyConstraint(['prescription_id'], ['prescriptions.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_order_items_order_id'), 'order_items', ['order_id'], unique=False)
    op.create_index(op.f('ix_order_items_product_id'), 'order_items', ['product_id'], unique=False)
    op.create_index(
        op.f('ix_order_items_prescription_id'), 'order_items', ['prescription_id'], unique=False
    )

    # --- payments ---
    op.create_table(
        'payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('payment_method', sa.String(length=50), nullable=False),
        sa.Column('payment_status', sa.String(length=50), nullable=False),
        sa.Column('transaction_id', sa.String(length=100), nullable=True),
        sa.Column('payment_date', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('order_id'),
        sa.UniqueConstraint('transaction_id'),
    )
    op.create_index(op.f('ix_payments_order_id'), 'payments', ['order_id'], unique=True)


def downgrade():
    op.drop_index(op.f('ix_payments_order_id'), table_name='payments')
    op.drop_table('payments')

    op.drop_index(op.f('ix_order_items_prescription_id'), table_name='order_items')
    op.drop_index(op.f('ix_order_items_product_id'), table_name='order_items')
    op.drop_index(op.f('ix_order_items_order_id'), table_name='order_items')
    op.drop_table('order_items')

    op.drop_index(op.f('ix_orders_address_id'), table_name='orders')
    op.drop_index(op.f('ix_orders_user_id'), table_name='orders')
    op.drop_table('orders')

    op.drop_index(op.f('ix_prescriptions_user_id'), table_name='prescriptions')
    op.drop_table('prescriptions')

    op.drop_index(op.f('ix_shipping_addresses_user_id'), table_name='shipping_addresses')
    op.drop_table('shipping_addresses')

    op.drop_table('products')

    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_table('users')


# NOTE ON EXISTING DATABASES:
# If you already have a populated site.db created via db.create_all() rather
# than through Alembic, running `flask db upgrade` against it will fail
# because the tables already exist. In that case, stamp the database at
# this revision instead of re-running the CREATE TABLEs:
#
#     flask db stamp a1b2c3d4e5f6
#
# From then on, `flask db migrate` will correctly diff against this baseline
# for any future model changes.
