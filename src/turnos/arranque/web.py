"""Modo web: `turnos`. Arranca el servidor y abre la interfaz en el navegador.

`turnos servidor …` es el modo servidor en la red local (ver `turnos.red.orden`).

Variables de entorno: TURNOS_PUERTO (8000; 0 = uno libre), TURNOS_SIN_NAVEGADOR,
TURNOS_SIN_TOKEN (solo para desarrollo y pruebas), TURNOS_DATOS.
"""

import os
import sys
import threading
import webbrowser

from turnos.arranque.servidor import preparar
from turnos.datos.bd import DatosMasNuevos


def main() -> None:
    if sys.argv[1:2] == ["servidor"]:
        from turnos.red.orden import main as servidor

        servidor(sys.argv[2:])
        return
    puerto = int(os.environ.get("TURNOS_PUERTO", "8000"))
    try:
        servidor = preparar(puerto=puerto, con_token=not os.environ.get("TURNOS_SIN_TOKEN"))
    except DatosMasNuevos as error:
        sys.exit(str(error))
    except OSError as error:
        sys.exit(f"No se puede usar el puerto {puerto} ({error.strerror}). Prueba con TURNOS_PUERTO=0.")
    print(f"turnosMedicos en {servidor.url}  (Ctrl+C para cerrar)", flush=True)
    if not os.environ.get("TURNOS_SIN_NAVEGADOR"):
        threading.Timer(1.0, webbrowser.open, [servidor.url]).start()
    servidor.ejecutar()


if __name__ == "__main__":
    main()
