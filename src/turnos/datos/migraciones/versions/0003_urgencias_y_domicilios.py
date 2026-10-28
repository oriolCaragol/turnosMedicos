"""Urgencias y domicilios de cada tarde (tabla rol_tarde)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('rol_tarde',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('periodo_id', sa.Integer(), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('rol', sa.Enum('URGENCIAS', 'DOMICILIOS', name='rol', native_enum=False, length=20), nullable=False),
    sa.Column('medico_id', sa.Integer(), nullable=False),
    sa.Column('manual', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['medico_id'], ['medico.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['periodo_id'], ['periodo.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('periodo_id', 'fecha', 'rol')
    )


def downgrade() -> None:
    op.drop_table('rol_tarde')
