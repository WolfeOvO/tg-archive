"""Add ArchiveStats table for deduplicated upload tracking

Revision ID: 001
Revises: 
Create Date: 2026-09-13 05:30:00
"""
from alembic import op
import sqlalchemy as sa

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'archive_stats',
        sa.Column('channel', sa.String(200), primary_key=True),
        sa.Column('bytes_uploaded', sa.Integer, nullable=False, default=0),
        sa.Column('run_transfer_bytes', sa.Integer, nullable=False, default=0),
        sa.Column('media_total_bytes', sa.Integer, nullable=False, default=0),
        sa.Column('messages_total', sa.Integer, nullable=False, default=0),
        sa.Column('messages_done', sa.Integer, nullable=False, default=0),
        sa.Column('media_total', sa.Integer, nullable=False, default=0),
        sa.Column('media_uploaded', sa.Integer, nullable=False, default=0),
        sa.Column('started_at', sa.Float, nullable=True),
        sa.Column('finished_at', sa.Float, nullable=True),
        sa.Column('updated_at', sa.Float, nullable=False, server_default=sa.text('(unixepoch())')),
    )


def downgrade():
    op.drop_table('archive_stats')
