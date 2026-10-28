"""Programa de la prueba de varios clientes en la interfaz nativa (lo lanza test_gnome.py).

Otro cliente cambia el mes mientras la ventana está abierta: la ventana debe verlo sin
recargar y vaciar su historial de deshacer; si no se entera (deja de escuchar) y cambia
una versión antigua, el servidor lo rechaza y la ventana muestra la actual."""

import json

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib  # noqa: E402

from turnos.arranque.gnome.aplicacion import Aplicacion  # noqa: E402
from turnos.arranque.gnome.calendario import cambios_al_soltar  # noqa: E402
from turnos.arranque.gnome.cliente import ClienteApi  # noqa: E402

app = Aplicacion()
r = {"errores": []}
otro: ClienteApi | None = None


def pagina():
    return app._ventana._pila.get_child_by_name("calendario")


def cal():
    return pagina().cal or {}


def libre():
    return pagina()._enviando == 0


def quitar_primera(c, fecha):
    a = next(a for a in c["asignaciones"] if a["fecha"] == fecha)
    origen = {"tipo": "celda", "medico": a["medico_id"], "fecha": fecha, "turno": "MANANA" if a["mitad"][0] == "M" else "TARDE"}
    return cambios_al_soltar(c, origen, None)


def generar():
    pagina()._generar_mes(False)


def quitar_propia():
    pagina()._cambiar(quitar_primera(cal(), "2026-11-03"))


def cambio_del_otro():
    global otro
    r["puede_deshacer_antes"] = bool(pagina()._atras)
    cliente = app._ventana.cliente
    otro = ClienteApi(cliente.base, cliente.token)
    actual = otro.pedir("GET", "/periodos/2026/11")
    r["version_del_otro"] = otro.pedir("POST", "/periodos/2026/11/cambios", quitar_primera(actual, "2026-11-04"),
                                       cabeceras={"X-Version-Mes": str(actual["version"])})["version"]


def tras_cambio_del_otro():
    r["visto_sin_recargar"] = True
    r["puede_deshacer_despues"] = bool(pagina()._atras)
    # La ventana deja de escuchar: el siguiente cambio del otro no le llega.
    app._ventana.cliente.parar()
    actual = otro.pedir("GET", "/periodos/2026/11")
    r["version_final"] = otro.pedir("POST", "/periodos/2026/11/cambios", quitar_primera(actual, "2026-11-05"),
                                    cabeceras={"X-Version-Mes": str(actual["version"])})["version"]


def cambio_con_version_antigua():
    r["version_antigua"] = cal()["version"]
    pagina()._cambiar(quitar_primera(cal(), "2026-11-06"))


def terminar():
    r["version_mostrada"] = cal()["version"]
    app.quit()


pasos = [
    (lambda: app._ventana.cliente is not None and cal().get("estado"), generar),
    (lambda: cal().get("estado") == "BORRADOR" and libre(), quitar_propia),
    (lambda: libre() and pagina()._atras and cal()["version"] == 2, cambio_del_otro),
    (lambda: cal().get("version") == r["version_del_otro"], tras_cambio_del_otro),
    (lambda: True, cambio_con_version_antigua),
    (lambda: libre() and cal().get("version") == r["version_final"], terminar),
]


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
