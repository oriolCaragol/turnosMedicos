"""Creación, migración y datos iniciales de la base de datos."""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, time
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session

from turnos.dominio.calendario import AmbitoFestivo
from turnos.dominio.modelos import Turno
from turnos.datos.tablas import Ajuste, CargaFestivos, Festivo, HorarioTurno
from turnos.recursos import CALENDARIO_PRECARGADO, MUNICIPIO_POR_DEFECTO, calendarios_festivos

MIGRACIONES = Path(__file__).parent / "migraciones"


def crear_motor(ruta: Path, wal: bool = False) -> Engine:
    """`wal`: modo WAL de SQLite, para el modo servidor (varios clientes leyendo
    mientras otro escribe). No se usa en el modo personal: con WAL, los últimos
    cambios viven un tiempo en `turnos.sqlite-wal`, y copiar o sustituir a mano solo
    `turnos.sqlite` podría perderlos o estropear los datos."""
    motor = create_engine(f"sqlite:///{ruta}")

    @event.listens_for(motor, "connect")
    def _ajustes_conexion(conexion, _):
        conexion.execute("PRAGMA foreign_keys = ON")
        # Si el otro modo (web o escritorio) está escribiendo, esperar en vez de fallar.
        conexion.execute("PRAGMA busy_timeout = 5000")
        if wal:
            conexion.execute("PRAGMA journal_mode = WAL")

    return motor


class DatosMasNuevos(RuntimeError):
    """La base de datos es de una versión más reciente de la aplicación."""

    MENSAJE = (
        "Estos datos son de una versión más reciente de turnosMedicos. "
        "Actualiza la aplicación para abrirlos (no se ha modificado nada)."
    )

    def __init__(self) -> None:
        super().__init__(self.MENSAJE)


def _config_alembic() -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRACIONES))
    return config


def _hay_migraciones_pendientes(motor: Engine) -> bool:
    """True si hay que actualizar la base de datos. Si es de una versión más nueva
    (revisión desconocida para esta versión), lanza DatosMasNuevos sin tocar nada."""
    scripts = ScriptDirectory.from_config(_config_alembic())
    with motor.connect() as conexion:
        actual = MigrationContext.configure(conexion).get_current_revision()
    if actual is not None and actual not in {r.revision for r in scripts.walk_revisions()}:
        raise DatosMasNuevos()
    return actual != scripts.get_current_head()


def copia_de_seguridad(ruta: Path, destino: Path | None = None) -> Path:
    """Copia consistente del fichero SQLite (aunque esté en uso)."""
    destino = destino or ruta.with_name(f"{ruta.stem}-{datetime.now():%Y%m%d-%H%M%S}.sqlite.bak")
    # closing: «with» en sqlite3 confirma, pero no cierra la conexión.
    with closing(sqlite3.connect(ruta)) as origen, closing(sqlite3.connect(destino)) as copia:
        origen.backup(copia)
        # La copia hereda el modo WAL del original (modo servidor): se deja en el diario
        # clásico, para que sea un solo fichero completo que se pueda copiar o enviar.
        copia.execute("PRAGMA journal_mode = DELETE")
    return destino


def migrar(motor: Engine, ruta: Path) -> Path | None:
    """Aplica las migraciones pendientes. Si la base ya tenía datos, antes hace
    una copia de seguridad y devuelve su ruta."""
    if not _hay_migraciones_pendientes(motor):
        return None
    copia = None
    if ruta.exists() and ruta.stat().st_size > 0:
        copia = copia_de_seguridad(ruta)
    config = _config_alembic()
    with motor.begin() as conexion:
        config.attributes["conexion"] = conexion
        command.upgrade(config, "head")
    return copia


def cargar_festivos(sesion: Session, calendario: str = CALENDARIO_PRECARGADO) -> None:
    """Vuelca los festivos precargados de los años que aún no se habían cargado.

    Un año ya cargado no se vuelve a tocar, para respetar los cambios del
    planificador; la excepción es un año que estaba incompleto y ahora está
    completo, del que solo se añaden los festivos locales que faltaban.
    """
    ajuste = sesion.get(Ajuste, "municipio")
    if ajuste is not None and json.loads(ajuste.valor) != MUNICIPIO_POR_DEFECTO:
        return  # los precargados son los del municipio por defecto; otro busca los suyos en línea
    cargados = {c.anio: c for c in sesion.scalars(select(CargaFestivos))}
    fechas = set(sesion.scalars(select(Festivo.fecha)))
    for cal in calendarios_festivos(calendario):
        previo = cargados.get(cal.anio)
        if previo is None:
            nuevos = cal.festivos
            sesion.add(CargaFestivos(
                anio=cal.anio, calendario=cal.calendario, completo=cal.completo,
                cargado_en=datetime.now(),
            ))
        elif not previo.completo and cal.completo:
            nuevos = tuple(f for f in cal.festivos if f.ambito is AmbitoFestivo.LOCAL)
            previo.completo, previo.cargado_en = True, datetime.now()
        else:
            continue
        for f in nuevos:
            if f.fecha not in fechas:
                sesion.add(Festivo(fecha=f.fecha, descripcion=f.descripcion, ambito=f.ambito))
                fechas.add(f.fecha)


HORARIOS_POR_DEFECTO = {
    Turno.MANANA: (time(8), time(11, 30), time(15)),
    Turno.TARDE: (time(15), time(18, 30), time(22)),
}


def cargar_horarios(sesion: Session) -> None:
    """Horario inicial de los turnos (especificaciones, 4.1), si no hay ninguno."""
    if sesion.scalar(select(HorarioTurno).limit(1)) is None:
        for turno, (inicio, corte, fin) in HORARIOS_POR_DEFECTO.items():
            sesion.add(HorarioTurno(turno=turno, inicio=inicio, corte=corte, fin=fin))


def inicializar(ruta: Path, wal: bool = False) -> Engine:
    """Crea o actualiza la base de datos y carga los datos iniciales. Devuelve el motor."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    motor = crear_motor(ruta, wal)
    migrar(motor, ruta)
    with Session(motor) as sesion, sesion.begin():
        cargar_horarios(sesion)
        cargar_festivos(sesion)
    return motor
