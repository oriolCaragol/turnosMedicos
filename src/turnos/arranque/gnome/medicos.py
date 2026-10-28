"""Médicos y sus reglas: datos, turnos de la semana y carga mensual."""

from datetime import date

from gi.repository import Adw, Gdk, Gtk

from turnos.arranque.gnome.comun import (
    DIAS,
    DIAS_CORTOS,
    ELEGIBILIDAD,
    NOMBRE_TURNO,
    TURNOS,
    SelectorFecha,
    aplicar_colores,
    nombre_mes,
)
from turnos.arranque.gnome.rotaciones import PaginaRotaciones

JORNADAS = (("", "Normal"), ("MANANA_MAS_MEDIA", "Mañana + ½ tarde"), ("TARDE_MAS_MEDIA", "½ mañana + tarde"), ("DOBLE", "Mañana y tarde"))
PREFERENCIAS = (("", "—"), ("PREFIERE", "Prefiere"), ("EVITA", "Evita"))
TURNO_AUSENCIA = ((None, "Día completo"), ("MANANA", "Mañana"), ("TARDE", "Tarde"))


def colorear_celda(desplegable: Gtk.DropDown) -> None:
    """Color de la celda según su valor (como en la web): fijo, habitual, disponible o «—»."""
    for valor, _t in ELEGIBILIDAD:
        desplegable.remove_css_class(f"eleg-{valor.lower()}")
    desplegable.add_css_class(f"eleg-{ELEGIBILIDAD[desplegable.get_selected()][0].lower()}")


def mostrar_turnos(spin: Gtk.SpinButton) -> bool:
    """Turnos sin decimales salvo los medios: 15 → «15», 18,5 → «18,5» (como en la web)."""
    valor = spin.get_value()
    spin.set_text(f"{valor:g}".replace(".", ","))
    return True


class PaginaEquipo(Gtk.Box):
    """«Médicos y reglas», con dos subpestañas: médicos y turnos rotativos (como en la web)."""

    def __init__(self, ventana) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.ventana = ventana
        self._pila = Adw.ViewStack(vexpand=True)
        self.medicos = PaginaMedicos(ventana)
        self.rotaciones = PaginaRotaciones(ventana)
        self._pila.add_titled(self.medicos, "medicos", "Médicos")
        self._pila.add_titled(self.rotaciones, "rotaciones", "Turnos rotativos")
        cambiador = Adw.InlineViewSwitcher(stack=self._pila, halign=Gtk.Align.CENTER, margin_top=12)
        self.append(cambiador)
        self.append(self._pila)
        self._pila.connect("notify::visible-child", lambda *_: self.cargar(solo_si_hace_falta=True))

    @property
    def pendiente(self) -> bool:
        return self.medicos.pendiente or self.rotaciones.pendiente

    @pendiente.setter
    def pendiente(self, valor: bool) -> None:
        if valor:
            self.medicos.pendiente = self.rotaciones.pendiente = True

    def cargar(self, solo_si_hace_falta: bool = False) -> None:
        pagina = self._pila.get_visible_child()
        if pagina.pendiente or not solo_si_hace_falta:
            pagina.pendiente = False
            pagina.cargar()


def _hex(rgba: Gdk.RGBA) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(round(c * 255) for c in (rgba.red, rgba.green, rgba.blue)))


