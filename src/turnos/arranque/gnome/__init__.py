"""Prototipo de interfaz nativa GNOME: `turnos-gnome`.

Alternativa a la interfaz web (que también se usa en el modo escritorio): las
pantallas están hechas con GTK 4 y libadwaita, sin WebView. Es cliente de la misma
API local, así que el núcleo, los datos y las reglas son los mismos.
"""

import sys

ID_APLICACION = "io.oriol.TurnosMedicos.Nativa"


def main() -> None:
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
    except (ImportError, ValueError) as error:
        sys.exit(
            f"La interfaz nativa necesita GTK 4 y libadwaita con PyGObject ({error}). "
            "En Fedora: sudo dnf install python3-gobject libadwaita."
        )
    from turnos.arranque.dialogos import volver_a_abrir_si_hace_falta
    from turnos.arranque.gnome.aplicacion import Aplicacion

    aplicacion = Aplicacion()
    codigo = aplicacion.run(sys.argv)
    volver_a_abrir_si_hace_falta(aplicacion)  # tras cambiar la conexión
    sys.exit(codigo)
