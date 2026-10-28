"""Búsqueda de los festivos oficiales de un municipio en fuentes en línea.

- festivos.io: recopila el BOE, los boletines autonómicos y los datos abiertos de
  cada comunidad para todos los municipios, con la referencia oficial de cada
  festivo (CC BY 4.0). Es la fuente principal.
- Comunidad de Madrid, datos abiertos («Festivos regionales y locales año en
  curso»): fuente oficial directa, solo del año en curso. Se usa en municipios de
  Madrid para los festivos locales que falten en la principal.
"""

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date

from turnos import __version__
from turnos.dominio.calendario import AmbitoFestivo
from turnos.recursos import Municipio

# Las direcciones se pueden cambiar (las pruebas de flujo completo usan ficheros locales).
FESTIVOS_IO = os.environ.get("TURNOS_FUENTE_FESTIVOS_IO", "https://festivos.io/v1/{anio}/municipio/{ine}.json")
MADRID_LOCALES = os.environ.get(
    "TURNOS_FUENTE_MADRID",
    "https://datos.comunidad.madrid/dataset/f160eb6c-6715-471e-9bc0-38497aae950f/resource/"
    "db6a3cb0-5504-4db8-9fe7-e42af1ae329b/download/festivos_locales.json",
)
MADRID_DATASET = "https://datos.comunidad.madrid/dataset/f160eb6c-6715-471e-9bc0-38497aae950f"
NIVELES = {"national": AmbitoFestivo.NACIONAL, "regional": AmbitoFestivo.AUTONOMICO, "local": AmbitoFestivo.LOCAL}


class SinConexion(RuntimeError):
    """Ninguna fuente ha respondido."""


@dataclass(frozen=True)
class FestivoOficial:
    fecha: date
    descripcion: str
    ambito: AmbitoFestivo
    fuente: str  # referencia oficial, p. ej. BOE-A-2025-21667
    url: str | None = None


@dataclass
class Busqueda:
    festivos: list[FestivoOficial] = field(default_factory=list)
    fuentes: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def locales(self) -> int:
        return sum(f.ambito is AmbitoFestivo.LOCAL for f in self.festivos)


def descargar_json(url: str):
    """JSON de una dirección; None si no existe (404). Las pruebas la sustituyen."""
    peticion = urllib.request.Request(url, headers={"User-Agent": f"turnosMedicos/{__version__}"})
    try:
        with urllib.request.urlopen(peticion, timeout=20) as respuesta:
            return json.load(respuesta)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise
    except urllib.error.URLError as error:
        if isinstance(error.reason, FileNotFoundError):  # fuente local (pruebas) sin ese fichero
            return None
        raise


def buscar(anio: int, municipio: Municipio) -> Busqueda:
    resultado = Busqueda()
    errores = []
    try:
        _de_festivos_io(anio, municipio, resultado)
    except (OSError, ValueError, KeyError) as error:
        errores.append(f"festivos.io: {_motivo(error)}")
    if municipio.ccaa == "ES-MD" and resultado.locales < 2:
        try:
            _locales_de_madrid(anio, municipio, resultado)
        except (OSError, ValueError, KeyError) as error:
            errores.append(f"Comunidad de Madrid: {_motivo(error)}")
    if not resultado.fuentes and errores:
        raise SinConexion("No se ha podido consultar ninguna fuente (" + "; ".join(errores) + ").")
    resultado.avisos += [f"No se ha podido consultar {e}" for e in errores]
    if not resultado.festivos:
        resultado.avisos.append(f"Aún no hay festivos publicados de {anio} para {municipio.nombre}.")
    elif resultado.locales < 2:
        resultado.avisos.append(
            f"Faltan festivos locales de {municipio.nombre} en {anio} (normalmente son dos): "
            "puede que aún no se hayan publicado."
        )
    resultado.festivos.sort(key=lambda f: f.fecha)
    return resultado


def _de_festivos_io(anio: int, municipio: Municipio, resultado: Busqueda) -> None:
    datos = descargar_json(FESTIVOS_IO.format(anio=anio, ine=municipio.ine))
    if datos is None:
        return
    resultado.fuentes.append(f"festivos.io ({datos.get('attribution', 'CC BY 4.0')})")
    for f in datos["holidays"]:
        fecha = date.fromisoformat(f["date"])
        if fecha.year != anio or any(x.fecha == fecha for x in resultado.festivos):
            continue
        fuente = f.get("source") or {}
        resultado.festivos.append(FestivoOficial(
            fecha=fecha,
            descripcion=f["name"].get("es") or next(iter(f["name"].values())),
            ambito=NIVELES.get(f.get("level"), AmbitoFestivo.OTRO),
            fuente=fuente.get("ref") or "festivos.io",
            url=fuente.get("url"),
        ))


def _locales_de_madrid(anio: int, municipio: Municipio, resultado: Busqueda) -> None:
    datos = descargar_json(MADRID_LOCALES)
    if datos is None:
        return
    filas = [
        f for f in datos["data"]
        if f["municipio_codigo"] == municipio.ine[2:] and f.get("entidad_codigo", "00") == "00" and f["año"] == str(anio)
    ]
    resultado.fuentes.append("Comunidad de Madrid, datos abiertos (CC BY)")
    for f in filas:
        fecha = date.fromisoformat(f["fecha_festivo"])
        if not any(x.fecha == fecha for x in resultado.festivos):
            resultado.festivos.append(FestivoOficial(
                fecha, "Fiesta local", AmbitoFestivo.LOCAL,
                "Comunidad de Madrid — Festivos locales (datos abiertos)", MADRID_DATASET,
            ))


def _motivo(error: Exception) -> str:
    if isinstance(error, urllib.error.URLError) and not isinstance(error, urllib.error.HTTPError):
        return "sin conexión a internet o la fuente no responde"
    if isinstance(error, urllib.error.HTTPError):
        return f"error {error.code}"
    if isinstance(error, TimeoutError):
        return "no responde"
    return "respuesta con un formato inesperado"