class PaginaMedicos(Gtk.ScrolledWindow):
    """Tarjetas de los médicos, abiertas y en paralelo (tantas columnas como quepan), como en la web."""

    def __init__(self, ventana) -> None:
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.ventana = ventana
        self.pendiente = True
        self.tarjetas: list[TarjetaMedico] = []
        self._orden: list[int] | None = None  # ver `orden_estable`
        self.por_presencia = False  # modo de carga «según la presencia»: sin rangos en las fichas
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=18, margin_bottom=24)
        cabecera = Gtk.Box(spacing=12)
        self.cabecera = cabecera  # en ventanas estrechas, en dos líneas (ver ventana.py)
        textos = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        textos.append(Gtk.Label(label="Médicos y sus reglas", xalign=0, css_classes=["title-4"]))
        self._explicacion = Gtk.Label(xalign=0, wrap=True, css_classes=["dim-label"])
        textos.append(self._explicacion)
        cabecera.append(textos)
        anadir = Gtk.Button(label="Añadir médico", css_classes=["suggested-action"], valign=Gtk.Align.CENTER)
        anadir.connect("clicked", lambda _b: self._anadir())
        acciones = Gtk.Box(spacing=12, halign=Gtk.Align.END, valign=Gtk.Align.CENTER)
        acciones.append(ventana.selector_mes())
        acciones.append(anadir)
        cabecera.append(acciones)
        caja.append(cabecera)
        self._rejilla = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, min_children_per_line=1, max_children_per_line=8,
            column_spacing=12, row_spacing=12, valign=Gtk.Align.START, activate_on_single_click=False,
        )
        caja.append(self._rejilla)
        self._vacio = Adw.StatusPage(icon_name="system-users-symbolic", title="Aún no hay médicos",
                                     description="Pulsa «Añadir médico» para empezar.", visible=False)
        caja.append(self._vacio)
        # Sin límite de ancho: en monitores anchos caben más tarjetas en paralelo.
        caja.set_margin_start(18)
        caja.set_margin_end(18)
        self.set_child(caja)

    @property
    def _grupo(self):  # compatibilidad: hay contenido cuando se han creado las tarjetas
        return self._rejilla if self.tarjetas or self._vacio.get_visible() else None

    def cargar(self) -> None:
        self.pendiente = False
        cliente = self.ventana.cliente

        def con_ajustes(ajustes: dict) -> None:
            self.por_presencia = ajustes.get("modo_carga") == "PRESENCIA"
            cliente.en_segundo_plano(
                "GET", f"/ausencias?desde={self.ventana.mes.isoformat()}",
                hecho=lambda a: cliente.en_segundo_plano("GET", "/medicos", hecho=lambda m: self._mostrar(m, a),
                                                         fallo=self.ventana.error),
                fallo=self.ventana.error,
            )

        cliente.en_segundo_plano("GET", "/ajustes", hecho=con_ajustes, fallo=self.ventana.error)

    def al_entrar(self) -> None:
        """Al volver a la pestaña, la lista se vuelve a ordenar (alfabéticamente)."""
        if self._orden is not None:
            self._orden = None
            self.pendiente = True

    def _mostrar(self, medicos: list[dict], ausencias: list[dict]) -> None:
        # Mientras se está en la pestaña, cada tarjeta se queda en su sitio: un médico
        # nuevo, al final (como en la web).
        self._orden = orden_estable(self._orden, [m["id"] for m in medicos])
        por_id = {m["id"]: m for m in medicos}
        medicos = [por_id[i] for i in self._orden]
        aplicar_colores(medicos)
        mes = nombre_mes(self.ventana.mes).lower()
        self._explicacion.set_label(
            f"Los cambios de reglas valen desde {mes} en adelante (el mes elegido en la cabecera). "
            "Disp.: disponible. Hab.: habitual, si ese día trabaja, preferentemente ese turno. Fijo: siempre. —: nunca."
        )
        self._rejilla.remove_all()
        self.tarjetas = [TarjetaMedico(self, m, [a for a in ausencias if a["medico_id"] == m["id"]]) for m in medicos]
        for tarjeta in self.tarjetas:
            self._rejilla.append(tarjeta)
            tarjeta.get_parent().set_focusable(False)  # el FlowBoxChild: el foco va a los campos
        self._vacio.set_visible(not medicos)

    def _anadir(self) -> None:
        dialogo = Adw.AlertDialog(heading="Añadir médico")
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        lista = Gtk.ListBox(css_classes=["boxed-list"], selection_mode=Gtk.SelectionMode.NONE)
        nombre = Adw.EntryRow(title="Nombre")
        codigo = Adw.EntryRow(title="Código (iniciales, hasta 6)")
        lista.append(nombre)
        lista.append(codigo)
        caja.append(lista)
        dialogo.set_extra_child(caja)
        dialogo.add_response("cancelar", "Cancelar")
        dialogo.add_response("anadir", "Añadir")
        dialogo.set_response_appearance("anadir", Adw.ResponseAppearance.SUGGESTED)

        def respuesta(_d, r):
            if r != "anadir":
                return
            datos = {"nombre": nombre.get_text().strip(), "codigo": codigo.get_text().strip().upper()}
            self.ventana.cliente.en_segundo_plano(
                "POST", "/medicos", datos, hecho=lambda _m: self._cambiado("Médico añadido"), fallo=self.ventana.error
            )

        dialogo.connect("response", respuesta)
        dialogo.present(self.ventana)

    def _cambiado(self, aviso: str) -> None:
        self.ventana.aviso(aviso)
        self.ventana.invalidar(self)
        self.cargar()


