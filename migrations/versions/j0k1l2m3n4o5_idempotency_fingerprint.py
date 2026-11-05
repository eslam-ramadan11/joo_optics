"""Store the request fingerprint for safe idempotent order retries."""
from alembic import op
import sqlalchemy as sa

revision = 'j0k1l2m3n4o5'
down_revision = 'i9j0k1l2m3n4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('orders') as batch_op:
        batch_op.add_column(sa.Column('idempotency_fingerprint', sa.String(length=64), nullable=True))


def downgrade():
    with op.batch_alter_table('orders') as batch_op:
        batch_op.drop_column('idempotency_fingerprint')
