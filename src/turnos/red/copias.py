"""Copias de seguridad del servidor (diseño del modo servidor, 10.2): una al día,
conservando las de los últimos `conservar` días, y las que se piden a mano."""

import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from turnos.datos.bd import copia_de_seguridad

_DIARIA = re.compile(r"^turnos-(\d{8})\.sqlite$")


@dataclass(frozen=True)
class Copia:
    ruta: Path
    fecha: datetime
    tamano: int


def listar(carpeta: Path) -> list[Copia]:
    if not carpeta.is_dir():
        return []
    copias = [
        Copia(r, datetime.fromtimestamp(r.stat().st_mtime), r.stat().st_size)
        for r in carpeta.glob("turnos-*.sqlite")
    ]
    return sorted(copias, key=lambda c: c.fecha, reverse=True)


def copiar_ahora(datos: Path, carpeta: Path) -> Path:
    """Copia a mano (no se borra al limpiar las diarias)."""
    carpeta.mkdir(parents=True, exist_ok=True)
    return copia_de_seguridad(datos, carpeta / f"turnos-{datetime.now():%Y%m%d-%H%M%S}.sqlite")


def copia_diaria(datos: Path, carpeta: Path, conservar: int, hoy: date | None = None) -> Path | None:
    """Hace la copia de hoy si aún no está y borra las diarias de hace más de `conservar` días.
    Devuelve la copia hecha (None si ya estaba)."""
    hoy = hoy or date.today()
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"turnos-{hoy:%Y%m%d}.sqlite"
    hecha = None
    if not destino.exists():
        temporal = destino.with_suffix(".tmp")
        copia_de_seguridad(datos, temporal)
        temporal.replace(destino)
        hecha = destino
    limite = hoy - timedelta(days=conservar)
    for fichero in carpeta.iterdir():
        if (m := _DIARIA.match(fichero.name)) and datetime.strptime(m[1], "%Y%m%d").date() <= limite:
            fichero.unlink()
    return hecha


class Tareas:
    """Hilo que, cada hora, hace la copia diaria y llama a `cada_hora` (renovar el
    certificado si hace falta)."""

    def __init__(self, datos: Path, carpeta: Path, conservar: int, cada_hora: Callable[[], None] | None = None):
        self.datos, self.carpeta, self.conservar, self.cada_hora = datos, carpeta, conservar, cada_hora
        self._parar = threading.Event()
        self._hilo = threading.Thread(target=self._trabajar, name="tareas-servidor", daemon=True)

    def iniciar(self) -> None:
        self._hilo.start()

    def detener(self) -> None:
        self._parar.set()
        self._hilo.join(5)

    def _trabajar(self) -> None:
        while not self._parar.is_set():
            try:
                copia_diaria(self.datos, self.carpeta, self.conservar)
                if self.cada_hora:
                    self.cada_hora()
            except Exception as error:  # noqa: BLE001 — que no pare el servidor
                print(f"Aviso: tarea periódica fallida: {error}", flush=True)
            self._parar.wait(3600)
