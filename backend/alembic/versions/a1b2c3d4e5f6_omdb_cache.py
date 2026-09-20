"""omdb cache

Revision ID: a1b2c3d4e5f6
Revises: 802b6b559b6b
Create Date: 2026-09-20 16:48:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '802b6b559b6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('omdb_cache',
    sa.Column('imdb_id', sa.String(length=16), nullable=False),
    sa.Column('data', sa.Text(), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('imdb_id')
    )
    op.create_index('ix_omdb_cache_fetched_at', 'omdb_cache', ['fetched_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_omdb_cache_fetched_at', table_name='omdb_cache')
    op.drop_table('omdb_cache')
