"""Programa de la prueba del modo escritorio (WebView) como cliente de un servidor de la
red (lo lanza test_humo.py). Abre la ventana, espera la página del servidor y escribe en
JSON lo que ve. Con el argumento «entrar», además entra como planificador (como haría el
formulario) y vuelve a cargar; la cookie debe quedar guardada para la próxima vez."""

import json
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("WebKit", "6.0")
from gi.repository import GLib, WebKit  # noqa: E402

from turnos.arranque.escritorio.aplicacion import Aplicacion  # noqa: E402

ENTRAR = """fetch('/api/sesion', {method: 'POST', headers: {'content-type': 'application/json', 'x-cliente': 'prueba'},
  body: JSON.stringify({usuario: 'plani', contrasena: 'contrasena-plani'})}).then(() => location.reload());"""
# Con sesión, las pestañas; sin ella, el título de la página de entrada.
QUE_SE_VE = "(document.querySelector('nav') || document.querySelector('h2') || {}).textContent || document.body.innerText.slice(0, 200)"

app = Aplicacion()
resultado = {"vistas": [], "servidor_interno": None}
entrar = sys.argv[1:] == ["entrar"]
intentos: dict[int, int] = {}


def leer(web):
    def recibido(web, tarea, *_datos):
        try:
            texto = web.evaluate_javascript_finish(tarea).to_string()
        except GLib.Error as error:
            texto = f"error: {error.message}"
        if not texto and intentos.setdefault(len(resultado["vistas"]), 0) < 30:  # aún «Cargando…»
            intentos[len(resultado["vistas"])] += 1
            GLib.timeout_add(300, leer, web)
            return
        resultado["vistas"].append(texto)
        if entrar and len(resultado["vistas"]) == 1:
            web.evaluate_javascript(ENTRAR, -1, None, None, None, None, None)
            GLib.timeout_add(2500, leer, web)
        else:
            terminar()

    web.evaluate_javascript(QUE_SE_VE, -1, None, None, None, recibido, None)
    return False


def al_cargar(web, evento):
    if evento is WebKit.LoadEvent.FINISHED and not resultado["vistas"] and web.get_uri().startswith("https://"):
        GLib.timeout_add(2000, leer, web)


def terminar():
    resultado["servidor_interno"] = app._servidor is not None
    resultado["uri"] = app._ventana._web.get_uri()
    GLib.timeout_add(200, lambda: app._ventana.close() and False)


def conectar_al_visor():
    if app._ventana._web is None:
        return True  # aún no está
    app._ventana._web.connect("load-changed", al_cargar)
    return False


app.connect("activate", lambda _a: GLib.timeout_add(20, conectar_al_visor))
GLib.timeout_add_seconds(45, app.quit)
resultado["salida"] = app.run([])
# Para diagnosticar un fallo: qué se veía al final.
paginas = app._ventana._paginas
resultado["pantalla"] = paginas.get_visible_child_name()
resultado["error"] = f"{app._ventana._error.get_title()}: {app._ventana._error.get_description()}"
resultado["uri_final"] = app._ventana._web.get_uri()
print(json.dumps(resultado))
