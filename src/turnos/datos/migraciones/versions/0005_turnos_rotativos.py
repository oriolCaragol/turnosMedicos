"""Turnos rotativos entre grupos de médicos

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('rotacion',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(), nullable=False),
    sa.Column('desde', sa.Date(), nullable=False),
    sa.Column('activa', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('rotacion_hueco',
    sa.Column('rotacion_id', sa.Integer(), nullable=False),
    sa.Column('dia_semana', sa.Integer(), nullable=False),
    sa.Column('turno', sa.Enum('MANANA', 'TARDE', name='turno', native_enum=False, length=20), nullable=False),
    sa.CheckConstraint('dia_semana BETWEEN 0 AND 4', name='ck_dia_semana'),
    sa.ForeignKeyConstraint(['rotacion_id'], ['rotacion.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('rotacion_id', 'dia_semana', 'turno')
    )
    op.create_table('rotacion_medico',
    sa.Column('rotacion_id', sa.Integer(), nullable=False),
    sa.Column('medico_id', sa.Integer(), nullable=False),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['medico_id'], ['medico.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['rotacion_id'], ['rotacion.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('rotacion_id', 'medico_id')
    )


def downgrade() -> None:
    op.drop_table('rotacion_medico')
    op.drop_table('rotacion_hueco')
    op.drop_table('rotacion')
