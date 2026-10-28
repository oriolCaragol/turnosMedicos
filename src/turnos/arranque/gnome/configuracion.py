"""Configuración: reglas generales, municipio y festivos oficiales, y datos."""

from datetime import date

from gi.repository import Adw, Gio, GLib, Gtk

from turnos.arranque.gnome.comun import AMBITOS, fecha_corta

ESTADO = {"NUEVO": "Falta", "IGUAL": "Ya está", "DISTINTO": "Distinto"}


class PaginaConfiguracion(Adw.PreferencesPage):
    def __init__(self, ventana) -> None:
        super().__init__()
        self.ventana = ventana
        self.pendiente = True
        self._ajustes: dict | None = None
        self._cargando = False

        generales = Adw.PreferencesGroup(title="Reglas generales", description="Se aplican al generar o regenerar el calendario.")
        self._todos = Adw.SwitchRow(
            title="Todos los médicos trabajan cada día laborable",
            subtitle="Salvo ausencia o si ese día no tienen ningún turno posible", subtitle_lines=2,
        )
        self._presencia = Adw.SwitchRow(
            title="Urgencias y domicilios según la presencia",
            subtitle="Quien tiene ausencias en el mes recibe menos, en proporción", subtitle_lines=2,
        )
        # Cuánto trabaja cada médico: con un rango en su ficha o todos los días salvo ausencia.
        self._modos = ["RANGOS", "PRESENCIA"]
        self._modo = Adw.ComboRow(
            title="Cuánto trabaja cada médico", title_lines=2,
            model=Gtk.StringList.new(["Según un rango de turnos al mes en su ficha",
                                      "Todos los días laborables, salvo ausencia"]),
        )
        self._modo.connect("notify::selected", lambda *_: self._guardar_ajustes())
        generales.add(self._modo)
        for fila in (self._todos, self._presencia):
            fila.connect("notify::active", lambda *_: self._guardar_ajustes())
            generales.add(fila)
        # Qué papel se mantiene igual para todos si no se pueden igualar los dos.
        self._prioridades = ["URGENCIAS", "DOMICILIOS", "IGUAL"]
        self._prioridad = Adw.ComboRow(
            title="Si no se pueden repartir las dos cosas por igual",
            subtitle="Qué papel se mantiene igual para todos", title_lines=2,
            model=Gtk.StringList.new(["Urgencias iguales; la diferencia, en domicilios",
                                      "Domicilios iguales; la diferencia, en urgencias",
                                      "Sin preferencia"]),
        )
        self._prioridad.connect("notify::selected", lambda *_: self._guardar_ajustes())
        generales.add(self._prioridad)
        self.add(generales)

        vista = Adw.PreferencesGroup(title="Vista del calendario")
        self._cobertura = Adw.SwitchRow(
            title="Mostrar en cada turno los médicos asignados frente a los necesarios",
            subtitle="Por ejemplo «6/0–7». Los turnos por debajo del mínimo o por encima del máximo se resaltan igualmente",
            title_lines=2, subtitle_lines=2,
        )
        self._cobertura.connect("notify::active", lambda *_: self._guardar_ajustes())
        vista.add(self._cobertura)
        self.add(vista)

        horario = Adw.PreferencesGroup(
            title="Horario de los turnos",
            description="Aparece en el calendario impreso y en la hoja de cálculo. El corte separa las dos mitades de "
            "cada turno, que se usan en las jornadas de turno y medio.",
        )
        self._horas: dict[tuple[str, str], Gtk.Entry] = {}
        for turno, nombre in (("MANANA", "Mañana"), ("TARDE", "Tarde")):
            fila = Adw.ActionRow(title=nombre)
            for campo, texto in (("inicio", "Inicio"), ("corte", "Corte"), ("fin", "Fin")):
                entrada = Gtk.Entry(max_length=5, width_chars=5, valign=Gtk.Align.CENTER, tooltip_text=f"{nombre}, {texto.lower()} (hh:mm)",
                                    placeholder_text="hh:mm", css_classes=["numeric"])
                fila.add_suffix(Gtk.Label(label=texto, css_classes=["caption", "dim-label"]))
                fila.add_suffix(entrada)
                self._horas[turno, campo] = entrada
            horario.add(fila)
        guardar_horario = Adw.ButtonRow(title="Guardar horarios", start_icon_name="document-save-symbolic")
        guardar_horario.connect("activated", lambda _r: self._guardar_horarios())
        horario.add(guardar_horario)
        self.add(horario)

        festivos = Adw.PreferencesGroup(
            title="Festivos oficiales",
            description="Busca los festivos nacionales, autonómicos y locales del municipio del centro y añade los que falten.",
        )
        self._municipio = Adw.ActionRow(title="Municipio del centro")
        cambiar = Gtk.Button(label="Cambiar", valign=Gtk.Align.CENTER)
        cambiar.connect("clicked", lambda _b: DialogoMunicipio(self).present(self.ventana))
        self._municipio.add_suffix(cambiar)
        festivos.add(self._municipio)
        buscar = Adw.ActionRow(title="Buscar los festivos del año", subtitle="Necesita conexión a internet")
        self._anio = Gtk.SpinButton.new_with_range(2020, 2100, 1)
        self._anio.set_valign(Gtk.Align.CENTER)
        boton = Gtk.Button(label="Buscar", css_classes=["suggested-action"], valign=Gtk.Align.CENTER)
        boton.connect("clicked", lambda _b: DialogoFestivosOficiales(self, int(self._anio.get_value())).present(self.ventana))
        buscar.add_suffix(self._anio)
        buscar.add_suffix(boton)
        festivos.add(buscar)
        self.add(festivos)

        datos = Adw.PreferencesGroup(
            title="Datos",
            description="Todos los datos están en un único fichero. Importar una copia sustituye todos los datos actuales.",
        )
        exportar = Adw.ButtonRow(title="Exportar copia de los datos…", start_icon_name="document-save-symbolic")
        exportar.connect("activated", lambda _r: self._exportar())
        importar = Adw.ButtonRow(title="Importar una copia…", start_icon_name="document-open-symbolic")
        importar.connect("activated", lambda _r: self._importar())
        datos.add(exportar)
        datos.add(importar)
        self.add(datos)

    def cargar(self) -> None:
        mes = self.ventana.mes
        self._anio.set_value(mes.year)
        self.ventana.cliente.en_segundo_plano("GET", "/ajustes", hecho=self._mostrar, fallo=self.ventana.error)
        self.ventana.cliente.en_segundo_plano("GET", "/horarios", hecho=self._mostrar_horarios, fallo=self.ventana.error)

    def _mostrar_horarios(self, horarios: list[dict]) -> None:
        for h in horarios:
            for campo in ("inicio", "corte", "fin"):
                self._horas[h["turno"], campo].set_text(h[campo][:5])

    def _guardar_horarios(self) -> None:
        datos = []
        for turno in ("MANANA", "TARDE"):
            fila = {"turno": turno}
            for campo in ("inicio", "corte", "fin"):
                texto = self._horas[turno, campo].get_text().strip()
                try:
                    h, m = (int(x) for x in texto.split(":"))
                    assert 0 <= h < 24 and 0 <= m < 60
                except (ValueError, AssertionError):
                    self.ventana.error(f"Hora no válida: «{texto}» (usa hh:mm)")
                    return
                fila[campo] = f"{h:02d}:{m:02d}:00"
            datos.append(fila)
        self.ventana.cliente.en_segundo_plano(
            "PUT", "/horarios", datos,
            hecho=lambda h: (self._mostrar_horarios(h), self.ventana.aviso("Horarios guardados")), fallo=self.ventana.error,
        )

    def _mostrar(self, ajustes: dict) -> None:
        self._cargando = True
        self._ajustes = ajustes
        por_presencia = ajustes.get("modo_carga") == "PRESENCIA"
        self._modo.set_selected(1 if por_presencia else 0)
        # Según la presencia, «todos trabajan» va incluido.
        self._todos.set_active(ajustes["todos_trabajan"] or por_presencia)
        self._todos.set_sensitive(not por_presencia)
        self._presencia.set_active(ajustes["roles_segun_presencia"])
        self._prioridad.set_selected(self._prioridades.index(ajustes.get("prioridad_roles", "URGENCIAS")))
        self._cobertura.set_active(ajustes.get("mostrar_cobertura", False))
        self._cargando = False
        self.ventana.cliente.en_segundo_plano(
            "GET", f"/festivos/municipios/{ajustes['municipio']}",
            hecho=lambda m: self._municipio.set_subtitle(f"{m['nombre']} · {m['provincia']} ({m['ccaa_nombre']})"),
            fallo=self.ventana.error,
        )

    def guardar(self, cambios: dict, aviso: str = "Ajuste guardado") -> None:
        nuevos = {**self._ajustes, **cambios}

        def hecho(ajustes):
            self._mostrar(ajustes)
            self.ventana.aviso(aviso)
            self.ventana.invalidar(self)

        self.ventana.cliente.en_segundo_plano("PUT", "/ajustes", nuevos, hecho=hecho, fallo=self.ventana.error)

    def _guardar_ajustes(self) -> None:
        if not self._cargando and self._ajustes is not None:
            por_presencia = self._modos[self._modo.get_selected()] == "PRESENCIA"
            self.guardar({"modo_carga": self._modos[self._modo.get_selected()],
                          "todos_trabajan": self._todos.get_active() and (not por_presencia or self._ajustes["todos_trabajan"]),
                          "roles_segun_presencia": self._presencia.get_active(),
                          "prioridad_roles": self._prioridades[self._prioridad.get_selected()],
                          "mostrar_cobertura": self._cobertura.get_active()})

    # --- Datos ------------------------------------------------------------------------

    def _exportar(self) -> None:
        def guardar(contenido: bytes) -> None:
            dialogo = Gtk.FileDialog(title="Exportar copia", initial_name=f"turnos-copia-{date.today():%Y%m%d}.sqlite")

            def elegido(d, resultado):
                try:
                    destino = d.save_finish(resultado)
                except GLib.Error:
                    return
                destino.replace_contents(contenido, None, False, Gio.FileCreateFlags.REPLACE_DESTINATION, None)
                self.ventana.aviso(f"Copia guardada en «{destino.get_basename()}»")

            dialogo.save(self.ventana, None, elegido)

        self.ventana.cliente.en_segundo_plano("GET", "/copia-de-seguridad", hecho=guardar, fallo=self.ventana.error, binario=True)

    def _importar(self) -> None:
        dialogo = Gtk.FileDialog(title="Importar una copia")

        def elegido(d, resultado):
            try:
                fichero = d.open_finish(resultado)
            except GLib.Error:
                return
            confirmar = Adw.AlertDialog(
                heading="¿Sustituir todos los datos?",
                body=f"Se reemplazan los médicos, reglas, ausencias, cobertura, festivos y calendarios por los de "
                     f"«{fichero.get_basename()}». Antes se guarda una copia de los datos actuales.",
            )
            confirmar.add_response("cancelar", "Cancelar")
            confirmar.add_response("importar", "Sustituir")
            confirmar.set_response_appearance("importar", Adw.ResponseAppearance.DESTRUCTIVE)
            confirmar.connect("response", lambda _c, r: r == "importar" and self._subir(fichero))
            confirmar.present(self.ventana)

        dialogo.open(self.ventana, None, elegido)

    def _subir(self, fichero: Gio.File) -> None:
        _ok, contenido, _etag = fichero.load_contents(None)

        def hecho(r):
            self.ventana.aviso(f"Datos importados: {r['medicos']} médicos y {r['meses']} meses")
            self.ventana.recargar()

        self.ventana.cliente.en_segundo_plano("POST", "/importar", bytes(contenido), hecho=hecho, fallo=self.ventana.error)


