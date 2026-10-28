"""Solicitudes de los médicos (modo servidor, fase 4)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('solicitud',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('estado', sa.String(length=20), nullable=False),
    sa.Column('medico_id', sa.Integer(), nullable=False),
    sa.Column('companero_id', sa.Integer(), nullable=True),
    sa.Column('autor_id', sa.Integer(), nullable=True),
    sa.Column('propuesta', sa.String(), nullable=False),
    sa.Column('comentario', sa.String(), nullable=False),
    sa.Column('respuesta_companero', sa.String(), nullable=True),
    sa.Column('creada', sa.DateTime(), nullable=False),
    sa.Column('resuelta_por_id', sa.Integer(), nullable=True),
    sa.Column('resuelta_en', sa.DateTime(), nullable=True),
    sa.Column('comentario_resolucion', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['medico_id'], ['medico.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['companero_id'], ['medico.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['autor_id'], ['usuario.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['resuelta_por_id'], ['usuario.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('solicitud')
