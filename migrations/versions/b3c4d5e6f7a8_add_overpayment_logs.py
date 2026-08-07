"""add overpayment_logs table

Revision ID: b3c4d5e6f7a8
Revises: e2a21139b806
Create Date: 2026-03-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision    = 'b3c4d5e6f7a8'
down_revision = 'e2a21139b806'
branch_labels = None
depends_on    = None


def upgrade():
    op.create_table(
        'overpayment_logs',
        sa.Column('id',                  sa.Integer(),       nullable=False),
        sa.Column('reservation_id',      sa.Integer(),       nullable=False),
        sa.Column('guest_id',            sa.Integer(),       nullable=True),
        sa.Column('overpaid_amount',     sa.Numeric(10, 2),  nullable=False),
        sa.Column('reason',              sa.String(20),      nullable=False),
        sa.Column('resolution',          sa.String(20),      nullable=False),
        sa.Column('refund_mode_id',      sa.Integer(),       nullable=True),
        sa.Column('waiter_name',         sa.String(100),     nullable=True),
        sa.Column('remarks',             sa.Text(),          nullable=True),
        sa.Column('resolved_by_user_id', sa.Integer(),       nullable=True),
        sa.Column('created_at',          sa.DateTime(),      nullable=True),
        sa.ForeignKeyConstraint(['reservation_id'],      ['reservations.id']),
        sa.ForeignKeyConstraint(['guest_id'],             ['guests.id']),
        sa.ForeignKeyConstraint(['refund_mode_id'],       ['payment_modes.id']),
        sa.ForeignKeyConstraint(['resolved_by_user_id'],  ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_overpay_reservation', 'overpayment_logs', ['reservation_id'])


def downgrade():
    op.drop_index('idx_overpay_reservation', table_name='overpayment_logs')
    op.drop_table('overpayment_logs')
