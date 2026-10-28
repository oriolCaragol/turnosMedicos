"""Turnos rotativos: grupos de médicos que comparten unos turnos por semanas alternas."""

from datetime import date, timedelta

from gi.repository import Adw, GLib, Gtk

from turnos.arranque.gnome.comun import DIAS, DIAS_CORTOS, NOMBRE_TURNO, TURNOS, Diferido, SelectorFecha, fecha_corta


def lunes_de(d: date) -> date:
    return d - timedelta(days=d.weekday())


def semanas_del_mes(mes: date) -> list[date]:
    """Lunes de las semanas que tocan días laborables del mes."""
    semanas, d = [], mes
    while d.month == mes.month:
        if d.weekday() < 5 and lunes_de(d) not in semanas:
            semanas.append(lunes_de(d))
        d += timedelta(days=1)
    return semanas


def titular(medicos: list[int], desde: date, lunes: date) -> int | None:
    """A quién le toca la semana del `lunes` (igual que el motor)."""
    if len(medicos) < 2 or lunes < lunes_de(desde):
        return None
    return medicos[((lunes - lunes_de(desde)).days // 7) % len(medicos)]


class PaginaRotaciones(Adw.PreferencesPage):
    def __init__(self, ventana) -> None:
        super().__init__()
        self.ventana = ventana
        self.pendiente = True
        self._grupo = None
        self.medicos: list[dict] = []

    def cargar(self) -> None:
        self.ventana.cliente.en_segundo_plano("GET", "/medicos", hecho=self._con_medicos, fallo=self.ventana.error)

    def _con_medicos(self, medicos: list[dict]) -> None:
        self.medicos = medicos
        self.ventana.cliente.en_segundo_plano("GET", "/rotaciones", hecho=self._mostrar, fallo=self.ventana.error)

    def _mostrar(self, rotaciones: list[dict]) -> None:
        if self._grupo is not None:
            self.remove(self._grupo)
        self._grupo = Adw.PreferencesGroup(
            title="Turnos rotativos",
            description="Grupos de médicos que comparten unos turnos de la semana sin coincidir: cada semana los hace uno "
            "del grupo, por orden, como turno fijo, y los demás no los tienen. Si a quien le toca está ausente o es "
            "festivo, ese día lo cubre el resto del equipo. La cuenta de semanas sigue de un mes a otro.",
        )
        anadir = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Añadir turno rotativo", css_classes=["flat"])
        anadir.connect("clicked", lambda _b: self._anadir())
        self._grupo.set_header_suffix(anadir)
        for r in rotaciones:
            self._grupo.add(FilaRotacion(self, r))
        if not rotaciones:
            self._grupo.add(Adw.ActionRow(title="Todavía no hay turnos rotativos", subtitle="Pulsa + para añadir uno."))
        self.add(self._grupo)

    def _anadir(self) -> None:
        datos = {"nombre": "Nuevo turno rotativo", "desde": semanas_del_mes(self.ventana.mes)[0].isoformat(),
                 "activa": True, "medicos": [], "huecos": []}

        def hecho(_r):
            self.ventana.aviso("Turno rotativo añadido")
            self.ventana.invalidar(self)
            self.cargar()

        self.ventana.cliente.en_segundo_plano("POST", "/rotaciones", datos, hecho=hecho, fallo=self.ventana.error)


class FilaRotacion(Adw.ExpanderRow):
    def __init__(self, pagina: PaginaRotaciones, rotacion: dict) -> None:
        super().__init__(title=GLib.markup_escape_text(rotacion["nombre"]))
        self.pagina = pagina
        self.id = rotacion["id"]
        self.r = {k: rotacion[k] for k in ("nombre", "desde", "activa", "medicos", "huecos")}
        self._guardar = Diferido(self._enviar, 500)
        self._filas_dinamicas: list = []
        self._estado = Gtk.Label(css_classes=["caption", "dim-label"], valign=Gtk.Align.CENTER)
        self.add_suffix(self._estado)

        nombre = Adw.EntryRow(title="Nombre", text=self.r["nombre"])
        nombre.connect("changed", lambda e: self._editar(nombre=e.get_text()))
        activa = Adw.SwitchRow(title="Activo", subtitle="Si no, no se aplica al generar", active=self.r["activa"])
        activa.connect("notify::active", lambda s, _p: self._editar(activa=s.get_active()))
        desde = Adw.ActionRow(title="Empieza la semana del", subtitle="Esa semana le toca al primero de la lista")
        desde.add_suffix(SelectorFecha(date.fromisoformat(self.r["desde"]), lambda d: self._editar(desde=d.isoformat())))
        for fila in (nombre, activa, desde):
            self.add_row(fila)

        # Turnos que comparten.
        cuadricula = Gtk.Grid(column_spacing=4, row_spacing=4, margin_top=10, margin_bottom=10, margin_start=12, margin_end=12)
        cuadricula.attach(Gtk.Label(label="Turnos que comparten", xalign=0), 0, 0, 6, 1)
        for d, dia in enumerate(DIAS_CORTOS):
            cuadricula.attach(Gtk.Label(label=dia, css_classes=["caption-heading"]), d + 1, 1, 1, 1)
        for fila, t in enumerate(TURNOS, start=2):
            cuadricula.attach(Gtk.Label(label=NOMBRE_TURNO[t], xalign=0, css_classes=["caption"]), 0, fila, 1, 1)
            for d in range(5):
                boton = Gtk.ToggleButton(active=self._tiene(d, t), tooltip_text=f"{DIAS[d]}, {NOMBRE_TURNO[t].lower()}",
                                         width_request=40, icon_name="object-select-symbolic", css_classes=["hueco"])
                boton.connect("toggled", lambda b, d=d, t=t: self._alternar(d, t, b.get_active()))
                cuadricula.attach(boton, d + 1, fila, 1, 1)
        self.add_row(Adw.PreferencesRow(activatable=False, child=cuadricula))

        borrar = Adw.ButtonRow(title="Borrar turno rotativo", start_icon_name="user-trash-symbolic", css_classes=["destructive-action"])
        borrar.connect("activated", lambda _r: self._borrar())
        self._borrar_fila = borrar
        self._redibujar()

    def _tiene(self, d: int, t: str) -> bool:
        return any(h["dia_semana"] == d and h["turno"] == t for h in self.r["huecos"])

    def _nombre(self, medico_id: int) -> str:
        return next((m["nombre"] for m in self.pagina.medicos if m["id"] == medico_id), f"Médico {medico_id}")

    def _redibujar(self) -> None:
        """Médicos, añadir médico, vista previa y borrar: cambian con cada edición."""
        for fila in self._filas_dinamicas:
            self.remove(fila)
        self._filas_dinamicas = []
        miembros = self.r["medicos"]
        for i, m in enumerate(miembros):
            fila = Adw.ActionRow(title=f"{i + 1}. {GLib.markup_escape_text(self._nombre(m))}")
            fila.add_prefix(Gtk.Box(css_classes=["punto-color", f"color-{m}"], valign=Gtk.Align.CENTER))
            for icono, texto, sensible, accion in [
                ("go-up-symbolic", "Subir", i > 0, lambda _b, i=i: self._mover(i, -1)),
                ("go-down-symbolic", "Bajar", i < len(miembros) - 1, lambda _b, i=i: self._mover(i, 1)),
                ("list-remove-symbolic", "Quitar", True, lambda _b, m=m: self._editar(medicos=[x for x in miembros if x != m])),
            ]:
                boton = Gtk.Button(icon_name=icono, tooltip_text=texto, sensitive=sensible, css_classes=["flat"], valign=Gtk.Align.CENTER)
                boton.connect("clicked", accion)
                fila.add_suffix(boton)
            self._filas_dinamicas.append(fila)
        candidatos = [m for m in self.pagina.medicos if m["activo"] and m["id"] not in miembros]
        if candidatos:
            anadir = Adw.ComboRow(title="Añadir médico", model=Gtk.StringList.new(["—"] + [m["nombre"] for m in candidatos]))
            anadir.connect("notify::selected", lambda c, _p: c.get_selected() > 0 and self._editar(
                medicos=miembros + [candidatos[c.get_selected() - 1]["id"]]))
            self._filas_dinamicas.append(anadir)
        incompleta = len(miembros) < 2 or not self.r["huecos"]
        mes = self.pagina.ventana.mes
        if incompleta:
            vista = Adw.ActionRow(title="Incompleto", subtitle="No se aplica hasta que tenga al menos dos médicos y un turno.",
                                  icon_name="dialog-warning-symbolic")
        else:
            desde = date.fromisoformat(self.r["desde"])
            texto = [f"Semana del {fecha_corta(l.isoformat())[:5]}: {self._nombre(t) if (t := titular(miembros, desde, l)) else 'aún no empieza'}"
                     for l in semanas_del_mes(mes)]
            vista = Adw.ActionRow(title="Este mes", subtitle="\n".join(texto), subtitle_lines=len(texto))
        self._filas_dinamicas.append(vista)
        self._filas_dinamicas.append(self._borrar_fila)
        for fila in self._filas_dinamicas:
            self.add_row(fila)
        self.set_subtitle(", ".join(self._nombre(m) for m in miembros) or "Sin médicos")

    def _mover(self, i: int, paso: int) -> None:
        lista = list(self.r["medicos"])
        lista[i], lista[i + paso] = lista[i + paso], lista[i]
        self._editar(medicos=lista)

    def _alternar(self, d: int, t: str, activo: bool) -> None:
        huecos = [h for h in self.r["huecos"] if not (h["dia_semana"] == d and h["turno"] == t)]
        if activo:
            huecos.append({"dia_semana": d, "turno": t})
        self._editar(huecos=huecos)

    def _editar(self, **cambios) -> None:
        self.r.update(cambios)
        if "nombre" in cambios:
            self.set_title(GLib.markup_escape_text(cambios["nombre"]))
        if {"medicos", "desde", "huecos"} & cambios.keys():
            GLib.idle_add(lambda: self._redibujar() and False)
        if self.r["nombre"].strip():
            self._estado.set_label("Guardando…")
            self._guardar.programar()

    def _enviar(self) -> None:
        def hecho(_r):
            self._estado.set_label("Guardado")
            self.pagina.ventana.invalidar(self.pagina)

        datos = {**self.r, "nombre": self.r["nombre"].strip()}
        self.pagina.ventana.cliente.en_segundo_plano("PUT", f"/rotaciones/{self.id}", datos, hecho=hecho,
                                                     fallo=self.pagina.ventana.error)

    def _borrar(self) -> None:
        dialogo = Adw.AlertDialog(heading=f"¿Borrar el turno rotativo «{self.r['nombre']}»?")
        dialogo.add_response("cancelar", "Cancelar")
        dialogo.add_response("borrar", "Borrar")
        dialogo.set_response_appearance("borrar", Adw.ResponseAppearance.DESTRUCTIVE)

        def hecho(_r):
            self.pagina.ventana.aviso("Turno rotativo borrado")
            self.pagina.ventana.invalidar(self.pagina)
            self.pagina.cargar()

        dialogo.connect("response", lambda _d, r: r == "borrar" and self.pagina.ventana.cliente.en_segundo_plano(
            "DELETE", f"/rotaciones/{self.id}", hecho=hecho, fallo=self.pagina.ventana.error))
        dialogo.present(self.pagina.ventana)
