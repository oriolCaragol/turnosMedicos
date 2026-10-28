"""Programa de la prueba de la interfaz nativa (lo lanza test_gnome.py con Xvfb).

Con un equipo ya preparado por la prueba: genera el mes, quita a un médico de una
tarde y cambia un papel desde el diálogo del turno, guarda las reglas de un médico
y añade un festivo, todo desde los widgets. Escribe el resultado en JSON."""

import json

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib  # noqa: E402

from turnos.arranque.gnome.aplicacion import Aplicacion  # noqa: E402

app = Aplicacion()
resultado = {"errores": []}


def v():
    return app._ventana


def pagina(nombre):
    return v()._pila.get_child_by_name(nombre)


def filas(contenedor):
    """Filas (Adw.ActionRow) dentro de un widget."""
    encontrados, pendientes = [], [contenedor]
    while pendientes:
        w = pendientes.pop()
        if isinstance(w, Adw.ActionRow):
            encontrados.append(w)
        hijo = w.get_first_child()
        while hijo is not None:
            pendientes.append(hijo)
            hijo = hijo.get_next_sibling()
    return encontrados


def sufijo(fila, clase):
    """El primer widget de esa clase dentro de la fila (en orden)."""
    pendientes = [fila]
    while pendientes:
        w = pendientes.pop(0)
        if isinstance(w, clase):
            return w
        hijo = w.get_first_child()
        while hijo is not None:
            pendientes.append(hijo)
            hijo = hijo.get_next_sibling()
    return None


def generar():
    pagina("calendario")._generar_mes(False)


def abrir_turno():
    cal = pagina("calendario")
    resultado["estado"] = cal.cal["estado"]
    cal._abrir_turno("2026-11-04", "TARDE")


def grupos_de(fila):
    """Los Adw.ToggleGroup de una fila: el del turno y, si hace la tarde completa, el del papel."""
    grupos, pendientes = [], [fila]
    while pendientes:
        w = pendientes.pop(0)
        if isinstance(w, Adw.ToggleGroup):
            grupos.append(w)
        hijo = w.get_first_child()
        while hijo is not None:
            pendientes.append(hijo)
            hijo = hijo.get_next_sibling()
    return grupos


def quitar_y_cambiar_papel():
    dialogo = pagina("calendario")._dialogo
    con_turno = [f for f in filas(dialogo) if sufijo(f, Adw.ToggleGroup).get_active_name() == "1"]
    resultado["en_la_tarde_antes"] = len(con_turno)
    # Se quita a quien tiene las urgencias: así siempre queda alguien a quien dárselas.
    de_urgencias = [f for f in con_turno if len(grupos_de(f)) == 2 and grupos_de(f)[1].get_active_name() == "URGENCIAS"]
    sufijo((de_urgencias or con_turno)[0], Adw.ToggleGroup).set_active_name("0")


def papel():
    dialogo = pagina("calendario")._dialogo
    resultado["en_la_tarde_despues"] = sum(sufijo(f, Adw.ToggleGroup).get_active_name() == "1" for f in filas(dialogo))
    # El último grupo de la primera fila con turno es el de urgencias/domicilios.
    for f in filas(dialogo):
        grupos = grupos_de(f)
        if len(grupos) == 2 and grupos[1].get_active_name() != "URGENCIAS":
            resultado["nuevo_de_urgencias"] = f.get_title()
            grupos[1].set_active_name("URGENCIAS")
            return


def cerrar_y_reglas():
    pagina("calendario")._dialogo.close()
    v()._pila.set_visible_child_name("medicos")


def desplegar():
    pass  # las tarjetas ya están abiertas


def guardar_reglas():
    fila = pagina("medicos").medicos.tarjetas[0]
    fila._celdas[0, "MANANA"].set_selected(3)  # lunes por la mañana: «—»
    fila._maximo.set_value(30)
    fila._guardar_reglas()


def festivo():
    v()._pila.set_visible_child_name("festivos")
    f = pagina("festivos")
    f._fecha.set_text("24/12/2026")
    f._nombre.set_text("Nochebuena")
    f._anadir()


def terminar():
    app.quit()


def cal():
    return pagina("calendario").cal or {}


def dialogo_al_dia():
    """El diálogo ya refleja el último cambio (se reconstruye al recibir el calendario)."""
    d = pagina("calendario")._dialogo
    return d is not None and not pagina("calendario")._enviando


# (condición para empezar, acción): se espera a la condición, comprobándola cada 100 ms.
pasos = [
    (lambda: v().cliente is not None and cal().get("estado"), generar),
    (lambda: cal().get("estado") == "BORRADOR", abrir_turno),
    (dialogo_al_dia, quitar_y_cambiar_papel),
    (dialogo_al_dia, papel),
    (dialogo_al_dia, cerrar_y_reglas),
    (lambda: pagina("medicos").medicos.tarjetas, desplegar),
    (lambda: getattr(pagina("medicos").medicos.tarjetas[0], "_celdas", None), guardar_reglas),
    (lambda: pagina("medicos").medicos.tarjetas[0]._reglas.get("carga", {}).get("maximo") == 60, festivo),
    (lambda: not pagina("festivos")._fecha.get_text(), terminar),
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
            resultado["errores"].append(f"{funcion.__name__}: {error!r}")
        siguiente()
        return False

    GLib.timeout_add(100, comprobar)


app.connect("activate", lambda _a: siguiente())
GLib.timeout_add_seconds(60, app.quit)
app.run([])
print(json.dumps(resultado))