class DialogoMunicipio(Adw.Dialog):
    def __init__(self, pagina: PaginaConfiguracion) -> None:
        super().__init__(title="Municipio del centro", content_width=460, content_height=520)
        self.pagina = pagina
        buscador = Gtk.SearchEntry(placeholder_text="Escribe el nombre del municipio", margin_start=12, margin_end=12)
        self._lista = Gtk.ListBox(css_classes=["boxed-list"], selection_mode=Gtk.SelectionMode.NONE, margin_start=12,
                                  margin_end=12, margin_bottom=12, valign=Gtk.Align.START)
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=6)
        caja.append(buscador)
        caja.append(Gtk.ScrolledWindow(child=self._lista, vexpand=True))
        vista = Adw.ToolbarView(content=caja)
        vista.add_top_bar(Adw.HeaderBar())
        self.set_child(vista)
        buscador.connect("search-changed", self._buscar)

    def _buscar(self, entrada: Gtk.SearchEntry) -> None:
        texto = entrada.get_text().strip()
        if len(texto) < 2:
            self._lista.remove_all()
            return
        self.pagina.ventana.cliente.en_segundo_plano(
            "GET", f"/festivos/municipios?q={GLib.uri_escape_string(texto, None, False)}",
            hecho=self._mostrar, fallo=self.pagina.ventana.error,
        )

    def _mostrar(self, municipios: list[dict]) -> None:
        self._lista.remove_all()
        for m in municipios:
            fila = Adw.ActionRow(title=GLib.markup_escape_text(m["nombre"]),
                                 subtitle=f"{m['provincia']} ({m['ccaa_nombre']})", activatable=True)
            fila.connect("activated", lambda _f, m=m: self._elegir(m))
            self._lista.append(fila)

    def _elegir(self, municipio: dict) -> None:
        self.pagina.guardar({"municipio": municipio["ine"]}, f"Municipio del centro: {municipio['nombre']}")
        self.close()


