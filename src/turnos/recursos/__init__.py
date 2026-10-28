"""Datos que se distribuyen con la aplicación: calendarios de festivos y municipios."""

import json
import unicodedata
from dataclasses import dataclass
from datetime import date
from functools import cache
from importlib import resources

from turnos.dominio.calendario import AmbitoFestivo, Festivo


@dataclass(frozen=True)
class CalendarioFestivos:
    """Festivos precargados de un municipio para un año.

    `completo` es False cuando faltan festivos por publicar (p. ej. los locales).
    """

    calendario: str
    anio: int
    completo: bool
    festivos: tuple[Festivo, ...]
    pendiente: str = ""


# Festivos que trae la aplicación (nacionales, autonómicos y locales) del municipio por
# defecto. Otro municipio busca los suyos en las fuentes oficiales (Configuración).
CALENDARIO_PRECARGADO = "madrid"


def calendarios_festivos(calendario: str = CALENDARIO_PRECARGADO) -> list[CalendarioFestivos]:
    """Todos los años disponibles del calendario indicado, en orden."""
    carpeta = resources.files(__package__) / "festivos"
    calendarios = []
    for fichero in sorted(carpeta.iterdir(), key=lambda f: f.name):
        if not (fichero.name.startswith(f"{calendario}-") and fichero.name.endswith(".json")):
            continue
        datos = json.loads(fichero.read_text(encoding="utf-8"))
        calendarios.append(CalendarioFestivos(
            calendario=datos["calendario"],
            anio=datos["anio"],
            completo=datos["completo"],
            pendiente=datos.get("pendiente", ""),
            festivos=tuple(
                Festivo(date.fromisoformat(f["fecha"]), f["descripcion"], AmbitoFestivo(f["ambito"]))
                for f in datos["festivos"]
            ),
        ))
    return calendarios


# --- Municipios (INE) ----------------------------------------------------------------

MUNICIPIO_POR_DEFECTO = "28079"  # Madrid (sus festivos vienen precargados)


@dataclass(frozen=True)
class Municipio:
    ine: str  # código INE de 5 cifras: provincia (2) + municipio (3)
    nombre: str
    provincia: str
    ccaa: str  # código ISO 3166-2, p. ej. ES-MD
    ccaa_nombre: str


@cache
def municipios() -> dict[str, Municipio]:
    """Relación de municipios del INE (recursos/municipios.json), por código."""
    datos = json.loads((resources.files(__package__) / "municipios.json").read_text(encoding="utf-8"))
    comunidades = datos["comunidades"]
    return {
        ine: Municipio(ine, nombre, provincia, ccaa, comunidades[ccaa])
        for ine, nombre, provincia, ccaa in datos["municipios"]
    }


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto.casefold())
    return "".join(c for c in sin_tildes if not unicodedata.combining(c))


def buscar_municipios(texto: str, limite: int = 20) -> list[Municipio]:
    """Municipios cuyo nombre contiene `texto` (sin distinguir tildes ni mayúsculas);
    primero los que empiezan por él."""
    buscado = _normalizar(texto.strip())
    if not buscado:
        return []
    encontrados = [m for m in municipios().values() if buscado in _normalizar(m.nombre)]
    encontrados.sort(key=lambda m: (not _normalizar(m.nombre).startswith(buscado), _normalizar(m.nombre), m.provincia))
    return encontrados[:limite]
