"""Usuarios y sesiones (modo servidor, fase 2)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('usuario',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=40), nullable=False),
    sa.Column('nombre_visible', sa.String(length=80), nullable=False),
    sa.Column('hash_contrasena', sa.String(), nullable=False),
    sa.Column('rol', sa.String(length=20), nullable=False),
    sa.Column('medico_id', sa.Integer(), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('debe_cambiar', sa.Boolean(), nullable=False),
    sa.Column('creado', sa.DateTime(), nullable=False),
    sa.CheckConstraint("rol IN ('ADMINISTRADOR', 'PLANIFICADOR', 'MEDICO')", name='ck_rol'),
    sa.ForeignKeyConstraint(['medico_id'], ['medico.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nombre')
    )
    op.create_table('sesion',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('hash_token', sa.String(length=64), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('dispositivo', sa.String(length=200), nullable=False),
    sa.Column('creada', sa.DateTime(), nullable=False),
    sa.Column('ultimo_uso', sa.DateTime(), nullable=False),
    sa.Column('caduca', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('hash_token')
    )


def downgrade() -> None:
    op.drop_table('sesion')
    op.drop_table('usuario')
