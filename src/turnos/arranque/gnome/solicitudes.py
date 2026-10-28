"""Bandeja de solicitudes del planificador (diseño del modo servidor, 6.4; D-S10): solo
cuando la aplicación está conectada a un servidor de la red."""

from gi.repository import Adw, GLib, Gtk

TIPOS = {"DISPONIBILIDAD": "Disponibilidad semanal", "AUSENCIA": "Ausencia", "CALENDARIO": "Cambio en el calendario"}
ESTADOS = {"ESPERA_COMPANERO": "Esperando al compañero", "PENDIENTE": "Pendiente", "APROBADA": "Aprobada",
           "RESUELTA": "Resuelta", "RECHAZADA": "Rechazada", "RETIRADA": "Retirada"}
ABIERTAS = ("PENDIENTE", "ESPERA_COMPANERO")


def _texto(x: str | None) -> str:
    return GLib.markup_escape_text(x or "")


class PaginaSolicitudes(Adw.PreferencesPage):
    def __init__(self, ventana) -> None:
        super().__init__()
        self.ventana = ventana
        self.pendiente = True
        self.pagina_pila: Adw.ViewStackPage | None = None  # para el contador de la pestaña
        self._grupos: list[Adw.PreferencesGroup] = []
        self.filas: dict[int, Adw.ExpanderRow] = {}  # por id (también para las pruebas)

    def cargar(self) -> None:
        self.ventana.cliente.en_segundo_plano("GET", "/solicitudes", hecho=self._mostrar, fallo=self.ventana.error)

    def actualizar_contador(self) -> None:
        self.ventana.cliente.en_segundo_plano(
            "GET", "/solicitudes", hecho=self._contar, fallo=lambda _m: None)

    def _contar(self, solicitudes: list[dict]) -> None:
        if self.pagina_pila is not None:
            pendientes = sum(s["estado"] == "PENDIENTE" for s in solicitudes)
            self.pagina_pila.set_badge_number(pendientes)
            self.pagina_pila.set_needs_attention(pendientes > 0)

    def _mostrar(self, solicitudes: list[dict]) -> None:
        self._contar(solicitudes)
        for grupo in self._grupos:
            self.remove(grupo)
        self._grupos, self.filas = [], {}
        abiertas = [s for s in solicitudes if s["estado"] in ABIERTAS]
        resueltas = [s for s in solicitudes if s["estado"] not in ABIERTAS]
        pendientes = Adw.PreferencesGroup(
            title="Solicitudes pendientes",
            description="Lo que proponen los médicos. Al aprobar, el cambio se aplica (en un mes publicado, sin "
            "reabrirlo) y el médico lo ve en el momento.",
        )
        if not abiertas:
            pendientes.add(Adw.ActionRow(title="No hay solicitudes pendientes", icon_name="emblem-ok-symbolic"))
        for s in abiertas:
            pendientes.add(self._fila(s))
        self._grupos.append(pendientes)
        if resueltas:
            historial = Adw.PreferencesGroup(title=f"Historial ({len(resueltas)})")
            for s in resueltas[:100]:
                resolucion = f" · «{_texto(s['comentario_resolucion'])}»" if s["comentario_resolucion"] else ""
                historial.add(Adw.ActionRow(
                    title=f"{_texto(s['medico'])} · {TIPOS[s['tipo']]}",
                    subtitle=f"{ESTADOS[s['estado']]}{resolucion}\n{_texto(' '.join(s['descripcion']))}",
                    subtitle_lines=3,
                ))
            self._grupos.append(historial)
        for grupo in self._grupos:
            self.add(grupo)

    def _fila(self, s: dict) -> Adw.ExpanderRow:
        estado = ESTADOS[s["estado"]] if s["estado"] != "ESPERA_COMPANERO" else f"Esperando a {s['companero']}"
        fila = Adw.ExpanderRow(
            title=f"{_texto(s['medico'])} · {TIPOS[s['tipo']]}",
            subtitle=f"{estado} · {_texto(s['descripcion'][-1])}",
            subtitle_lines=2,
        )
        self.filas[s["id"]] = fila
        for linea in s["descripcion"]:
            fila.add_row(Adw.ActionRow(title=_texto(linea), title_lines=3))
        if s["comentario"]:
            fila.add_row(Adw.ActionRow(title=f"«{_texto(s['comentario'])}»", subtitle="Comentario del médico", title_lines=4))
        if s["estado"] != "PENDIENTE":
            return fila
        efectos = Adw.ActionRow(title="Calculando qué pasaría al aprobarla…", title_lines=6,
                                icon_name="dialog-information-symbolic")
        fila.add_row(efectos)
        fila.efectos = efectos
        comentario = Adw.EntryRow(title="Comentario para el médico (para rechazar, el motivo)")
        fila.comentario = comentario
        fila.add_row(comentario)
        botones = Gtk.Box(spacing=8, halign=Gtk.Align.END, margin_top=8, margin_bottom=8, margin_end=8)
        acciones = [("Aprobar", "aprobar", True, "suggested-action"), ("Rechazar", "rechazar", True, "destructive-action")]
        if s["tipo"] == "CALENDARIO":
            acciones.append(("Resuelta de otra forma", "aprobar", False, "flat"))
        for etiqueta, accion, aplicar, clase in acciones:
            boton = Gtk.Button(label=etiqueta, css_classes=[clase])
            boton.connect("clicked", lambda _b, a=accion, ap=aplicar: self.resolver(s["id"], a, ap))
            botones.append(boton)
        caja = Gtk.ListBoxRow(activatable=False, child=botones)
        fila.add_row(caja)
        fila.connect("notify::expanded", lambda f, _p: f.get_expanded() and self._efectos(s["id"], f))
        return fila

    def _efectos(self, id_: int, fila: Adw.ExpanderRow) -> None:
        if getattr(fila, "efectos_cargados", False):
            return
        fila.efectos_cargados = True

        def mostrar(efectos: dict) -> None:
            lineas = [*efectos["avisos"], *(f"Afecta a {m}: revisa el calendario" for m in efectos["meses"])]
            fila.efectos.set_title(_texto("\n".join(lineas)) or "Aprobarla no produce avisos nuevos en el calendario")
            fila.efectos.set_icon_name("dialog-warning-symbolic" if lineas else "emblem-ok-symbolic")

        self.ventana.cliente.en_segundo_plano("GET", f"/solicitudes/{id_}/efectos", hecho=mostrar, fallo=self.ventana.error)

    def resolver(self, id_: int, accion: str, aplicar: bool = True) -> None:
        fila = self.filas[id_]
        comentario = fila.comentario.get_text()

        def hecho(_s) -> None:
            self.ventana.aviso({"aprobar": "Aprobada" if aplicar else "Marcada como resuelta",
                                "rechazar": "Rechazada"}[accion])
            self.ventana.invalidar(self)  # puede haber cambiado el calendario, las reglas o las ausencias
            self.cargar()

        self.ventana.cliente.en_segundo_plano(
            "POST", f"/solicitudes/{id_}/{accion}", {"comentario": comentario, "aplicar": aplicar},
            hecho=hecho, fallo=self.ventana.error)
