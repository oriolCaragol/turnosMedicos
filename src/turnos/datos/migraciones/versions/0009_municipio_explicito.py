"""Municipio guardado en los datos que ya tenían festivos precargados (versión 2.14)

El municipio por defecto (y con él los festivos que trae la aplicación) pasa a ser
Madrid. Una base de datos que nunca guardó su municipio, pero cuyos festivos se
cargaron de otro calendario precargado, conserva ese municipio: se busca por el nombre
del calendario en la relación de municipios del INE y se guarda en los ajustes.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-25

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from turnos.recursos import CALENDARIO_PRECARGADO, municipios, _normalizar


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conexion = op.get_bind()
    if conexion.execute(sa.text("SELECT 1 FROM ajuste WHERE clave = 'municipio'")).first():
        return  # ya lo eligió el planificador
    anteriores = {
        c for (c,) in conexion.execute(sa.text("SELECT DISTINCT calendario FROM carga_festivos"))
        if c != CALENDARIO_PRECARGADO and not c.startswith("oficial:")
    }
    for calendario in sorted(anteriores):
        coincidencias = [m for m in municipios().values() if _normalizar(m.nombre) == _normalizar(calendario)]
        if len(coincidencias) == 1:
            conexion.execute(sa.text("INSERT INTO ajuste (clave, valor) VALUES ('municipio', :valor)"),
                             {"valor": json.dumps(coincidencias[0].ine)})
            return


def downgrade() -> None:
    pass  # el municipio guardado sigue siendo válido
