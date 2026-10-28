"""esquema inicial

Revision ID: 0001
Revises: 
Create Date: 2026-10-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('carga_festivos',
    sa.Column('anio', sa.Integer(), nullable=False),
    sa.Column('calendario', sa.String(), nullable=False),
    sa.Column('completo', sa.Boolean(), nullable=False),
    sa.Column('cargado_en', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('anio')
    )
    op.create_table('cobertura_fecha',
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('mitad', sa.Enum('M1', 'M2', 'T1', 'T2', name='mitad', native_enum=False, length=20), nullable=False),
    sa.Column('minimo', sa.Integer(), nullable=False),
    sa.Column('maximo', sa.Integer(), nullable=False),
    sa.CheckConstraint('0 <= minimo AND minimo <= maximo', name='ck_cobertura'),
    sa.PrimaryKeyConstraint('fecha', 'mitad')
    )
    op.create_table('cobertura_semanal',
    sa.Column('dia_semana', sa.Integer(), nullable=False),
    sa.Column('mitad', sa.Enum('M1', 'M2', 'T1', 'T2', name='mitad', native_enum=False, length=20), nullable=False),
    sa.Column('minimo', sa.Integer(), nullable=False),
    sa.Column('maximo', sa.Integer(), nullable=False),
    sa.CheckConstraint('0 <= minimo AND minimo <= maximo', name='ck_cobertura'),
    sa.CheckConstraint('dia_semana BETWEEN 0 AND 4', name='ck_dia_semana'),
    sa.PrimaryKeyConstraint('dia_semana', 'mitad')
    )
    op.create_table('festivo',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('descripcion', sa.String(), nullable=False),
    sa.Column('ambito', sa.Enum('NACIONAL', 'AUTONOMICO', 'LOCAL', 'OTRO', name='ambitofestivo', native_enum=False, length=20), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('fecha')
    )
    op.create_table('horario_turno',
    sa.Column('turno', sa.Enum('MANANA', 'TARDE', name='turno', native_enum=False, length=20), nullable=False),
    sa.Column('inicio', sa.Time(), nullable=False),
    sa.Column('corte', sa.Time(), nullable=False),
    sa.Column('fin', sa.Time(), nullable=False),
    sa.CheckConstraint('inicio < corte AND corte < fin', name='ck_horas'),
    sa.PrimaryKeyConstraint('turno')
    )
    op.create_table('medico',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(), nullable=False),
    sa.Column('codigo', sa.String(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('codigo')
    )
    op.create_table('periodo',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('anio', sa.Integer(), nullable=False),
    sa.Column('mes', sa.Integer(), nullable=False),
    sa.Column('publicado_en', sa.DateTime(), nullable=True),
    sa.CheckConstraint('mes BETWEEN 1 AND 12', name='ck_mes'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('anio', 'mes')
    )
    op.create_table('asignacion',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('periodo_id', sa.Integer(), nullable=False),
    sa.Column('medico_id', sa.Integer(), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('mitad', sa.Enum('M1', 'M2', 'T1', 'T2', name='mitad', native_enum=False, length=20), nullable=False),
    sa.Column('origen', sa.Enum('GENERADOR', 'FIJO', 'MANUAL', name='origenasignacion', native_enum=False, length=20), nullable=False),
    sa.Column('bloqueada', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['medico_id'], ['medico.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['periodo_id'], ['periodo.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('periodo_id', 'medico_id', 'fecha', 'mitad')
    )
    op.create_table('ausencia',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('medico_id', sa.Integer(), nullable=False),
    sa.Column('desde', sa.Date(), nullable=False),
    sa.Column('hasta', sa.Date(), nullable=False),
    sa.Column('turno', sa.Enum('MANANA', 'TARDE', name='turno', native_enum=False, length=20), nullable=True),
    sa.CheckConstraint('desde <= hasta', name='ck_fechas'),
    sa.ForeignKeyConstraint(['medico_id'], ['medico.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('aviso',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('periodo_id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.Enum('CAUSA', 'INCUMPLIMIENTO', name='tipoaviso', native_enum=False, length=20), nullable=False),
    sa.Column('mensaje', sa.String(), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=True),
    sa.Column('medico_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['medico_id'], ['medico.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['periodo_id'], ['periodo.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('carga',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('medico_id', sa.Integer(), nullable=False),
    sa.Column('vigente_desde', sa.Date(), nullable=False),
    sa.Column('turno', sa.Enum('MANANA', 'TARDE', name='turno', native_enum=False, length=20), nullable=True),
    sa.Column('minimo', sa.Integer(), nullable=False),
    sa.Column('maximo', sa.Integer(), nullable=True),
    sa.CheckConstraint('0 <= minimo AND (maximo IS NULL OR minimo <= maximo)', name='ck_carga'),
    sa.CheckConstraint('turno IS NOT NULL OR maximo IS NOT NULL', name='ck_carga_total'),
    sa.ForeignKeyConstraint(['medico_id'], ['medico.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('medico_id', 'vigente_desde', 'turno')
    )
    op.create_table('carga_ajustada',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('periodo_id', sa.Integer(), nullable=False),
    sa.Column('medico_id', sa.Integer(), nullable=False),
    sa.Column('turno', sa.Enum('MANANA', 'TARDE', name='turno', native_enum=False, length=20), nullable=True),
    sa.Column('minimo_calc', sa.Integer(), nullable=False),
    sa.Column('maximo_calc', sa.Integer(), nullable=False),
    sa.Column('minimo_manual', sa.Integer(), nullable=True),
    sa.Column('maximo_manual', sa.Integer(), nullable=True),
    sa.Column('objetivo', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['medico_id'], ['medico.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['periodo_id'], ['periodo.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('periodo_id', 'medico_id', 'turno')
    )
    op.create_table('elegibilidad',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('medico_id', sa.Integer(), nullable=False),
    sa.Column('vigente_desde', sa.Date(), nullable=False),
    sa.Column('dia_semana', sa.Integer(), nullable=False),
    sa.Column('turno', sa.Enum('MANANA', 'TARDE', name='turno', native_enum=False, length=20), nullable=False),
    sa.Column('valor', sa.Enum('FIJO', 'DISPONIBLE', 'NO_DISPONIBLE', name='elegibilidad', native_enum=False, length=20), nullable=False),
    sa.CheckConstraint('dia_semana BETWEEN 0 AND 4', name='ck_dia_semana'),
    sa.ForeignKeyConstraint(['medico_id'], ['medico.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('medico_id', 'vigente_desde', 'dia_semana', 'turno')
    )
    op.create_table('jornada_semanal',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('medico_id', sa.Integer(), nullable=False),
    sa.Column('vigente_desde', sa.Date(), nullable=False),
    sa.Column('dia_semana', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.Enum('MANANA_MAS_MEDIA', 'TARDE_MAS_MEDIA', 'DOBLE', name='tipojornada', native_enum=False, length=20), nullable=True),
    sa.CheckConstraint('dia_semana BETWEEN 0 AND 4', name='ck_dia_semana'),
    sa.ForeignKeyConstraint(['medico_id'], ['medico.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('medico_id', 'vigente_desde', 'dia_semana')
    )
    op.create_table('preferencia',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('medico_id', sa.Integer(), nullable=False),
    sa.Column('dia_semana', sa.Integer(), nullable=False),
    sa.Column('turno', sa.Enum('MANANA', 'TARDE', name='turno', native_enum=False, length=20), nullable=False),
    sa.Column('valor', sa.Enum('PREFIERE', 'EVITA', name='preferencia', native_enum=False, length=20), nullable=False),
    sa.CheckConstraint('dia_semana BETWEEN 0 AND 4', name='ck_dia_semana'),
    sa.ForeignKeyConstraint(['medico_id'], ['medico.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('medico_id', 'dia_semana', 'turno')
    )
    op.create_table('veto',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('periodo_id', sa.Integer(), nullable=False),
    sa.Column('medico_id', sa.Integer(), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('turno', sa.Enum('MANANA', 'TARDE', name='turno', native_enum=False, length=20), nullable=False),
    sa.ForeignKeyConstraint(['medico_id'], ['medico.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['periodo_id'], ['periodo.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('periodo_id', 'medico_id', 'fecha', 'turno')
    )


def downgrade() -> None:
    op.drop_table('veto')
    op.drop_table('preferencia')
    op.drop_table('jornada_semanal')
    op.drop_table('elegibilidad')
    op.drop_table('carga_ajustada')
    op.drop_table('carga')
    op.drop_table('aviso')
    op.drop_table('ausencia')
    op.drop_table('asignacion')
    op.drop_table('periodo')
    op.drop_table('medico')
    op.drop_table('horario_turno')
    op.drop_table('festivo')
    op.drop_table('cobertura_semanal')
    op.drop_table('cobertura_fecha')
    op.drop_table('carga_festivos')