class DialogoFestivosOficiales(Adw.Dialog):
    def __init__(self, pagina: PaginaConfiguracion, anio: int) -> None:
        super().__init__(title=f"Festivos oficiales de {anio}", content_width=640, content_height=680)
        self.pagina, self.anio = pagina, anio
        self._cabecera = Adw.HeaderBar()
        self._anadir = Gtk.Button(label="Añadir los que faltan", css_classes=["suggested-action"], sensitive=False)
        self._anadir.connect("clicked", lambda _b: self._cargar())
        self._cabecera.pack_end(self._anadir)
        self._contenido = Adw.PreferencesPage()
        self._estado = Adw.StatusPage(title="Buscando…", child=Adw.Spinner(width_request=32, height_request=32))
        self._vista = Adw.ToolbarView(content=self._estado)
        self._vista.add_top_bar(self._cabecera)
        self.set_child(self._vista)
        self._buscar()

    def _buscar(self) -> None:
        self.pagina.ventana.cliente.en_segundo_plano(
            "GET", f"/festivos/oficiales/{self.anio}", hecho=self._mostrar, fallo=self._fallo
        )

    def _fallo(self, mensaje: str) -> None:
        self._vista.set_content(Adw.StatusPage(icon_name="network-offline-symbolic", title="No se ha podido buscar",
                                               description=GLib.markup_escape_text(mensaje)))

    def _mostrar(self, busqueda: dict) -> None:
        pagina = Adw.PreferencesPage()
        if busqueda["avisos"]:
            avisos = Adw.PreferencesGroup()
            for aviso in busqueda["avisos"]:
                avisos.add(Adw.ActionRow(title=GLib.markup_escape_text(aviso), title_lines=3, icon_name="dialog-warning-symbolic"))
            pagina.add(avisos)
        grupo = Adw.PreferencesGroup(
            title=busqueda["municipio"]["nombre"],
            description="Fuentes: " + (" y ".join(busqueda["fuentes"]) or "ninguna")
            + ". «Distinto»: ya tienes un festivo ese día con otro nombre o ámbito; no se cambia.",
        )
        nombres = dict(AMBITOS)
        faltan = 0
        for f in busqueda["festivos"]:
            fila = Adw.ActionRow(
                title=GLib.markup_escape_text(f["descripcion"]),
                subtitle=GLib.markup_escape_text(f"{fecha_corta(f['fecha'])} · {nombres.get(f['ambito'], f['ambito'])} · {f['fuente']}"),
            )
            if f.get("url"):
                enlace = Gtk.LinkButton(uri=f["url"], icon_name="adw-external-link-symbolic", valign=Gtk.Align.CENTER,
                                        tooltip_text="Abrir la fuente oficial")
                enlace.set_label("")
                fila.add_suffix(enlace)
            etiqueta = Gtk.Label(label=ESTADO.get(f["estado"], f["estado"]), valign=Gtk.Align.CENTER,
                                 css_classes=["caption-heading"] + (["success"] if f["estado"] == "NUEVO" else ["dim-label"]))
            fila.add_suffix(etiqueta)
            faltan += f["estado"] == "NUEVO"
            grupo.add(fila)
        pagina.add(grupo)
        self._anadir.set_sensitive(faltan > 0)
        self._anadir.set_label(f"Añadir los {faltan} que faltan" if faltan else "No falta ninguno")
        self._vista.set_content(pagina)

    def _cargar(self) -> None:
        def hecho(anadidos):
            self.pagina.ventana.aviso(f"Añadidos {len(anadidos)} festivos")
            self.pagina.ventana.invalidar(self.pagina)
            self._buscar()

        self.pagina.ventana.cliente.en_segundo_plano(
            "POST", f"/festivos/oficiales/{self.anio}", hecho=hecho, fallo=self.pagina.ventana.error
        )