def orden_estable(previo: list[int] | None, actuales: list[int]) -> list[int]:
    """Los que ya estaban conservan su sitio, los nuevos van al final y los que ya no
    están desaparecen (como `util/orden.ts` de la web)."""
    if previo is None:
        return actuales
    return [i for i in previo if i in actuales] + [i for i in actuales if i not in previo]


class TarjetaMedico(Gtk.Box):
    """Tarjeta de un médico, siempre abierta: datos, turnos de la semana, carga, más reglas y ausencias."""

    def __init__(self, pagina: PaginaMedicos, medico: dict, ausencias: list[dict]) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["card", "tarjeta-medico"])
        self.pagina, self.medico, self.ausencias = pagina, medico, ausencias
        self._reglas = None
        m = medico

        # Cabecera: color, nombre, código y borrar.
        cabecera = Gtk.Box(spacing=6)
        self._color = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False), valign=Gtk.Align.CENTER,
                                            tooltip_text="Color en el calendario")
        rgba = Gdk.RGBA()
        rgba.parse(m["color"] or "#9a9996")
        self._color.set_rgba(rgba)
        self._color.connect("notify::rgba", lambda *_: self._guardar_medico())
        self._nombre = Gtk.Entry(text=m["nombre"], hexpand=True, width_chars=6, css_classes=["nombre-medico"],
                                 tooltip_text="Nombre del médico")
        self._codigo = Gtk.Entry(text=m["codigo"], width_chars=5, max_width_chars=6, max_length=6, tooltip_text="Código corto (iniciales)")
        for entrada in (self._nombre, self._codigo):
            entrada.connect("activate", lambda _e: self._guardar_medico())
            foco = Gtk.EventControllerFocus()
            foco.connect("leave", lambda _f: self._guardar_si_cambia())
            entrada.add_controller(foco)
        borrar = Gtk.Button(icon_name="user-trash-symbolic", css_classes=["flat"], valign=Gtk.Align.CENTER, tooltip_text="Borrar médico")
        borrar.connect("clicked", lambda _b: self._borrar())
        for w in (self._color, self._nombre, self._codigo, borrar):
            cabecera.append(w)
        self.append(cabecera)
        self._activo = Gtk.CheckButton(label="Activo" if m["activo"] else "Activo — no se le asignan turnos", active=m["activo"])
        self._activo.connect("toggled", lambda _c: self._guardar_medico())
        self.append(self._activo)
        if not m["activo"]:
            self.add_css_class("inactiva")

        self._cuerpo = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self._cuerpo.append(Gtk.Label(label="Cargando reglas…", css_classes=["dim-label"], xalign=0))
        self.append(self._cuerpo)
        self.append(Gtk.Separator())
        self._ausencias = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.append(self._ausencias)
        self._mostrar_ausencias()
        self._cargar_reglas()

    @property
    def _cliente(self):
        return self.pagina.ventana.cliente

    def _cargar_reglas(self) -> None:
        mes = self.pagina.ventana.mes
        self._cliente.en_segundo_plano(
            "GET", f"/medicos/{self.medico['id']}/reglas?fecha={mes.isoformat()}",
            hecho=self._construir, fallo=self.pagina.ventana.error,
        )

    def _construir(self, reglas: dict) -> None:
        self._reglas = reglas
        while (hijo := self._cuerpo.get_first_child()) is not None:
            self._cuerpo.remove(hijo)

        # Turnos de la semana.
        valores = {(c["dia_semana"], c["turno"]): c["valor"] for c in reglas["elegibilidad"]}
        cuadricula = Gtk.Grid(column_spacing=3, row_spacing=3, column_homogeneous=False)
        self._celdas = {}
        etiquetas = [texto for _v, texto in ELEGIBILIDAD]
        for col, dia in enumerate(DIAS_CORTOS, start=1):
            cuadricula.attach(Gtk.Label(label=dia, css_classes=["caption-heading"]), col, 0, 1, 1)
        for fila, turno in enumerate(TURNOS, start=1):
            cuadricula.attach(Gtk.Label(label=NOMBRE_TURNO[turno][:3] + ".", xalign=0,
                                        css_classes=["caption-heading", "titulo-turno", turno.lower()]), 0, fila, 1, 1)
            for dia in range(5):
                desplegable = Gtk.DropDown.new_from_strings(etiquetas)
                desplegable.add_css_class("celda-semana")
                actual = valores.get((dia, turno), "DISPONIBLE")
                desplegable.set_selected([v for v, _t in ELEGIBILIDAD].index(actual))
                desplegable.set_tooltip_text(f"{DIAS[dia]} · {NOMBRE_TURNO[turno]}")
                colorear_celda(desplegable)
                desplegable.connect("notify::selected", lambda d, _p: (colorear_celda(d), self._marcar_pendiente()))
                self._celdas[dia, turno] = desplegable
                cuadricula.attach(desplegable, dia + 1, fila, 1, 1)
        self._cuerpo.append(cuadricula)

        # Carga mensual (en turnos; la API la guarda en medios turnos) y más reglas.
        carga = reglas.get("carga")
        fila = Gtk.Box(spacing=6)
        self._minimo = Gtk.SpinButton.new_with_range(0, 40, 0.5)
        self._maximo = Gtk.SpinButton.new_with_range(0, 40, 0.5)
        fila.append(Gtk.Label(label="Turnos/mes", css_classes=["caption-heading", "dim-label"], margin_end=4))
        for spin, clave, texto in ((self._minimo, "minimo", "mín."), (self._maximo, "maximo", "máx.")):
            spin.set_digits(1)
            spin.set_width_chars(3)
            spin.connect("output", mostrar_turnos)
            spin.set_value((carga or {}).get(clave, 0) / 2)
            spin.set_valign(Gtk.Align.CENTER)
            spin.set_tooltip_text(f"Turnos al mes, {'mínimo' if clave == 'minimo' else 'máximo'}")
            spin.connect("value-changed", lambda *_: self._marcar_pendiente())
            fila.append(Gtk.Label(label=texto, css_classes=["caption"]))
            fila.append(spin)
        if not self.pagina.por_presencia:  # según la presencia no hay rangos (se conservan al guardar)
            self._cuerpo.append(fila)
        extra = Gtk.Box(spacing=6)
        self._resumen_extra = Gtk.Label(xalign=0, wrap=True, hexpand=True, css_classes=["caption", "dim-label"])
        mas = Gtk.Button(label="Más reglas…", css_classes=["flat"], valign=Gtk.Align.CENTER,
                         tooltip_text="Jornadas de más de un turno, límites por tipo de turno y preferencias")
        mas.connect("clicked", lambda _b: DialogoMasReglas(self).present(self.pagina.ventana))
        extra.append(self._resumen_extra)
        extra.append(mas)
        self._actualizar_resumen_extra()
        self._cuerpo.append(extra)

        pie = Gtk.Box(spacing=8)
        self._estado = Gtk.Label(xalign=0, hexpand=True, wrap=True, css_classes=["caption"])
        self._guardar = Gtk.Button(label="Guardar reglas", css_classes=["suggested-action"], valign=Gtk.Align.CENTER)
        self._guardar.connect("clicked", lambda _b: self._guardar_reglas())
        pie.append(self._estado)
        pie.append(self._guardar)
        self._cuerpo.append(pie)
        self._poner_estado(pendiente=False)

    def _poner_estado(self, pendiente: bool) -> None:
        carga = self._reglas.get("carga")
        vigente = self._reglas.get("vigente_desde")
        if pendiente:
            texto, clases = "Cambios sin guardar", ["caption", "warning"]
        elif carga is None:
            texto, clases = "Falta la carga mensual: sin ella no se le asignan turnos.", ["caption", "warning"]
        else:
            texto, clases = (f"Reglas desde {vigente[8:10]}/{vigente[5:7]}/{vigente[:4]}" if vigente else "Sin reglas guardadas"), ["caption", "dim-label"]
        self._estado.set_label(texto)
        self._estado.set_css_classes(clases)
        self._guardar.set_sensitive(pendiente or carga is None)

    def _marcar_pendiente(self) -> None:
        if self._reglas is not None and hasattr(self, "_estado"):
            self._poner_estado(pendiente=True)

    def _actualizar_resumen_extra(self) -> None:
        r = self._reglas
        partes = []
        if r.get("jornadas"):
            partes.append(f"{len(r['jornadas'])} {'jornada larga' if len(r['jornadas']) == 1 else 'jornadas largas'}")
        if r.get("carga_por_turno") and not self.pagina.por_presencia:
            partes.append("límites por turno")
        if r.get("preferencias"):
            partes.append(f"{len(r['preferencias'])} {'preferencia' if len(r['preferencias']) == 1 else 'preferencias'}")
        self._resumen_extra.set_label(", ".join(partes).capitalize() if partes else "Sin reglas adicionales")

    # --- Ausencias ------------------------------------------------------------------

    def _mostrar_ausencias(self) -> None:
        while (hijo := self._ausencias.get_first_child()) is not None:
            self._ausencias.remove(hijo)
        mes = self.pagina.ventana.mes
        titulo = Gtk.Box(spacing=6)
        titulo.append(Gtk.Label(label="AUSENCIAS", css_classes=["caption-heading", "dim-label"], xalign=0))
        titulo.append(Gtk.Label(label="" if self.ausencias else f"ninguna desde {nombre_mes(mes).lower()}",
                                css_classes=["caption", "dim-label"], hexpand=True, xalign=0))
        anadir = Gtk.Button(label="Añadir", icon_name="list-add-symbolic", tooltip_text="Añadir ausencia", css_classes=["flat"],
                            valign=Gtk.Align.CENTER, sensitive=self.medico["activo"])
        anadir.connect("clicked", lambda _b: self._crear_ausencia())
        titulo.append(anadir)
        self._ausencias.append(titulo)
        for a in self.ausencias:
            caja = Adw.WrapBox(child_spacing=6, line_spacing=6, natural_line_length=300)
            desde = SelectorFecha(date.fromisoformat(a["desde"]), lambda d, a=a: self._cambiar_ausencia(a, desde=d.isoformat()))
            hasta = SelectorFecha(date.fromisoformat(a["hasta"]), lambda d, a=a: self._cambiar_ausencia(a, hasta=d.isoformat()))
            turno = Gtk.DropDown.new_from_strings([t for _v, t in TURNO_AUSENCIA])
            turno.set_selected([v for v, _t in TURNO_AUSENCIA].index(a["turno"]))
            turno.connect("notify::selected", lambda d, _p, a=a: self._cambiar_ausencia(a, turno=TURNO_AUSENCIA[d.get_selected()][0]))
            quitar = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Quitar ausencia", css_classes=["flat"])
            quitar.connect("clicked", lambda _b, a=a: self._quitar_ausencia(a))
            for w in (desde, Gtk.Label(label="a"), hasta, turno, quitar):
                caja.append(w)
            self._ausencias.append(caja)

    def _recargar_ausencias(self, aviso: str) -> None:
        ventana = self.pagina.ventana

        def hecho(todas):
            self.ausencias = [a for a in todas if a["medico_id"] == self.medico["id"]]
            self._mostrar_ausencias()
            ventana.aviso(aviso)
            ventana.invalidar(self.pagina)

        self._cliente.en_segundo_plano("GET", f"/ausencias?desde={ventana.mes.isoformat()}", hecho=hecho, fallo=ventana.error)

    def _crear_ausencia(self) -> None:
        mes = self.pagina.ventana.mes.isoformat()
        datos = {"medico_id": self.medico["id"], "desde": mes, "hasta": mes, "turno": None}
        self._cliente.en_segundo_plano("POST", "/ausencias", datos, hecho=lambda _a: self._recargar_ausencias("Ausencia añadida"),
                                       fallo=self.pagina.ventana.error)

    def _cambiar_ausencia(self, ausencia: dict, **cambios) -> None:
        nueva = {k: ausencia[k] for k in ("medico_id", "desde", "hasta", "turno")} | cambios
        if nueva["hasta"] < nueva["desde"]:
            nueva["hasta"] = nueva["desde"]
        self._cliente.en_segundo_plano("PUT", f"/ausencias/{ausencia['id']}", nueva,
                                       hecho=lambda _a: self._recargar_ausencias("Ausencia guardada"), fallo=self.pagina.ventana.error)

    def _quitar_ausencia(self, ausencia: dict) -> None:
        self._cliente.en_segundo_plano("DELETE", f"/ausencias/{ausencia['id']}",
                                       hecho=lambda _a: self._recargar_ausencias("Ausencia quitada"), fallo=self.pagina.ventana.error)

    def _guardar_si_cambia(self) -> None:
        if (self._nombre.get_text().strip(), self._codigo.get_text().strip().upper()) != (self.medico["nombre"], self.medico["codigo"]):
            self._guardar_medico()

    def _guardar_medico(self) -> None:
        datos = {
            "nombre": self._nombre.get_text().strip(),
            "codigo": self._codigo.get_text().strip().upper(),
            "activo": self._activo.get_active(),
            "color": _hex(self._color.get_rgba()),
        }

        def hecho(medico):
            self.medico = medico
            self._activo.set_label("Activo" if medico["activo"] else "Activo — no se le asignan turnos")
            (self.remove_css_class if medico["activo"] else self.add_css_class)("inactiva")
            aplicar_colores([medico])
            self.pagina.ventana.aviso("Médico guardado")
            self.pagina.ventana.invalidar(self.pagina)

        self._cliente.en_segundo_plano("PUT", f"/medicos/{self.medico['id']}", datos, hecho=hecho, fallo=self.pagina.ventana.error)

    def _guardar_reglas(self) -> None:
        minimo, maximo = round(self._minimo.get_value() * 2), round(self._maximo.get_value() * 2)
        r = self._reglas
        datos = {
            "vigente_desde": self.pagina.ventana.mes.isoformat(),
            "elegibilidad": [
                {"dia_semana": dia, "turno": turno, "valor": ELEGIBILIDAD[d.get_selected()][0]}
                for (dia, turno), d in self._celdas.items() if ELEGIBILIDAD[d.get_selected()][0] != "DISPONIBLE"
            ],
            "jornadas": r.get("jornadas", []),
            "carga_por_turno": r.get("carga_por_turno", []),
            "preferencias": r.get("preferencias", []),
        }
        if maximo > 0 or r.get("carga") is not None:
            datos["carga"] = {"minimo": minimo, "maximo": maximo}

        def hecho(reglas):
            self._reglas = reglas
            self._actualizar_resumen_extra()
            self._poner_estado(pendiente=False)
            self.pagina.ventana.aviso("Reglas guardadas")
            self.pagina.ventana.invalidar(self.pagina)

        self._cliente.en_segundo_plano("PUT", f"/medicos/{self.medico['id']}/reglas", datos, hecho=hecho, fallo=self.pagina.ventana.error)

    def _borrar(self) -> None:
        dialogo = Adw.AlertDialog(
            heading=f"¿Borrar a {self.medico['nombre']}?",
            body="Si ya tiene turnos asignados, desactívalo en su lugar.",
        )
        dialogo.add_response("cancelar", "Cancelar")
        dialogo.add_response("borrar", "Borrar")
        dialogo.set_response_appearance("borrar", Adw.ResponseAppearance.DESTRUCTIVE)
        dialogo.connect("response", lambda _d, r: r == "borrar" and self._cliente.en_segundo_plano(
            "DELETE", f"/medicos/{self.medico['id']}",
            hecho=lambda _x: self.pagina._cambiado("Médico borrado"), fallo=self.pagina.ventana.error,
        ))
        dialogo.present(self.pagina.ventana)


