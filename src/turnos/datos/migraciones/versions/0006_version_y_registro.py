"""Versión de cada mes y registro de cambios (modo servidor, fase 1)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('periodo') as tabla:
        tabla.add_column(sa.Column('version', sa.Integer(), nullable=False, server_default='0'))
    op.create_table('registro_cambio',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('momento', sa.DateTime(), nullable=False),
    sa.Column('usuario', sa.String(), nullable=True),
    sa.Column('accion', sa.String(), nullable=False),
    sa.Column('ruta', sa.String(), nullable=False),
    sa.Column('anio', sa.Integer(), nullable=True),
    sa.Column('mes', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('registro_cambio')
    with op.batch_alter_table('periodo') as tabla:
        tabla.drop_column('version')
