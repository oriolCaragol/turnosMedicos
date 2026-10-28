"""Programa de la prueba completa de la interfaz nativa (lo lanza test_gnome.py con Xvfb).

Recorre, desde los widgets, las funciones que no cubre gnome_humo.py y escribe en
JSON lo que ha visto; test_gnome.py comprueba después el resultado en la API."""

import json
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib  # noqa: E402

from turnos.arranque.gnome.aplicacion import Aplicacion  # noqa: E402
from turnos.arranque.gnome.calendario import cambios_al_soltar  # noqa: E402
from turnos.arranque.gnome.imprimir import imprimir  # noqa: E402
from turnos.arranque.gnome.medicos import DialogoMasReglas  # noqa: E402

salida = sys.argv[1]
app = Aplicacion()
r = {"errores": []}


def v():
    return app._ventana


def p(nombre):
    return v()._pila.get_child_by_name(nombre)


def cal():
    return p("calendario").cal or {}


def libre():
    return p("calendario")._enviando == 0


def asignaciones():
    return sorted((a["medico_id"], a["fecha"], a["mitad"]) for a in cal()["asignaciones"])


# --- Calendario ---------------------------------------------------------------------


def generar():
    p("calendario")._generar_mes(False)


def guardar_base():
    r["base"] = asignaciones()
    p("calendario")._generar_mes(True)  # alternativa


def tras_alternativa():
    r["alternativa_distinta"] = asignaciones() != r["base"]
    p("calendario").deshacer()


def tras_deshacer():
    r["deshacer_vuelve"] = asignaciones() == r["base"]
    p("calendario").rehacer()


def tras_rehacer():
    r["rehacer_vuelve"] = asignaciones() != r["base"]
    # Arrastrar: mover a alguien de la mañana del día 4 a la tarde del día 5.
    c = cal()
    medico = next(a["medico_id"] for a in c["asignaciones"] if a["fecha"] == "2026-11-04" and a["mitad"] == "M1")
    r["arrastrado"] = medico
    origen = {"tipo": "celda", "medico": medico, "fecha": "2026-11-04", "turno": "MANANA"}
    r["cambios_arrastre"] = cambios_al_soltar(c, origen, {"fecha": "2026-11-05", "turno": "TARDE"})
    p("calendario")._soltar(f"celda|{medico}|2026-11-04|MANANA", {"fecha": "2026-11-05", "turno": "TARDE"})


def rango():
    m = cal()["medicos"][0]
    r["rango_medico"] = m["id"]
    p("calendario")._enviar("PUT", f"/carga/{m['id']}", {"minimo": 2, "maximo": 30}, "Rango guardado")


def pdfs():
    horarios = [{"turno": "MANANA", "inicio": "08:00:00", "fin": "15:00:00"}, {"turno": "TARDE", "inicio": "15:00:00", "fin": "22:00:00"}]
    imprimir(v(), "calendario", cal(), horarios, v().mes, pdf=f"{salida}/calendario.pdf")
    imprimir(v(), "roles", cal(), horarios, v().mes, pdf=f"{salida}/roles.pdf")
    v()._pila.set_visible_child_name("medicos")


# --- Médicos: ausencia y más reglas -------------------------------------------------


def fila_medico():
    return p("medicos").medicos.tarjetas[0]


def desplegar():
    pass  # las tarjetas ya están abiertas


def ausencia():
    fila_medico()._crear_ausencia()


def mas_reglas():
    dialogo = DialogoMasReglas(fila_medico())
    dialogo._jornadas[2].set_selected(3)  # miércoles: mañana y tarde
    expansor, minimo, con_maximo, maximo = dialogo._limites["TARDE"]
    expansor.set_enable_expansion(True)
    minimo.set_value(2)
    con_maximo.set_active(True)
    maximo.set_value(8)
    dialogo._preferencias[4, "TARDE"].set_selected(2)  # viernes tarde: evita
    dialogo._guardar()


def rotacion():
    p("medicos")._pila.set_visible_child_name("rotaciones")


def anadir_rotacion():
    p("medicos").rotaciones._anadir()


def editar_rotacion():
    fila = p("medicos").rotaciones._grupo.get_row(0)
    medicos = [m["id"] for m in p("medicos").rotaciones.medicos][:2]
    fila._editar(nombre="Lunes de mañana", medicos=medicos, huecos=[{"dia_semana": 0, "turno": "MANANA"}])
    r["rotacion_medicos"] = medicos


def cobertura():
    v()._pila.set_visible_child_name("cobertura")


def editar_cobertura():
    pagina = p("cobertura")
    pagina._cambiar(4, ("T1", "T2"), "maximo", 4)  # viernes por la tarde: hasta 4


def excepcion():
    from datetime import date

    p("cobertura")._guardar_excepcion(date(2026, 12, 24), {"MANANA": {"minimo": 1, "maximo": 1}, "TARDE": {"minimo": 1, "maximo": 2}})


def configuracion():
    v()._pila.set_visible_child_name("configuracion")


def horarios():
    pagina = p("configuracion")
    pagina._horas["MANANA", "inicio"].set_text("08:30")
    pagina._guardar_horarios()


def festivos():
    v()._pila.set_visible_child_name("festivos")


def restaurar():
    p("festivos")._restaurar()


def terminar():
    app.quit()


pasos = [
    (lambda: v().cliente is not None and cal().get("estado"), generar),
    (lambda: cal().get("estado") == "BORRADOR" and libre(), guardar_base),
    (lambda: libre() and p("calendario")._generar.get_sensitive(), tras_alternativa),
    (libre, tras_deshacer),
    (libre, tras_rehacer),
    (libre, rango),
    (libre, pdfs),
    (lambda: p("medicos").medicos.tarjetas, desplegar),
    (lambda: getattr(fila_medico(), "_celdas", None), ausencia),
    (lambda: len(fila_medico().ausencias) == 1, mas_reglas),
    (lambda: fila_medico()._reglas.get("jornadas"), rotacion),
    (lambda: p("medicos").rotaciones._grupo is not None, anadir_rotacion),
    (lambda: p("medicos").rotaciones._grupo.get_row(0).id, editar_rotacion),
    (lambda: p("medicos").rotaciones._grupo.get_row(0)._estado.get_label() == "Guardado", cobertura),
    (lambda: p("cobertura")._valores, editar_cobertura),
    (lambda: not p("cobertura")._guardar._id, excepcion),
    (lambda: True, configuracion),
    (lambda: p("configuracion")._horas["MANANA", "inicio"].get_text(), horarios),
    (lambda: p("configuracion")._horas["MANANA", "inicio"].get_text() == "08:30", festivos),
    (lambda: p("festivos")._grupos, restaurar),
    (lambda: True, terminar),
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
GLib.timeout_add_seconds(90, app.quit)
app.run([])
r["pasos_sin_hacer"] = len(pasos)
print(json.dumps(r))
