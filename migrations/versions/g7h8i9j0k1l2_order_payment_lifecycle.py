"""Add order idempotency, stock release, and Paymob attempts."""
from alembic import op
import sqlalchemy as sa

revision = 'g7h8i9j0k1l2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('orders') as batch_op:
        batch_op.add_column(sa.Column('idempotency_key', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('stock_released_at', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_orders_idempotency_key', ['idempotency_key'], unique=True)

    op.create_table(
        'payment_attempts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('payment_id', sa.Integer(), nullable=False),
        sa.Column('paymob_order_id', sa.String(length=50), nullable=False),
        sa.Column('transaction_id', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('paymob_order_id'),
        sa.UniqueConstraint('transaction_id'),
    )
    op.create_index('ix_payment_attempts_order_id', 'payment_attempts', ['order_id'])
    op.create_index('ix_payment_attempts_payment_id', 'payment_attempts', ['payment_id'])


def downgrade():
    op.drop_index('ix_payment_attempts_payment_id', table_name='payment_attempts')
    op.drop_index('ix_payment_attempts_order_id', table_name='payment_attempts')
    op.drop_table('payment_attempts')
    with op.batch_alter_table('orders') as batch_op:
        batch_op.drop_index('ix_orders_idempotency_key')
        batch_op.drop_column('stock_released_at')
        batch_op.drop_column('idempotency_key')
