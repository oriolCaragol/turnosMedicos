"""Cuánto tarda el motor en este equipo (diseño del modo servidor, 12; fase 5).

Con los datos del servidor (en una copia: no se cambia nada) o, si aún no hay, con el
equipo de ejemplo del motor (12 médicos). Para comprobar que una Raspberry Pi basta.
"""

import platform
import resource
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from turnos.datos.bd import copia_de_seguridad, inicializar
from turnos.datos.tablas import Medico


@dataclass
class Medida:
    origen: str
    medicos: int
    segundos: float
    memoria_mb: float

    def informe(self) -> str:
        lineas = [
            f"Equipo: {platform.machine()}, {platform.python_implementation()} {platform.python_version()}",
            f"Datos: {self.origen} ({self.medicos} médicos)",
            f"Generar un mes: {self.segundos:.2f} s; memoria máxima del proceso: {self.memoria_mb:.0f} MB",
        ]
        if self.segundos > 60:
            lineas.append("Aviso: tarda más de un minuto; se puede usar, pero conviene un equipo más rápido.")
        return "\n".join(lineas)


def _memoria_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # en Linux, KiB


def _hay_medicos(datos: Path) -> bool:
    import sqlite3
    from contextlib import closing

    try:
        with closing(sqlite3.connect(f"file:{datos}?mode=ro", uri=True)) as conexion:
            return conexion.execute("SELECT count(*) FROM medico WHERE activo").fetchone()[0] > 0
    except sqlite3.Error:
        return False


def medir(datos: Path | None, anio: int, mes: int) -> Medida:
    if datos is not None and datos.exists() and _hay_medicos(datos):
        with tempfile.TemporaryDirectory() as carpeta:
            copia = copia_de_seguridad(datos, Path(carpeta) / "medir.sqlite")
            motor = inicializar(copia)
            try:
                from turnos.servicios.periodos import generar_mes

                with Session(motor) as sesion, sesion.begin():
                    medicos = sesion.scalar(select(func.count()).select_from(Medico).where(Medico.activo))
                    inicio = time.perf_counter()
                    generar_mes(sesion, anio, mes)
                    segundos = time.perf_counter() - inicio
            finally:
                motor.dispose()
        return Medida(f"copia de {datos}", medicos, segundos, _memoria_mb())
    from turnos.motor.ejemplo import problema_de_ejemplo
    from turnos.motor.modelo_cpsat import generar

    problema = problema_de_ejemplo(anio, mes)
    inicio = time.perf_counter()
    generar(problema)
    return Medida("equipo de ejemplo", len(problema.medicos), time.perf_counter() - inicio, _memoria_mb())
