"""Add stock reservation expiry."""
from alembic import op
import sqlalchemy as sa

revision = 'i9j0k1l2m3n4'
down_revision = 'h8i9j0k1l2m3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('orders') as batch_op:
        batch_op.add_column(sa.Column('stock_reserved_until', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_orders_stock_reserved_until', ['stock_reserved_until'])


def downgrade():
    with op.batch_alter_table('orders') as batch_op:
        batch_op.drop_index('ix_orders_stock_reserved_until')
        batch_op.drop_column('stock_reserved_until')
