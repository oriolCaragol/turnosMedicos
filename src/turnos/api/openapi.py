"""Escribe el esquema OpenAPI de la API, del que la interfaz genera sus tipos.

Uso: python -m turnos.api.openapi interfaz/openapi.json
"""

import json
import sys
from pathlib import Path

from sqlalchemy import create_engine

from turnos.api.app import crear_app
from turnos.api.rutas.servidor import EstadoServidor
from turnos.red.configuracion import ConfigServidor


def main() -> None:
    # El esquema no consulta la base de datos: basta un motor en memoria. Se genera en
    # el modo servidor, que tiene todas las rutas (las de cuentas y servidor, además).
    estado = EstadoServidor(ConfigServidor(datos=Path("turnos.sqlite"), https=False), None)
    app = crear_app(create_engine("sqlite://"), interfaz=None, servidor=estado)
    texto = json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n"
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            f.write(texto)
    else:
        sys.stdout.write(texto)


if __name__ == "__main__":
    main()
