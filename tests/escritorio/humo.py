"""Programa de la prueba de humo del modo escritorio (lo lanza test_humo.py con Xvfb).

Abre la aplicación, espera a que cargue la interfaz, registra en la página un
«pagehide» que crea un médico (como hacen los guardados pendientes de la
interfaz), cierra la ventana y escribe el resultado en JSON."""

import json
import socket

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("WebKit", "6.0")
from gi.repository import GLib, WebKit  # noqa: E402

from turnos.arranque.escritorio.aplicacion import Aplicacion  # noqa: E402

GUARDAR_AL_SALIR = """window.addEventListener('pagehide', () => fetch('/api/medicos', {
  method: 'POST', keepalive: true, headers: {'content-type': 'application/json'},
  body: JSON.stringify({nombre: 'Al cerrar', codigo: 'CIE'})}));"""

app = Aplicacion()
resultado = {"cargada": False, "titulo": None, "puerto": None}


def al_cargar(web, evento):
    if evento is not WebKit.LoadEvent.FINISHED or resultado["cargada"]:
        return
    resultado["cargada"] = True
    GLib.timeout_add(1500, cerrar, web)


def cerrar(web):
    resultado["titulo"] = app._ventana.get_title()
    resultado["puerto"] = app._servidor.puerto
    web.evaluate_javascript(GUARDAR_AL_SALIR, -1, None, None, None, None, None)
    GLib.timeout_add(300, lambda: app._ventana.close() and False)
    return False


def elegir_este_equipo():
    """Sin conexión guardada, la aplicación pregunta dónde trabajar: en este equipo."""
    paginas = app._ventana._paginas
    selector = paginas.get_child_by_name("inicio")
    if selector is None:
        return True  # aún no
    resultado["preguntado"] = True
    selector.elegir_local()
    app._ventana._web.connect("load-changed", al_cargar)
    return False


app.connect("activate", lambda _a: GLib.timeout_add(100, elegir_este_equipo))
GLib.timeout_add_seconds(40, app.quit)
resultado["salida"] = app.run([])
try:
    socket.create_connection(("127.0.0.1", resultado["puerto"] or 1), timeout=1).close()
    resultado["servidor_detenido"] = False
except OSError:
    resultado["servidor_detenido"] = True
print(json.dumps(resultado))
