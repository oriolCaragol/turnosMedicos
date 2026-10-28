"""Turnos médicos en Windows: `TurnosMedicos.exe` (docs/windows.md).

El núcleo y los datos van en el propio equipo, como el modo web: el servidor interno
arranca en 127.0.0.1 y la interfaz se abre en el navegador predeterminado. Una
ventana pequeña (Tkinter) pregunta dónde trabajar (en este equipo o en un servidor
de la red), vuelve a abrir el navegador y cierra la aplicación.

    TurnosMedicos.exe                    normal
    TurnosMedicos.exe --prueba FICHERO   autoprueba sin ventana (para la compilación)
"""

import sys
from pathlib import Path


def _salida_a_fichero() -> None:
    """Sin consola (ejecutable con ventana), sys.stdout y sys.stderr son None y uvicorn
    fallaría al escribir su registro: se mandan a un fichero junto a los datos."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    from turnos.config import ruta_datos

    carpeta = ruta_datos().parent
    carpeta.mkdir(parents=True, exist_ok=True)
    registro = open(carpeta / "registro.txt", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    sys.stdout = sys.stdout or registro
    sys.stderr = sys.stderr or registro


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    _salida_a_fichero()
    if argv[:1] == ["--prueba"]:
        from turnos.arranque.windows.autoprueba import autoprueba

        sys.exit(autoprueba(Path(argv[1]) if len(argv) > 1 else None))
    from turnos.arranque.windows.lanzador import Lanzador

    Lanzador().ejecutar()
