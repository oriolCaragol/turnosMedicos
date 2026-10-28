"""Configuración del modo servidor: `servidor.toml` (diseño del modo servidor, 10.1)."""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

RUTAS_CONFIGURACION = (Path("/etc/turnos/servidor.toml"),)


def _carpeta_usuario() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "turnosMedicos"


def _datos_por_defecto() -> Path:
    # Aparte de los del modo personal: los dos modos no deben usar los mismos datos a la vez (D-S7).
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "turnosMedicos" / "servidor" / "turnos.sqlite"


class ErrorConfiguracion(ValueError):
    pass


@dataclass
class ConfigServidor:
    direccion: str = "0.0.0.0"
    puerto: int = 8443
    nombre: str = "turnos"  # se anuncia como turnos.local
    datos: Path = field(default_factory=_datos_por_defecto)
    copias: Path | None = None  # por defecto, «copias» junto a los datos
    conservar_copias: int = 14
    https: bool = True
    duracion_sesion_dias: int = 30
    anunciar: bool = True  # mDNS
    origen: Path | None = None  # fichero del que se ha leído

    def __post_init__(self) -> None:
        self.datos = Path(self.datos).expanduser()
        self.copias = Path(self.copias).expanduser() if self.copias else self.datos.parent / "copias"

    @property
    def certificados(self) -> Path:
        return self.datos.parent / "certificados"


def buscar_configuracion() -> Path | None:
    for ruta in (*RUTAS_CONFIGURACION, _carpeta_usuario() / "servidor.toml"):
        if ruta.is_file():
            return ruta
    return None


def leer_configuracion(ruta: Path | None = None) -> ConfigServidor:
    """Lee el fichero indicado o el primero que exista (/etc/turnos, ~/.config/turnosMedicos).
    Sin fichero, los valores por defecto."""
    ruta = ruta or buscar_configuracion()
    if ruta is None:
        return ConfigServidor()
    try:
        datos = tomllib.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ErrorConfiguracion(f"No se puede leer {ruta}: {error}") from error
    red, almacen, seguridad = datos.get("red", {}), datos.get("datos", {}), datos.get("seguridad", {})
    try:
        return ConfigServidor(
            direccion=str(red.get("direccion", "0.0.0.0")),
            puerto=int(red.get("puerto", 8443)),
            nombre=str(red.get("nombre", "turnos")),
            anunciar=bool(red.get("anunciar", True)),
            datos=Path(almacen["ruta"]) if "ruta" in almacen else _datos_por_defecto(),
            copias=Path(almacen["copias"]) if "copias" in almacen else None,
            conservar_copias=int(almacen.get("conservar_copias", 14)),
            https=bool(seguridad.get("https", True)),
            duracion_sesion_dias=int(seguridad.get("duracion_sesion_dias", 30)),
            origen=ruta,
        )
    except (TypeError, ValueError) as error:
        raise ErrorConfiguracion(f"Valor no válido en {ruta}: {error}") from error


EJEMPLO = """\
# Configuración del servidor de turnos médicos (docs/diseno-servidor.md, 10.1)
[red]
direccion = "0.0.0.0"     # todas las interfaces de la red local
puerto = 8443
nombre = "turnos"         # se anuncia como turnos.local
anunciar = true           # mDNS: las aplicaciones lo encuentran solas

[datos]
# ruta = "/var/lib/turnos/turnos.sqlite"
# copias = "/var/lib/turnos/copias"
conservar_copias = 14     # días

[seguridad]
https = true
duracion_sesion_dias = 30
"""
