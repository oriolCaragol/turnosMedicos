"""Textos y utilidades compartidas por las pantallas del prototipo nativo."""

from datetime import date

MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre")
DIAS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
DIAS_CORTOS = ("L", "M", "X", "J", "V")
TURNOS = ("MANANA", "TARDE")
NOMBRE_TURNO = {"MANANA": "Mañana", "TARDE": "Tarde"}
MITADES = {"MANANA": ("M1", "M2"), "TARDE": ("T1", "T2")}
MITAD_CONTIGUA = {"MANANA": "M2", "TARDE": "T1"}  # la del medio turno (especificaciones, 5.3)
OTRO_TURNO = {"MANANA": "TARDE", "TARDE": "MANANA"}
ELEGIBILIDAD = (("DISPONIBLE", "Disp."), ("HABITUAL", "Hab."), ("FIJO", "Fijo"), ("NO_DISPONIBLE", "—"))
AMBITOS = (("NACIONAL", "Nacional"), ("AUTONOMICO", "Autonómico"), ("LOCAL", "Local"), ("OTRO", "Otro"))


def nombre_mes(mes: date) -> str:
    return f"{MESES[mes.month - 1].capitalize()} {mes.year}"


def desplazar(mes: date, meses: int) -> date:
    total = mes.year * 12 + mes.month - 1 + meses
    return date(total // 12, total % 12 + 1, 1)


def mes_siguiente(hoy: date | None = None) -> date:
    return desplazar((hoy or date.today()).replace(day=1), 1)


def cifra(medios: int) -> str:
    """Medios turnos → texto: 7 → "3½", 1 → "½", 4 → "2"."""
    enteros = medios // 2
    if medios % 2 == 0:
        return str(enteros)
    return "½" if enteros == 0 else f"{enteros}½"


def fecha_corta(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def mitades_con_valor(mitades: set[str], turno: str, valor: float) -> list[str]:
    """Mitades del día tras poner el turno a 0, ½ o 1, conservando el otro turno."""
    nuevas = {h for h in mitades if h not in MITADES[turno]}
    if valor == 1:
        nuevas |= set(MITADES[turno])
    elif valor == 0.5:
        nuevas.add(MITAD_CONTIGUA[turno])
    return sorted(nuevas)


def valor_en_turno(mitades: set[str], turno: str) -> float:
    n = sum(h in mitades for h in MITADES[turno])
    return 1 if n == 2 else 0.5 if n == 1 else 0


# --- Colores de los médicos ----------------------------------------------------------

_proveedor_colores = None


def aplicar_colores(medicos: list[dict]) -> None:
    """Clases CSS `medico-<id>` (ficha) y `color-<id>` (punto) con el color de cada médico."""
    global _proveedor_colores
    from gi.repository import Gdk, Gtk

    reglas = []
    for m in medicos:
        color = m.get("color")
        if color:
            reglas.append(f".medico-{m['id']} {{ background: alpha({color}, 0.28); }}")
            reglas.append(f".color-{m['id']} {{ background: {color}; }}")
        else:
            reglas.append(f".color-{m['id']} {{ background: alpha(currentColor, 0.3); }}")
    if _proveedor_colores is None:
        _proveedor_colores = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), _proveedor_colores, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1
        )
    _proveedor_colores.load_from_string("\n".join(reglas))


def nombre_corto(nombre: str) -> str:
    """"Dra. García" → "García" (como en las fichas del calendario web)."""
    for prefijo in ("Dra. ", "Dr. "):
        if nombre.startswith(prefijo):
            return nombre[len(prefijo):]
    return nombre


# --- Widgets comunes ---------------------------------------------------------------


def SelectorFecha(fecha: date | None, al_cambiar, minimo: date | None = None):  # noqa: N802 — se usa como un widget
    """Botón con la fecha (dd/mm/aaaa) que abre un calendario. `al_cambiar(date)`."""
    from gi.repository import GLib, Gtk

    boton = Gtk.MenuButton(valign=Gtk.Align.CENTER, always_show_arrow=False, css_classes=["numeric"])
    calendario = Gtk.Calendar()
    boton.set_popover(Gtk.Popover(child=calendario))
    estado = {"fecha": fecha}

    def mostrar(d):
        estado["fecha"] = d
        boton.set_label(f"{d.day:02d}/{d.month:02d}/{d.year}" if d else "Elegir fecha")
        if d:
            calendario.select_day(GLib.DateTime.new_local(d.year, d.month, d.day, 0, 0, 0))

    def elegido(cal):
        g = cal.get_date()
        d = date(g.get_year(), g.get_month(), g.get_day_of_month())
        if minimo and d < minimo:
            d = minimo
        boton.get_popover().popdown()
        if d != estado["fecha"]:
            mostrar(d)
            al_cambiar(d)

    mostrar(fecha)
    calendario.connect("day-selected", elegido)
    boton.fecha = lambda: estado["fecha"]
    boton.poner = mostrar
    return boton


def Numero(valor: int, al_cambiar, maximo: int = 50):  # noqa: N802
    """Campo numérico entero (0–maximo) que avisa al cambiar."""
    from gi.repository import Gtk

    campo = Gtk.SpinButton.new_with_range(0, maximo, 1)
    campo.set_value(valor)
    campo.set_valign(Gtk.Align.CENTER)
    campo.set_numeric(True)
    campo.connect("value-changed", lambda c: al_cambiar(int(c.get_value())))
    return campo


class Diferido:
    """Llama a una función cuando dejan de llegar cambios durante `ms` (guardado automático)."""

    def __init__(self, funcion, ms: int = 600) -> None:
        self._funcion, self._ms, self._id = funcion, ms, 0

    def programar(self, *args) -> None:
        from gi.repository import GLib

        if self._id:
            GLib.source_remove(self._id)
        self._id = GLib.timeout_add(self._ms, self._lanzar, args)

    def _lanzar(self, args) -> bool:
        self._id = 0
        self._funcion(*args)
        return False
