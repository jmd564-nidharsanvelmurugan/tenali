"""add indexing status, infrastructure costs, model pricing

Revision ID: manual_001
Revises: 6fcebd34a094
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'manual_001'
# down_revision = '6fcebd34a094'
down_revision = '2d0b99aa1b4e'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add IndexingStatus enum
    indexing_status_enum = sa.Enum('pending', 'indexed', 'failed', 'dead_letter', name='indexingstatus')
    indexing_status_enum.create(op.get_bind(), checkfirst=True)

    # 2. Add indexing columns to file_metadata
    op.add_column('file_metadata', sa.Column('indexing_status', sa.Enum('pending', 'indexed', 'failed', 'dead_letter', name='indexingstatus'), server_default='pending', nullable=True))
    op.add_column('file_metadata', sa.Column('indexing_error', sa.Text(), nullable=True))
    op.add_column('file_metadata', sa.Column('indexing_attempts', sa.Integer(), server_default='0', nullable=True))

    # 3. Add pricing columns to ai_models
    op.add_column('ai_models', sa.Column('input_price_per_million', sa.Float(), nullable=True))
    op.add_column('ai_models', sa.Column('output_price_per_million', sa.Float(), nullable=True))

    # 4. Create infrastructure_costs table
    op.create_table(
        'infrastructure_costs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('date', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('service_name', sa.String(100), nullable=False),
        sa.Column('environment', sa.String(50), server_default='production'),
        sa.Column('resource_name', sa.String(255), nullable=True),
        sa.Column('cost_amount', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(10), server_default='USD'),
        sa.Column('cost_type', sa.String(50), server_default='variable'),
        sa.Column('client_name', sa.String(100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table('infrastructure_costs')
    op.drop_column('ai_models', 'output_price_per_million')
    op.drop_column('ai_models', 'input_price_per_million')
    op.drop_column('file_metadata', 'indexing_attempts')
    op.drop_column('file_metadata', 'indexing_error')
    op.drop_column('file_metadata', 'indexing_status')
    sa.Enum('pending', 'indexed', 'failed', 'dead_letter', name='indexingstatus').drop(op.get_bind(), checkfirst=True)
