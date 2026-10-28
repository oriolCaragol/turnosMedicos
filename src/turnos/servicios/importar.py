"""Importar una copia de los datos (el fichero SQLite que se descarga en
Configuración): sustituye todos los datos actuales."""

import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import DatabaseError

from turnos.datos.bd import DatosMasNuevos, copia_de_seguridad, crear_motor, migrar

CABECERA_SQLITE = b"SQLite format 3\x00"


class CopiaNoValida(ValueError):
    """El fichero no es una copia que se pueda importar; no se ha cambiado nada."""


@dataclass(frozen=True)
class Resultado:
    medicos: int
    meses: int
    copia_anterior: str


def importar(motor: Engine, ruta: Path, contenido: bytes, *, conservar_cuentas: bool = False) -> Resultado:
    """Comprueba la copia, la actualiza a la versión actual si es de una anterior, guarda
    una copia de los datos actuales y los sustituye por los de la copia.

    Con `conservar_cuentas` (modo servidor), los usuarios y sesiones actuales se mantienen:
    importar los datos del modo personal no debe dejar a nadie sin poder entrar."""
    if not contenido.startswith(CABECERA_SQLITE):
        raise CopiaNoValida("El fichero no es una copia de turnosMedicos (no es una base de datos SQLite).")
    with tempfile.TemporaryDirectory() as carpeta:
        importada = Path(carpeta) / "importada.sqlite"
        importada.write_bytes(contenido)
        medicos, meses = _preparar(importada)
        if conservar_cuentas:
            _pasar_cuentas(ruta, importada)
        copia = copia_de_seguridad(
            ruta, ruta.with_name(f"{ruta.stem}-antes-de-importar-{datetime.now():%Y%m%d-%H%M%S}.sqlite.bak")
        )
        motor.dispose()  # sin conexiones abiertas mientras se sustituye el contenido
        with closing(sqlite3.connect(importada)) as origen, closing(sqlite3.connect(ruta)) as destino:
            # Con WAL (modo servidor), volcar encima no sustituye bien los datos: antes se
            # vuelve al diario clásico. Las conexiones nuevas reactivan WAL (datos/bd.py).
            destino.execute("PRAGMA journal_mode = DELETE")
            origen.backup(destino)
    return Resultado(medicos=medicos, meses=meses, copia_anterior=str(copia))


def _pasar_cuentas(actual: Path, importada: Path) -> None:
    """Copia usuarios y sesiones de los datos actuales a la copia importada (las dos ya
    con el mismo esquema). Cada cuenta de médico se vuelve a vincular por el código del
    médico; si en la copia no está, queda sin vincular."""
    with closing(sqlite3.connect(actual)) as origen, closing(sqlite3.connect(importada)) as destino:
        codigos = dict(origen.execute("SELECT id, codigo FROM medico"))
        ids = {codigo: id_ for id_, codigo in destino.execute("SELECT id, codigo FROM medico")}
        columnas = [c[1] for c in origen.execute("PRAGMA table_info(usuario)")]
        usuarios = [dict(zip(columnas, fila)) for fila in origen.execute("SELECT * FROM usuario")]
        sesiones = origen.execute("SELECT * FROM sesion").fetchall()
        with destino:
            destino.execute("DELETE FROM sesion")
            destino.execute("DELETE FROM usuario")
            for us in usuarios:
                us["medico_id"] = ids.get(codigos.get(us["medico_id"]))
                destino.execute(
                    f"INSERT INTO usuario ({', '.join(columnas)}) VALUES ({', '.join('?' * len(columnas))})",
                    [us[c] for c in columnas],
                )
            if sesiones:
                destino.executemany(f"INSERT INTO sesion VALUES ({', '.join('?' * len(sesiones[0]))})", sesiones)


def _preparar(ruta: Path) -> tuple[int, int]:
    """Valida y migra la copia en su sitio temporal. Devuelve (médicos, meses)."""
    motor = crear_motor(ruta)
    try:
        with motor.connect() as conexion:
            if conexion.exec_driver_sql("PRAGMA integrity_check").scalar() != "ok":
                raise CopiaNoValida("La copia está dañada.")
            tablas = set(inspect(conexion).get_table_names())
        if not {"alembic_version", "medico", "festivo"} <= tablas:
            raise CopiaNoValida("El fichero es una base de datos, pero no una copia de turnosMedicos.")
        migrar(motor, ruta)
        with motor.connect() as conexion:
            medicos = conexion.execute(text("SELECT count(*) FROM medico")).scalar()
            meses = conexion.execute(text("SELECT count(*) FROM periodo")).scalar()
        return medicos, meses
    except DatosMasNuevos as error:
        raise CopiaNoValida(
            "La copia es de una versión más reciente de turnosMedicos. Actualiza la aplicación para importarla."
        ) from error
    except (sqlite3.DatabaseError, DatabaseError) as error:
        raise CopiaNoValida(f"La copia está dañada ({error}).") from error
    finally:
        motor.dispose()
