"""Modo escritorio GNOME: `turnos-escritorio` (diseño del modo escritorio, 9).

Una ventana GTK con un WebView que muestra la misma interfaz que el modo web,
servida por el mismo servidor en un puerto libre de 127.0.0.1 y con token.
Necesita PyGObject con GTK 4, libadwaita 1 y WebKitGTK 6.0 (los trae el
runtime de GNOME en Flatpak; fuera de él, `python3-gobject` del sistema).
"""

import sys

ID_APLICACION = "io.oriol.TurnosMedicos"


def main() -> None:
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        gi.require_version("WebKit", "6.0")
    except (ImportError, ValueError) as error:
        sys.exit(
            "El modo escritorio necesita GTK 4, libadwaita y WebKitGTK 6.0 con PyGObject "
            f"({error}). En Fedora: sudo dnf install python3-gobject webkitgtk6.0 libadwaita; "
            "y el entorno de Python creado con --system-site-packages."
        )
    from turnos.arranque.dialogos import volver_a_abrir_si_hace_falta
    from turnos.arranque.escritorio.aplicacion import Aplicacion

    aplicacion = Aplicacion()
    codigo = aplicacion.run(sys.argv)
    volver_a_abrir_si_hace_falta(aplicacion)  # tras cambiar la conexión
    sys.exit(codigo)
