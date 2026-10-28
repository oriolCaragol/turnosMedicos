"""Programa de la prueba de la pantalla de inicio de la interfaz nativa (lo lanza
test_gnome.py sin conexión guardada): ¿en este equipo o en un servidor?

Argumento: «local», o la dirección de un servidor de prueba (se elige «Recordar mi
elección», se confirma la huella y se entra como planificador)."""

import json
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib  # noqa: E402

from turnos.arranque import conexion as cx  # noqa: E402
from turnos.arranque.dialogos import SelectorInicio  # noqa: E402
from turnos.arranque.gnome.aplicacion import Aplicacion  # noqa: E402

destino = sys.argv[1]
app = Aplicacion()
r = {"errores": []}


def v():
    return app._ventana


def cal():
    pagina = v()._pila.get_child_by_name("calendario")
    return (pagina.cal or {}) if pagina else {}


def elegir():
    selector = v().get_content()
    if destino == "local":
        selector.elegir_local()
    else:
        selector.recordar.set_active(True)
        selector.elegir_servidor(destino)


def confirmar():
    alerta = v().get_visible_dialog()
    r["texto_confirmacion"] = alerta.get_body()
    r["huella"] = cx.formatear_huella(cx.huella_pem(cx.descargar_autoridad(destino)))
    alerta.emit("response", "confiar")
    alerta.force_close()


def entrar():
    app.dialogo_entrar.usuario.set_text("plani")
    app.dialogo_entrar.contrasena.set_text("contrasena-plani")
    app.dialogo_entrar.enviar()


def anotar():
    r["estado"] = cal()["estado"]
    r["servidor_interno"] = app._servidor is not None
    r["usuario"] = (v().usuario or {}).get("nombre_visible")
    app.quit()


pasos = [(lambda: isinstance(v().get_content(), SelectorInicio), elegir)]
if destino != "local":
    pasos += [
        (lambda: isinstance(v().get_visible_dialog(), Adw.AlertDialog), confirmar),
        (lambda: getattr(app, "dialogo_entrar", None) is not None and app.dialogo_entrar.get_mapped(), entrar),
    ]
pasos.append((lambda: v().cliente is not None and cal().get("estado"), anotar))


def siguiente():
    if not pasos:
        return
    condicion, funcion = pasos.pop(0)

    def comprobar():
        try:
            listo = condicion()
        except Exception:  # noqa: BLE001 — aún no está
            listo = False
        if not listo:
            return True
        try:
            funcion()
        except Exception as error:  # noqa: BLE001
            r["errores"].append(f"{funcion.__name__}: {error!r}")
        GLib.timeout_add(300, lambda: siguiente() and False)
        return False

    GLib.timeout_add(100, comprobar)


app.connect("activate", lambda _a: siguiente())
GLib.timeout_add_seconds(60, app.quit)
app.run([])
r["pasos_sin_hacer"] = len(pasos)
print(json.dumps(r))
