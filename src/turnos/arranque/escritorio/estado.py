"""Tamaño de la ventana, recordado entre sesiones en un JSON (sin GSettings,
para no tener que compilar esquemas)."""

import json
from pathlib import Path

from gi.repository import GLib

POR_DEFECTO = {"ancho": 1280, "alto": 860, "maximizada": False}


def _ruta() -> Path:
    return Path(GLib.get_user_config_dir()) / "turnosMedicos" / "ventana.json"


def leer() -> dict:
    try:
        datos = json.loads(_ruta().read_text(encoding="utf-8"))
        return {
            "ancho": max(480, int(datos["ancho"])),
            "alto": max(360, int(datos["alto"])),
            "maximizada": bool(datos["maximizada"]),
        }
    except (OSError, ValueError, KeyError, TypeError):
        return dict(POR_DEFECTO)


def guardar(ancho: int, alto: int, maximizada: bool) -> None:
    ruta = _ruta()
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(
            json.dumps({"ancho": ancho, "alto": alto, "maximizada": maximizada}), encoding="utf-8"
        )
    except OSError:
        pass  # no es grave: la próxima vez se abre con el tamaño por defecto
