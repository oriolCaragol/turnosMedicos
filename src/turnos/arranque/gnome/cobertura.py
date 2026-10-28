"""Cobertura: médicos necesarios en cada turno de la semana y excepciones por fecha."""

from datetime import date

from gi.repository import Adw, GLib, Gtk

from turnos.arranque.gnome.comun import DIAS, MITADES, NOMBRE_TURNO, TURNOS, Diferido, Numero, SelectorFecha, fecha_corta

MITAD_CORTA = {"M1": "1.ª", "M2": "2.ª", "T1": "1.ª", "T2": "2.ª"}


class PaginaCobertura(Adw.PreferencesPage):
    def __init__(self, ventana) -> None:
        super().__init__()
        self.ventana = ventana
        self.pendiente = True
        self._valores: dict[tuple[int, str], dict] = {}
        self._por_mitades = False
        self._guardar = Diferido(self._enviar_semanal)
        self._grupos: list = []

    def cargar(self) -> None:
        cliente = self.ventana.cliente
        cliente.en_segundo_plano("GET", "/cobertura/semanal", hecho=self._mostrar_semanal, fallo=self.ventana.error)

    # --- Cobertura semanal ------------------------------------------------------------

    def _mostrar_semanal(self, filas: list[dict]) -> None:
        self._valores = {(c["dia_semana"], c["mitad"]): {"minimo": c["minimo"], "maximo": c["maximo"]} for c in filas}
        self._por_mitades = self._por_mitades or any(
            self._valores[d, MITADES[t][0]] != self._valores[d, MITADES[t][1]] for d in range(5) for t in TURNOS
        )
        self.ventana.cliente.en_segundo_plano("GET", "/cobertura/fechas", hecho=self._construir, fallo=self.ventana.error)

    def _construir(self, excepciones: list[dict]) -> None:
        for grupo in self._grupos:
            self.remove(grupo)
        self._grupos = [self._grupo_semanal(), *self._grupos_excepciones(excepciones)]
        for grupo in self._grupos:
            self.add(grupo)

    def _grupo_semanal(self) -> Adw.PreferencesGroup:
        grupo = Adw.PreferencesGroup(
            title="Médicos necesarios por turno",
            description="El mínimo es obligatorio: el calendario avisa de cualquier turno por debajo. El máximo no se "
            "supera salvo por turnos fijos o cambios a mano. Los cambios se guardan solos.",
        )
        cuadricula = Gtk.Grid(column_spacing=6, row_spacing=6, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        columnas = [(t, MITADES[t] if not self._por_mitades else (h,)) for t in TURNOS
                    for h in ((None,) if not self._por_mitades else MITADES[t])]
        col = 1
        for turno, mitades in columnas:
            etiqueta = NOMBRE_TURNO[turno] + (f" · {MITAD_CORTA[mitades[0]]} mitad" if self._por_mitades else "")
            cuadricula.attach(Gtk.Label(label=etiqueta, css_classes=["caption-heading", "titulo-turno", turno.lower()]), col, 0, 2, 1)
            cuadricula.attach(Gtk.Label(label="Mín.", css_classes=["caption", "dim-label"]), col, 1, 1, 1)
            cuadricula.attach(Gtk.Label(label="Máx.", css_classes=["caption", "dim-label"]), col + 1, 1, 1, 1)
            col += 2
        for d in range(5):
            cuadricula.attach(Gtk.Label(label=DIAS[d], xalign=0), 0, d + 2, 1, 1)
            col = 1
            for _turno, mitades in columnas:
                for campo in ("minimo", "maximo"):
                    numero = Numero(self._valores[d, mitades[0]][campo],
                                    lambda v, d=d, m=mitades, c=campo: self._cambiar(d, m, c, v))
                    numero.set_tooltip_text(f"{DIAS[d]}, {campo == 'minimo' and 'mínimo' or 'máximo'}")
                    cuadricula.attach(numero, col, d + 2, 1, 1)
                    col += 1
        fila = Adw.PreferencesRow(activatable=False, child=Gtk.ScrolledWindow(
            child=cuadricula, vscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True))
        grupo.add(fila)
        mitades = Adw.SwitchRow(title="Detallar por mitades de turno", active=self._por_mitades,
                                subtitle="Útil con jornadas de turno y medio, que cubren solo media tarde o media mañana")
        mitades.connect("notify::active", lambda r, _p: self._alternar_mitades(r.get_active()))
        grupo.add(mitades)
        copiar = Adw.ButtonRow(title="Copiar el lunes a toda la semana", start_icon_name="edit-copy-symbolic")
        copiar.connect("activated", lambda _r: self._copiar_lunes())
        grupo.add(copiar)
        return grupo

    def _cambiar(self, d: int, mitades, campo: str, valor: int) -> None:
        for h in mitades:
            actual = self._valores[d, h]
            actual[campo] = valor
            if campo == "minimo" and actual["maximo"] < valor:
                actual["maximo"] = valor
                self._guardar.programar(True)  # hay que redibujar para ver el máximo ajustado
                return
            if campo == "maximo" and actual["minimo"] > valor:
                actual["minimo"] = valor
                self._guardar.programar(True)
                return
        self._guardar.programar(False)

    def _alternar_mitades(self, activo: bool) -> None:
        if activo != self._por_mitades:
            self._por_mitades = activo
            GLib.idle_add(lambda: self._construir(self._excepciones) and False)

    def _copiar_lunes(self) -> None:
        for d in range(1, 5):
            for t in TURNOS:
                for h in MITADES[t]:
                    self._valores[d, h] = dict(self._valores[0, h])
        self._enviar_semanal(True)

    def _enviar_semanal(self, redibujar: bool) -> None:
        lista = [{"dia_semana": d, "mitad": h, **self._valores[d, h]} for d in range(5) for t in TURNOS for h in MITADES[t]]

        def hecho(_r):
            self.ventana.aviso("Cobertura guardada")
            self.ventana.invalidar(self)
            if redibujar:
                self._construir(self._excepciones)

        self.ventana.cliente.en_segundo_plano("PUT", "/cobertura/semanal", lista, hecho=hecho, fallo=self.ventana.error)

    # --- Excepciones por fecha -----------------------------------------------------------

    def _grupos_excepciones(self, filas: list[dict]) -> list:
        self._excepciones = filas
        nueva = Adw.PreferencesGroup(
            title="Excepciones por fecha",
            description="Sustituyen la cobertura semanal en un día concreto, por ejemplo con plantilla reducida el 24 de diciembre.",
        )
        valores = {"MANANA": {"minimo": 1, "maximo": 1}, "TARDE": {"minimo": 1, "maximo": 1}}
        fecha_fila = Adw.ActionRow(title="Fecha")
        selector = SelectorFecha(None, lambda _d: None)
        fecha_fila.add_suffix(selector)
        nueva.add(fecha_fila)
        for t in TURNOS:
            fila = Adw.ActionRow(title=NOMBRE_TURNO[t])
            for campo, texto in (("minimo", "mín."), ("maximo", "máx.")):
                fila.add_suffix(Gtk.Label(label=texto, css_classes=["dim-label"]))
                fila.add_suffix(Numero(1, lambda v, t=t, c=campo: valores[t].__setitem__(c, v)))
            nueva.add(fila)
        guardar = Adw.ButtonRow(title="Guardar excepción", start_icon_name="list-add-symbolic")
        guardar.connect("activated", lambda _r: self._guardar_excepcion(selector.fecha(), valores))
        nueva.add(guardar)

        lista = Adw.PreferencesGroup(title="Excepciones guardadas")
        por_fecha: dict[str, dict] = {}
        for c in filas:
            por_fecha.setdefault(c["fecha"], {})[c["mitad"]] = c
        for f, mitades in sorted(por_fecha.items()):
            def rango(a, b):
                texto = lambda v: f"{v['minimo']}–{v['maximo']}" if v else "?"  # noqa: E731
                return texto(a) if texto(a) == texto(b) else f"{texto(a)} / {texto(b)}"
            fila = Adw.ActionRow(
                title=fecha_corta(f),
                subtitle=f"Mañana {rango(mitades.get('M1'), mitades.get('M2'))} · Tarde {rango(mitades.get('T1'), mitades.get('T2'))}",
            )
            quitar = Gtk.Button(icon_name="user-trash-symbolic", css_classes=["flat"], valign=Gtk.Align.CENTER,
                                tooltip_text=f"Quitar la excepción del {fecha_corta(f)}")
            quitar.connect("clicked", lambda _b, f=f: self._quitar_excepcion(f))
            fila.add_suffix(quitar)
            lista.add(fila)
        if not por_fecha:
            lista.add(Adw.ActionRow(title="No hay excepciones"))
        return [nueva, lista]

    def _guardar_excepcion(self, fecha: date | None, valores: dict) -> None:
        if fecha is None:
            self.ventana.error("Elige la fecha de la excepción")
            return
        mitades = [{"mitad": h, **valores[t]} for t in TURNOS for h in MITADES[t]]
        self.ventana.cliente.en_segundo_plano(
            "PUT", f"/cobertura/fechas/{fecha.isoformat()}", mitades,
            hecho=lambda _r: self._recargar("Excepción guardada"), fallo=self.ventana.error,
        )

    def _quitar_excepcion(self, fecha: str) -> None:
        self.ventana.cliente.en_segundo_plano(
            "DELETE", f"/cobertura/fechas/{fecha}", hecho=lambda _r: self._recargar("Excepción quitada"), fallo=self.ventana.error
        )

    def _recargar(self, aviso: str) -> None:
        self.ventana.aviso(aviso)
        self.ventana.invalidar(self)
        self.cargar()
