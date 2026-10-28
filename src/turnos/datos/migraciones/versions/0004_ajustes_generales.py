"""Ajustes generales de la aplicación (tabla ajuste)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('ajuste',
    sa.Column('clave', sa.String(), nullable=False),
    sa.Column('valor', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('clave')
    )


def downgrade() -> None:
    op.drop_table('ajuste')
