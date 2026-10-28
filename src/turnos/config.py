"""Configuración de la aplicación."""

import os
from pathlib import Path


def _en_windows() -> bool:
    return os.name == "nt"


def ruta_datos() -> Path:
    """Fichero SQLite de datos (diseño, 9; diseño del modo escritorio, 8.1).

    Por defecto `~/.local/share/turnosMedicos/turnos.sqlite`, la misma en el modo
    web y en el de escritorio (Flatpak), para que los dos usen los mismos datos. En
    Windows, `%LOCALAPPDATA%\\TurnosMedicos\\turnos.sqlite`.
    Se puede cambiar con la variable de entorno TURNOS_DATOS.
    """
    if ruta := os.environ.get("TURNOS_DATOS"):
        return Path(ruta)
    if _en_windows():
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "TurnosMedicos" / "turnos.sqlite"
    if os.environ.get("FLATPAK_ID"):
        # Dentro de Flatpak, XDG_DATA_HOME apunta a ~/.var/app/<id>/data: se usa la
        # carpeta real del usuario, a la que el Flatpak tiene acceso.
        base = Path.home() / ".local" / "share"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "turnosMedicos" / "turnos.sqlite"


def carpeta_configuracion() -> Path:
    """Configuración de las aplicaciones (conexión, ventana): `~/.config/turnosMedicos`
    (en Flatpak, la de la aplicación; en Windows, `%APPDATA%\\TurnosMedicos`)."""
    if _en_windows():
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "TurnosMedicos"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "turnosMedicos"
