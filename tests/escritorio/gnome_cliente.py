"""Programa de la prueba de la interfaz nativa como cliente de un servidor de la red (lo
lanza test_gnome.py con la configuración ya apuntando al servidor de prueba).

Argumento: «plani» (entra, genera noviembre), «ana» (médico: debe ir a la web) o
«bandeja» (entra como planificador y aprueba la solicitud pendiente)."""

import json
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib  # noqa: E402

from turnos.arranque.gnome.aplicacion import Aplicacion  # noqa: E402

modo = sys.argv[1]
quien = "plani" if modo == "bandeja" else modo
app = Aplicacion()
r = {"errores": []}


def v():
    return app._ventana


def cal():
    pagina = v()._pila.get_child_by_name("calendario")
    return (pagina.cal or {}) if pagina else {}


def entrar():
    dialogo = app.dialogo_entrar
    dialogo.usuario.set_text(quien)
    dialogo.contrasena.set_text(f"contrasena-{quien}")
    dialogo.enviar()


def generar():
    v()._pila.get_child_by_name("calendario")._generar_mes(False)


def anotar():
    r["usuario"] = v().usuario["nombre_visible"]
    r["estado"] = cal()["estado"]
    r["servidor_interno"] = app._servidor is not None
    app.quit()


def anotar_medico():
    r["titulo"] = v().get_content().get_title()
    app.quit()


def ir_a_solicitudes():
    r["contador"] = v().solicitudes.pagina_pila.get_badge_number()
    v()._pila.set_visible_child_name("solicitudes")


def desplegar():
    (id_, fila), = v().solicitudes.filas.items()
    r["solicitud"] = id_
    fila.set_expanded(True)


def aprobar():
    fila = v().solicitudes.filas[r["solicitud"]]
    r["efectos"] = fila.efectos.get_title()
    fila.comentario.set_text("Aprobada desde la nativa")
    v().solicitudes.resolver(r["solicitud"], "aprobar")


def terminar_bandeja():
    r["contador_despues"] = v().solicitudes.pagina_pila.get_badge_number()
    app.quit()


pasos = [(lambda: getattr(app, "dialogo_entrar", None) is not None and app.dialogo_entrar.get_mapped(), entrar)]
if modo == "bandeja":
    pasos += [
        (lambda: v().solicitudes is not None and v().solicitudes.pagina_pila.get_badge_number() == 1, ir_a_solicitudes),
        (lambda: len(v().solicitudes.filas) == 1, desplegar),
        (lambda: not v().solicitudes.filas[r["solicitud"]].efectos.get_title().startswith("Calculando"), aprobar),
        (lambda: v().solicitudes.pagina_pila.get_badge_number() == 0, terminar_bandeja),
    ]
elif modo == "plani":
    pasos += [
        (lambda: v().cliente is not None and cal().get("estado"), generar),
        (lambda: cal().get("estado") == "BORRADOR" and v()._pila.get_child_by_name("calendario")._enviando == 0, anotar),
    ]
else:
    pasos += [(lambda: isinstance(v().get_content(), Adw.StatusPage) and "Hola" in v().get_content().get_title(),
               anotar_medico)]


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