class DialogoMasReglas(Adw.Dialog):
    """Reglas menos habituales: jornadas de más de un turno, límites por tipo de turno y preferencias."""

    def __init__(self, fila: TarjetaMedico) -> None:
        super().__init__(title=f"Más reglas de {fila.medico['nombre']}", content_width=560, content_height=720)
        self.fila = fila
        r = fila._reglas
        cabecera = Adw.HeaderBar(show_end_title_buttons=False, show_start_title_buttons=False)
        cancelar = Gtk.Button(label="Cancelar")
        cancelar.connect("clicked", lambda _b: self.close())
        guardar = Gtk.Button(label="Guardar", css_classes=["suggested-action"])
        guardar.connect("clicked", lambda _b: self._guardar())
        cabecera.pack_start(cancelar)
        cabecera.pack_end(guardar)
        pagina = Adw.PreferencesPage()

        jornadas = Adw.PreferencesGroup(title="Jornadas de más de un turno",
                                        description="El generador nunca las crea por su cuenta: solo se aplican los días que indiques aquí.")
        actuales = {j["dia_semana"]: j["tipo"] for j in r.get("jornadas", [])}
        self._jornadas = []
        for d in range(5):
            combo = Adw.ComboRow(title=DIAS[d], model=Gtk.StringList.new([t for _v, t in JORNADAS]))
            combo.set_selected([v for v, _t in JORNADAS].index(actuales.get(d, "")))
            self._jornadas.append(combo)
            jornadas.add(combo)
        pagina.add(jornadas)

        limites = Adw.PreferencesGroup(title="Límites por tipo de turno", description="Opcional, en turnos al mes.")
        por_turno = {c["turno"]: c for c in r.get("carga_por_turno", [])}
        self._limites = {}
        for t in TURNOS:
            actual = por_turno.get(t)
            expansor = Adw.ExpanderRow(title=f"Limitar las {NOMBRE_TURNO[t].lower()}s", show_enable_switch=True,
                                       enable_expansion=actual is not None, expanded=actual is not None)
            minimo = Adw.SpinRow.new_with_range(0, 40, 0.5)
            minimo.set_title("Mínimo")
            minimo.set_digits(1)
            minimo.connect("output", mostrar_turnos)
            minimo.set_value((actual or {}).get("minimo", 0) / 2)
            con_maximo = Adw.SwitchRow(title="Con máximo", active=bool(actual and actual.get("maximo") is not None))
            maximo = Adw.SpinRow.new_with_range(0, 40, 0.5)
            maximo.set_title("Máximo")
            maximo.set_digits(1)
            maximo.connect("output", mostrar_turnos)
            maximo.set_value(((actual or {}).get("maximo") or 0) / 2)
            con_maximo.bind_property("active", maximo, "sensitive", 2)  # SYNC_CREATE
            for w in (minimo, con_maximo, maximo):
                expansor.add_row(w)
            self._limites[t] = (expansor, minimo, con_maximo, maximo)
            limites.add(expansor)
        if not fila.pagina.por_presencia:  # según la presencia no hay límites que poner
            pagina.add(limites)

        preferencias = Adw.PreferencesGroup(title="Preferencias",
                                            description="Se respetan siempre que no impidan cumplir las demás reglas.")
        actuales_p = {(p["dia_semana"], p["turno"]): p["valor"] for p in r.get("preferencias", [])}
        cuadricula = Gtk.Grid(column_spacing=4, row_spacing=4, margin_top=10, margin_bottom=10, margin_start=12, margin_end=12)
        self._preferencias = {}
        for d, dia in enumerate(DIAS_CORTOS):
            cuadricula.attach(Gtk.Label(label=dia, css_classes=["caption-heading"]), d + 1, 0, 1, 1)
        for fila_n, t in enumerate(TURNOS, start=1):
            cuadricula.attach(Gtk.Label(label=NOMBRE_TURNO[t], xalign=0, css_classes=["caption"]), 0, fila_n, 1, 1)
            for d in range(5):
                desplegable = Gtk.DropDown.new_from_strings([texto for _v, texto in PREFERENCIAS])
                desplegable.set_selected([v for v, _t in PREFERENCIAS].index(actuales_p.get((d, t), "")))
                self._preferencias[d, t] = desplegable
                cuadricula.attach(desplegable, d + 1, fila_n, 1, 1)
        preferencias.add(Adw.PreferencesRow(activatable=False, child=Gtk.ScrolledWindow(
            child=cuadricula, vscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True)))
        pagina.add(preferencias)

        vista = Adw.ToolbarView(content=pagina)
        vista.add_top_bar(cabecera)
        self.set_child(vista)

    def _guardar(self) -> None:
        r = self.fila._reglas
        r["jornadas"] = [{"dia_semana": d, "tipo": JORNADAS[c.get_selected()][0]}
                         for d, c in enumerate(self._jornadas) if JORNADAS[c.get_selected()][0]]
        if not self.fila.pagina.por_presencia:
            r["carga_por_turno"] = [
                {"turno": t, "minimo": round(minimo.get_value() * 2),
                 "maximo": round(maximo.get_value() * 2) if con_maximo.get_active() else None}
                for t, (expansor, minimo, con_maximo, maximo) in self._limites.items() if expansor.get_enable_expansion()
            ]
        r["preferencias"] = [{"dia_semana": d, "turno": t, "valor": PREFERENCIAS[w.get_selected()][0]}
                             for (d, t), w in self._preferencias.items() if PREFERENCIAS[w.get_selected()][0]]
        self.fila._guardar_reglas()
        self.close()
