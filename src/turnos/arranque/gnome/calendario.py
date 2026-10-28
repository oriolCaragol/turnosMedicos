"""Calendario del mes: cuadrícula o lista, generar, deshacer, arrastrar y soltar,
publicar, exportar, imprimir y retoques por turno."""

from collections import defaultdict
from datetime import date

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango

from turnos.arranque.gnome.comun import (
    DIAS,
    MITADES,
    NOMBRE_TURNO,
    OTRO_TURNO,
    TURNOS,
    aplicar_colores,
    cifra,
    mitades_con_valor,
    nombre_corto,
    nombre_mes,
    valor_en_turno,
)

ESTADOS = {"SIN_GENERAR": "Sin generar", "BORRADOR": "Borrador", "PUBLICADO": "Publicado"}
LIMITE_HISTORIAL = 50


def mitades_de(cal: dict, medico: int, fecha: str) -> set[str]:
    return {a["mitad"] for a in cal["asignaciones"] if a["medico_id"] == medico and a["fecha"] == fecha}


def cambios_al_soltar(cal: dict, origen: dict, destino: dict | None, copiar: bool = False) -> list[dict]:
    """Cambios que produce soltar un médico arrastrado (como en la web, especificaciones 7):
    de un turno a otro lo mueve (con Ctrl, lo copia); desde la tabla de carga lo añade;
    fuera de cualquier turno lo quita del de origen."""
    medico = origen["medico"]
    por_fecha: dict[str, set[str]] = {}

    def actuales(fecha):
        if fecha not in por_fecha:
            por_fecha[fecha] = mitades_de(cal, medico, fecha)
        return por_fecha[fecha]

    if origen["tipo"] == "celda":
        if destino and destino["fecha"] == origen["fecha"] and destino["turno"] == origen["turno"]:
            return []
        if not copiar or destino is None:
            actuales(origen["fecha"]).difference_update(MITADES[origen["turno"]])
    if destino:
        ya = set(MITADES[destino["turno"]]) <= mitades_de(cal, medico, destino["fecha"])
        if ya and origen["tipo"] == "resumen":
            return []
        actuales(destino["fecha"]).update(MITADES[destino["turno"]])
    return [
        {"medico_id": medico, "fecha": fecha, "mitades": sorted(mitades)}
        for fecha, mitades in por_fecha.items() if mitades != mitades_de(cal, medico, fecha)
    ]


def foto(cal: dict) -> dict:
    """Estado manual del mes, para deshacer (PUT /manual)."""
    return {"asignaciones": cal["asignaciones"], "vetos": cal["vetos"], "roles": cal.get("roles", [])}


def estado_turno(cal: dict, fecha: str, turno: str) -> str:
    estado = "cubierto"
    for h in MITADES[turno]:
        cob = next((c for c in cal["cobertura"] if c["fecha"] == fecha and c["mitad"] == h), None)
        if not cob:
            continue
        n = sum(1 for a in cal["asignaciones"] if a["fecha"] == fecha and a["mitad"] == h)
        if n < cob["minimo"]:
            return "falta"
        if n > cob["maximo"]:
            estado = "sobra"
    return estado


def turno_bloqueado(cal: dict, fecha: str, turno: str) -> bool:
    return (
        any(a["fecha"] == fecha and a["bloqueada"] and a["mitad"] in MITADES[turno] for a in cal["asignaciones"])
        or any(v["fecha"] == fecha and v["turno"] == turno for v in cal["vetos"])
        or (turno == "TARDE" and any(r["fecha"] == fecha and r["manual"] for r in cal.get("roles", [])))
    )


def _ctrl_pulsado() -> bool:
    teclado = Gdk.Display.get_default().get_default_seat().get_keyboard()
    return bool(teclado and teclado.get_modifier_state() & Gdk.ModifierType.CONTROL_MASK)


class PaginaCalendario(Gtk.ScrolledWindow):
    def __init__(self, ventana) -> None:
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.ventana = ventana
        self.pendiente = True
        self.cal: dict | None = None
        self.estado_general: dict | None = None
        self.ajustes: dict = {}
        self._dialogo = None
        self._enviando = 0  # peticiones de cambio en curso
        self._cola: list[tuple] = []  # cambios esperando a que termine el anterior
        self._atras: list[dict] = []
        self._adelante: list[dict] = []
        self._mes_historial = None
        self._vista = "cuadricula"

        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, margin_top=18, margin_bottom=24)
        self.clamp = Adw.Clamp(maximum_size=1400, tightening_threshold=1000, child=caja, margin_start=12, margin_end=12)
        self.set_child(self.clamp)

        # Barra superior: estado y cifras; acciones (en ventanas estrechas, en dos líneas).
        self.barra = Gtk.Box(spacing=12)
        informacion = Gtk.Box(spacing=12, hexpand=True)
        self._estado = Gtk.Label(css_classes=["estado-mes"], valign=Gtk.Align.CENTER)
        self._resumen = Gtk.Label(css_classes=["dim-label"], wrap=True, xalign=0)
        informacion.append(self._estado)
        informacion.append(self._resumen)
        self.barra.append(informacion)
        botones = Adw.WrapBox(child_spacing=8, line_spacing=8, halign=Gtk.Align.END, valign=Gtk.Align.CENTER)
        self.barra.append(botones)
        historial = Gtk.Box(css_classes=["linked"])
        self._deshacer = Gtk.Button(icon_name="edit-undo-symbolic", tooltip_text="Deshacer (Ctrl+Z)")
        self._deshacer.connect("clicked", lambda _b: self.deshacer())
        self._rehacer = Gtk.Button(icon_name="edit-redo-symbolic", tooltip_text="Rehacer (Ctrl+Y)")
        self._rehacer.connect("clicked", lambda _b: self.rehacer())
        historial.append(self._deshacer)
        historial.append(self._rehacer)
        self._historial = historial
        self._exportar = Gtk.MenuButton(label="Exportar", menu_model=self._menu_exportar())
        self._publicar = Gtk.Button()
        self._publicar.connect("clicked", lambda _b: self._publicar_o_reabrir())
        self._generar = Adw.SplitButton(css_classes=["suggested-action"], menu_model=self._menu_generar(),
                                        dropdown_tooltip="Más opciones de generación")
        self._generar.connect("clicked", lambda _b: self._generar_mes(False))
        for widget in (ventana.selector_mes(), historial, self._exportar, self._publicar, self._generar):
            botones.append(widget)
        caja.append(self.barra)

        # Debajo de la barra: los días y, debajo o al lado (en monitores anchos), los
        # problemas y la carga por médico.
        self.contenido = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        izquierda = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, hexpand=True)
        self.lateral = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.contenido.append(izquierda)
        self.contenido.append(self.lateral)
        caja.append(self.contenido)
        self._problemas = Adw.PreferencesGroup()
        self.lateral.append(self._problemas)

        # Vista: cuadrícula de lunes a viernes o lista de días (en ventanas estrechas, siempre lista).
        barra_vista = Gtk.Box(halign=Gtk.Align.END, spacing=8)
        barra_vista.append(Gtk.Label(label="Vista", css_classes=["caption-heading", "dim-label"]))
        self._selector_vista = Adw.ToggleGroup()
        self._selector_vista.add(Adw.Toggle(name="cuadricula", label="Cuadrícula"))
        self._selector_vista.add(Adw.Toggle(name="lista", label="Lista"))
        self._selector_vista.set_active_name("cuadricula")
        self._selector_vista.connect("notify::active-name", lambda g, _p: self._cambiar_vista(g.get_active_name()))
        barra_vista.append(self._selector_vista)
        self.barra_vista = barra_vista
        izquierda.append(barra_vista)
        self.cuadricula = Gtk.Grid(column_spacing=8, row_spacing=8, column_homogeneous=True)
        self.lista = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, visible=False)
        izquierda.append(self.cuadricula)
        izquierda.append(self.lista)

        self._carga = Adw.PreferencesGroup()
        self.lateral.append(self._carga)

        acciones = Gio.SimpleActionGroup()
        for nombre, funcion in [
            ("exportar-calendario", lambda: self._exportar_xlsx("exportar.xlsx", "turnos")),
            ("exportar-roles", lambda: self._exportar_xlsx("urgencias-domicilios.xlsx", "urgencias-domicilios")),
            ("imprimir-calendario", lambda: self._imprimir("calendario")),
            ("imprimir-roles", lambda: self._imprimir("roles")),
            ("alternativa", lambda: self._generar_mes(True)),
            ("liberar-mes", lambda: self._liberar({}, "Todo el mes vuelve a ser automático")),
            ("deshacer", self.deshacer),
            ("rehacer", self.rehacer),
        ]:
            a = Gio.SimpleAction(name=nombre)
            a.connect("activate", lambda *_a, f=funcion: f())
            acciones.add_action(a)
        self.insert_action_group("cal", acciones)
        atajos = Gtk.ShortcutController(scope=Gtk.ShortcutScope.GLOBAL)
        for teclas, accion in [("<Control>z", "cal.deshacer"), ("<Control>y", "cal.rehacer"), ("<Control><Shift>z", "cal.rehacer")]:
            atajos.add_shortcut(Gtk.Shortcut(trigger=Gtk.ShortcutTrigger.parse_string(teclas),
                                             action=Gtk.ShortcutAction.parse_string(f"action({accion})")))
        self.add_controller(atajos)

    @staticmethod
    def _menu_exportar() -> Gio.Menu:
        menu = Gio.Menu()
        hojas = Gio.Menu()
        hojas.append("Calendario (hoja de cálculo)", "cal.exportar-calendario")
        hojas.append("Urgencias y domicilios (hoja de cálculo)", "cal.exportar-roles")
        menu.append_section(None, hojas)
        imprimir = Gio.Menu()
        imprimir.append("Imprimir calendario…", "cal.imprimir-calendario")
        imprimir.append("Imprimir urgencias y domicilios…", "cal.imprimir-roles")
        menu.append_section(None, imprimir)
        return menu

    @staticmethod
    def _menu_generar() -> Gio.Menu:
        menu = Gio.Menu()
        menu.append("Generar alternativa", "cal.alternativa")
        menu.append("Volver a automático todo el mes", "cal.liberar-mes")
        return menu

    @property
    def _ruta(self) -> str:
        return f"/periodos/{self.ventana.mes.year}/{self.ventana.mes.month}"

    @property
    def editable(self) -> bool:
        return bool(self.cal) and self.cal["estado"] != "PUBLICADO"

    # --- Datos ----------------------------------------------------------------------

    def cargar(self) -> None:
        if self._mes_historial != self.ventana.mes:
            self._mes_historial = self.ventana.mes
            self._atras, self._adelante = [], []
        cliente = self.ventana.cliente
        cliente.en_segundo_plano("GET", "/estado", hecho=lambda e: setattr(self, "estado_general", e), fallo=lambda _m: None)

        def con_ajustes(ajustes):
            self.ajustes = ajustes
            cliente.en_segundo_plano("GET", self._ruta, hecho=self._mostrar, fallo=self.ventana.error)

        # Primero los ajustes (qué mostrar), después el calendario.
        cliente.en_segundo_plano("GET", "/ajustes", hecho=con_ajustes, fallo=lambda _m: con_ajustes(self.ajustes))

    def _mostrar(self, cal: dict) -> None:
        self.cal = cal
        aplicar_colores(cal["medicos"])
        estado = cal["estado"]
        self._estado.set_label(ESTADOS.get(estado, estado))
        self._estado.set_css_classes(["estado-mes", estado.lower().replace("_", "-")])
        self._resumen.set_label(self._cifras(cal))
        generado = estado != "SIN_GENERAR"
        self._generar.set_label("Generar calendario" if not generado else "Regenerar")
        self._generar.set_sensitive(self.editable)
        self._generar.set_dropdown_tooltip("Más opciones de generación")
        self._historial.set_visible(self.editable)
        self._deshacer.set_sensitive(bool(self._atras))
        self._rehacer.set_sensitive(bool(self._adelante))
        self._publicar.set_label("Reabrir" if estado == "PUBLICADO" else "Publicar")
        self._publicar.set_visible(generado)
        self._exportar.set_sensitive(generado)
        self._mostrar_problemas(cal)
        self._mostrar_dias(cal)
        self._mostrar_carga(cal)
        if self._dialogo is not None:
            self._dialogo.actualizar(cal)

    @staticmethod
    def _cifras(cal: dict) -> str:
        laborables = [d for d in cal["dias"] if not d["festivo"]]
        festivos = len(cal["dias"]) - len(laborables)
        partes = [f"{len(laborables)} días laborables", f"{2 * len(laborables)} turnos"]
        if cal["estado"] != "SIN_GENERAR":
            estados = [estado_turno(cal, d["fecha"], t) for d in laborables for t in TURNOS]
            partes += [f"{estados.count('falta')} bajo el mínimo", f"{estados.count('sobra')} sobre el máximo"]
        partes.append(f"{festivos} {'festivo' if festivos == 1 else 'festivos'} entre semana")
        if cal["estado"] != "SIN_GENERAR":
            bloqueados = sum(turno_bloqueado(cal, d["fecha"], t) for d in laborables for t in TURNOS)
            partes.append(f"{bloqueados} {'turno bloqueado' if bloqueados == 1 else 'turnos bloqueados'}")
        return " · ".join(partes)

    def _reemplazar(self, viejo: Gtk.Widget, nuevo: Gtk.Widget) -> None:
        caja = viejo.get_parent()
        caja.insert_child_after(nuevo, viejo)
        caja.remove(viejo)

    def _mostrar_problemas(self, cal: dict) -> None:
        nuevo = Adw.PreferencesGroup(title="Problemas a resolver")
        mes = nombre_mes(self.ventana.mes).lower()
        filas = []
        activos = [m for m in cal["medicos"] if m["activo"]]
        if not activos:
            filas.append(("dialog-information-symbolic", "Aún no hay médicos", "Añádelos en «Médicos y reglas»."))
        estado = self.estado_general
        if estado and not estado["cobertura_definida"]:
            filas.append(("dialog-warning-symbolic", "No se ha definido cuántos médicos necesita cada turno",
                          "Defínelo en la pestaña «Cobertura»."))
        sin_carga = [m["nombre"] for m in activos if not m["con_carga"]]
        if sin_carga:
            todos = len(sin_carga) == len(activos)
            filas.append(("dialog-error-symbolic" if todos else "dialog-warning-symbolic",
                          f"Sin carga mensual en {mes}: no recibirán turnos",
                          ", ".join(sin_carga) + ". Indica sus turnos/mes en «Médicos y reglas»."))
        if estado and self.ventana.mes.year in estado["anios_festivos_incompletos"]:
            filas.append(("dialog-warning-symbolic", f"Faltan festivos por publicar en {self.ventana.mes.year}",
                          "Normalmente las dos fiestas locales: búscalas en «Configuración» o revisa «Festivos»."))
        causas = [a for a in cal["avisos"] if a["tipo"] == "CAUSA"]
        usadas = set()
        incumplimientos = [a for a in cal["avisos"] if a["tipo"] == "INCUMPLIMIENTO"]
        for a in incumplimientos:
            i = next((j for j, c in enumerate(causas) if j not in usadas and c["fecha"] and c["fecha"] == a["fecha"]), None)
            if i is not None:
                usadas.add(i)
            critico = "falta" in a["mensaje"] or "por debajo" in a["mensaje"]
            filas.append(("dialog-error-symbolic" if critico else "dialog-warning-symbolic", a["mensaje"],
                          f"Causa: {causas[i]['mensaje']}" if i is not None else ""))
        for j, c in enumerate(causas):
            if j not in usadas:
                filas.append(("dialog-information-symbolic", c["mensaje"], ""))
        if not filas and cal["estado"] != "SIN_GENERAR":
            filas.append(("emblem-ok-symbolic", "Todos los turnos cumplen su cobertura y las reglas", ""))
        if len(filas) > 6:
            expansor = Adw.ExpanderRow(title=f"{len(filas)} avisos", icon_name="dialog-warning-symbolic",
                                       subtitle="Pulsa para verlos todos")
            for icono, titulo, subtitulo in filas:
                expansor.add_row(Adw.ActionRow(title=GLib.markup_escape_text(titulo), subtitle=GLib.markup_escape_text(subtitulo),
                                               icon_name=icono, title_lines=3, subtitle_lines=3))
            nuevo.add(expansor)
        else:
            for icono, titulo, subtitulo in filas:
                nuevo.add(Adw.ActionRow(title=GLib.markup_escape_text(titulo), subtitle=GLib.markup_escape_text(subtitulo),
                                        icon_name=icono, title_lines=3, subtitle_lines=3))
        nuevo.set_visible(bool(filas))
        self._reemplazar(self._problemas, nuevo)
        self._problemas = nuevo

    # --- Días ---------------------------------------------------------------------------

    def _cambiar_vista(self, vista: str | None) -> None:
        if vista:
            self._vista = vista
            self.cuadricula.set_visible(vista == "cuadricula")
            self.lista.set_visible(vista == "lista")

    def _mostrar_dias(self, cal: dict) -> None:
        for contenedor in (self.cuadricula, self.lista):
            while (hijo := contenedor.get_first_child()) is not None:
                contenedor.remove(hijo)
        for col, dia in enumerate(DIAS[:5]):
            self.cuadricula.attach(Gtk.Label(label=dia, css_classes=["caption-heading", "dim-label"], xalign=0), col, 0, 1, 1)
        if not cal["dias"]:
            return
        primero = date.fromisoformat(cal["dias"][0]["fecha"])
        for d in cal["dias"]:
            fecha = date.fromisoformat(d["fecha"])
            fila = 1 + ((fecha - primero).days + primero.weekday()) // 7
            self.cuadricula.attach(self._celda(cal, d, fecha), fecha.weekday(), fila, 1, 1)
            self.lista.append(self._celda(cal, d, fecha, con_dia=True))

    def _celda(self, cal: dict, d: dict, fecha: date, con_dia: bool = False) -> Gtk.Widget:
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, css_classes=["dia"])
        cabecera = Gtk.Box(spacing=6)
        texto = f"{DIAS[fecha.weekday()]} {fecha.day}" if con_dia else str(fecha.day)
        cabecera.append(Gtk.Label(label=texto, css_classes=["numero-dia"], xalign=0))
        caja.append(cabecera)
        if d["festivo"]:
            caja.add_css_class("festivo")
            cabecera.append(Gtk.Label(label="Festivo", css_classes=["caption", "dim-label"], hexpand=True, xalign=1))
            caja.append(Gtk.Label(label=d["festivo"], wrap=True, xalign=0, css_classes=["caption", "dim-label"]))
            return caja
        papeles = {(r["medico_id"], r["fecha"]): r["rol"] for r in cal.get("roles", [])}
        for turno in TURNOS:
            caja.append(self._turno(cal, d["fecha"], turno, papeles))
        return caja

    def _turno(self, cal: dict, fecha: str, turno: str, papeles: dict) -> Gtk.Widget:
        mitades = {m["id"]: mitades_de(cal, m["id"], fecha) for m in cal["medicos"]}
        medicos = [m for m in cal["medicos"] if mitades[m["id"]] & set(MITADES[turno])]
        cobs = [c for c in cal["cobertura"] if c["fecha"] == fecha and c["mitad"] in MITADES[turno]]
        n = sum(valor_en_turno(mitades[m["id"]], turno) for m in medicos)
        boton = Gtk.Button(css_classes=["flat", "turno", f"turno-{turno.lower()}", estado_turno(cal, fecha, turno)],
                           tooltip_text=f"{NOMBRE_TURNO[turno]}: pulsa para cambiar quién lo hace, o arrastra médicos aquí")
        interior = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        titulo = Gtk.Box()
        titulo.append(Gtk.Label(label=NOMBRE_TURNO[turno].upper(), css_classes=["titulo-turno", turno.lower()], hexpand=True, xalign=0))
        if turno_bloqueado(cal, fecha, turno):
            titulo.append(Gtk.Image(icon_name="changes-prevent-symbolic", pixel_size=12, tooltip_text="Cambiado a mano",
                                    margin_end=4, css_classes=["dim-label"]))
        minimo = max((c["minimo"] for c in cobs), default=0)
        maximo = max((c["maximo"] for c in cobs), default=0)
        necesarios = str(minimo) if minimo == maximo else f"{minimo}–{maximo}"
        if self.ajustes.get("mostrar_cobertura"):
            titulo.append(Gtk.Label(label=f"{cifra(round(n * 2))}/{necesarios}", css_classes=["caption", "dim-label", "numeric"],
                                    tooltip_text="Médicos asignados / necesarios"))
        interior.append(titulo)
        fichas = Adw.WrapBox(child_spacing=3, line_spacing=3)
        bloqueadas = {a["medico_id"] for a in cal["asignaciones"] if a["fecha"] == fecha and a["bloqueada"]}
        for m in sorted(medicos, key=lambda m: m["nombre"]):
            fichas.append(self._ficha(m, mitades[m["id"]], fecha, turno, papeles.get((m["id"], fecha)), m["id"] in bloqueadas))
        if not medicos:
            fichas.append(Gtk.Label(label="nadie", css_classes=["caption", "dim-label"]))
        interior.append(fichas)
        boton.set_child(interior)
        boton.connect("clicked", lambda _b: self._abrir_turno(fecha, turno))
        if self.editable:
            destino = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE | Gdk.DragAction.COPY)
            destino.connect("drop", lambda _t, valor, _x, _y: self._soltar(valor, {"fecha": fecha, "turno": turno}))
            destino.connect("enter", lambda *_a: (boton.add_css_class("destino"), Gdk.DragAction.MOVE)[1])
            destino.connect("leave", lambda *_a: boton.remove_css_class("destino"))
            boton.add_controller(destino)
        return boton

    def _ficha(self, medico, mitades, fecha, turno, papel, bloqueada) -> Gtk.Widget:
        caja = Gtk.Box(spacing=3, css_classes=["ficha", f"medico-{medico['id']}"])
        medio = valor_en_turno(mitades, turno) == 0.5
        doble = valor_en_turno(mitades, OTRO_TURNO[turno]) > 0
        caja.append(Gtk.Label(label=nombre_corto(medico["nombre"]) + (" ½" if medio else ""),
                              ellipsize=Pango.EllipsizeMode.END, max_width_chars=14))
        if doble:
            caja.add_css_class("doble")
        if turno == "TARDE" and papel:
            insignia = Gtk.Box(css_classes=["papel", papel.lower()], valign=Gtk.Align.CENTER)
            insignia.append(Gtk.Image(icon_name=f"turnos-{papel.lower()}", pixel_size=11))
            caja.append(insignia)
        if bloqueada:
            caja.append(Gtk.Image(icon_name="changes-prevent-symbolic", pixel_size=10))
        partes = [medico["nombre"], "medio turno" if medio else "", "también el otro turno" if doble else "",
                  {"URGENCIAS": "urgencias", "DOMICILIOS": "domicilios"}.get(papel or "", ""), "cambiado a mano" if bloqueada else ""]
        caja.set_tooltip_text(" · ".join(p for p in partes if p))
        if self.editable:
            self._arrastrable(caja, {"tipo": "celda", "medico": medico["id"], "fecha": fecha, "turno": turno})
        return caja

    # --- Arrastrar y soltar ------------------------------------------------------------

    def _arrastrable(self, widget: Gtk.Widget, origen: dict) -> None:
        fuente = Gtk.DragSource(actions=Gdk.DragAction.MOVE | Gdk.DragAction.COPY)
        clave = "|".join(str(origen.get(k, "")) for k in ("tipo", "medico", "fecha", "turno"))
        fuente.connect("prepare", lambda *_a: Gdk.ContentProvider.new_for_value(clave))
        fuente.connect("drag-begin", lambda f, _d: f.set_icon(Gtk.WidgetPaintable.new(widget), 10, 10))
        fuente.connect("drag-cancel", self._cancelado, origen)
        widget.add_controller(fuente)

    def _cancelado(self, _fuente, _drag, motivo, origen: dict) -> bool:
        # Soltar fuera de cualquier turno quita al médico del de origen (como en la web).
        if motivo == Gdk.DragCancelReason.NO_TARGET and origen["tipo"] == "celda" and self.cal:
            self._cambiar(cambios_al_soltar(self.cal, origen, None))
        return False

    def _soltar(self, valor: str, destino: dict) -> bool:
        if not self.cal:
            return False
        tipo, medico, fecha, turno = valor.split("|")
        origen = {"tipo": tipo, "medico": int(medico), "fecha": fecha, "turno": turno}
        self._cambiar(cambios_al_soltar(self.cal, origen, destino, copiar=_ctrl_pulsado()))
        return True

    # --- Carga por médico ---------------------------------------------------------------

    def _mostrar_carga(self, cal: dict) -> None:
        """Tabla de carga por médico, como en la web: turnos del mes frente al rango,
        días de turno y medio, dobles, urgencias y domicilios."""
        nuevo = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        nuevo.append(Gtk.Label(label="Carga por médico", xalign=0, css_classes=["heading"]))
        # Según la presencia no hay rangos: ni columna, ni ajuste del mes, ni «fuera de rango».
        rangos = cal.get("carga_por_rangos", True)
        nuevo.append(Gtk.Label(
            label=("Turnos del mes frente al rango de cada médico, ya ajustado por sus ausencias. " if rangos
                   else "Turnos del mes de cada médico: trabaja todos los días salvo ausencia. ")
            + "Arrastra un nombre al calendario para añadirlo a un turno.",
            xalign=0, wrap=True, css_classes=["dim-label", "caption"]))
        tabla = Gtk.Grid(css_classes=["tabla-carga"], column_spacing=0, row_spacing=0)
        columnas = [("Médico", ""), ("Total", ""), ("M", "Mañanas"), ("T", "Tardes"),
                    *([("Rango", "Rango del mes")] if rangos else []),
                    ("Días 1½", "Días de turno y medio"), ("Dobles", "Días de mañana y tarde"),
                    ("Urg.", "Tardes de urgencias en el mes"), ("Dom.", "Tardes de domicilios en el mes"), ("", "")]
        for col, (texto, ayuda) in enumerate(columnas):
            etiqueta = Gtk.Label(label=texto, xalign=0 if col == 0 else 1, css_classes=["celda", "cabecera-tabla"],
                                 tooltip_text=ayuda or None, hexpand=col == 0)
            tabla.attach(etiqueta, col, 0, 1, 1)
        medicos = [m for m in sorted(cal["medicos"], key=lambda m: m["nombre"]) if m["activo"] or m["asignado"]]
        for fila, m in enumerate(medicos, start=1):
            medio = doble = 0
            for d in cal["dias"]:
                n = len(mitades_de(cal, m["id"], d["fecha"]))
                medio += n == 3
                doble += n == 4
            fuera = rangos and m["con_carga"] and not (m["minimo"] <= m["asignado"] <= m["maximo"])
            ficha = Gtk.Box(css_classes=["ficha", f"medico-{m['id']}"], halign=Gtk.Align.START,
                            tooltip_text=f"{m['nombre']}: arrastra a un turno para añadirlo" if self.editable else m["nombre"])
            ficha.append(Gtk.Label(label=m["nombre"], ellipsize=Pango.EllipsizeMode.END, max_width_chars=22))
            if self.editable and m["activo"]:
                self._arrastrable(ficha, {"tipo": "resumen", "medico": m["id"]})
            celda_nombre = Gtk.Box(css_classes=["celda"])
            celda_nombre.append(ficha)
            tabla.attach(celda_nombre, 0, fila, 1, 1)
            if m["con_carga"]:
                rango = f"{cifra(m['minimo'])}–{cifra(m['maximo'])}" + (" ✎" if m.get("carga_manual") else "")
            else:
                rango = "sin carga"
            tardes = f"Puede trabajar {m.get('tardes_disponibles', 0)} tardes este mes"
            valores = [
                (cifra(m["asignado"]), ["fuera-de-rango"] if fuera else [], None),
                (cifra(m["asignado_manana"]), [], None),
                (cifra(m["asignado_tarde"]), [], None),
                *([(rango, [] if m["con_carga"] else ["dim-label"],
                    "Rango ajustado a mano para este mes" if m.get("carga_manual") else None)] if rangos else []),
                (str(medio), [], None),
                (str(doble), [], None),
                (str(m.get("urgencias", 0)), [], tardes),
                (str(m.get("domicilios", 0)), [], tardes),
            ]
            for col, (texto, clases, ayuda) in enumerate(valores, start=1):
                tabla.attach(Gtk.Label(label=texto, xalign=1, css_classes=["celda", "numeric", *clases], tooltip_text=ayuda),
                             col, fila, 1, 1)
            celda_accion = Gtk.Box(css_classes=["celda"])
            if rangos and self.editable and m["con_carga"]:
                ajustar = Gtk.Button(icon_name="document-edit-symbolic", css_classes=["flat", "circular"],
                                     tooltip_text="Ajustar el rango de este mes", valign=Gtk.Align.CENTER)
                ajustar.connect("clicked", lambda _b, m=m: self._ajustar_rango(m))
                celda_accion.append(ajustar)
            tabla.attach(celda_accion, len(valores) + 1, fila, 1, 1)
        marco = Gtk.ScrolledWindow(child=tabla, vscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True,
                                   css_classes=["card"])
        nuevo.append(marco)
        self._reemplazar(self._carga, nuevo)
        self._carga = nuevo

    def _ajustar_rango(self, medico: dict) -> None:
        from turnos.arranque.gnome.medicos import mostrar_turnos

        dialogo = Adw.AlertDialog(
            heading=f"Rango de {medico['nombre']} en {nombre_mes(self.ventana.mes).lower()}",
            body=f"Solo para este mes. Según sus ausencias le corresponden "
                 f"{cifra(medico['minimo_calculado'])}–{cifra(medico['maximo_calculado'])} turnos.",
        )
        lista = Gtk.ListBox(css_classes=["boxed-list"], selection_mode=Gtk.SelectionMode.NONE)
        campos = {}
        for clave, titulo in (("minimo", "Mínimo"), ("maximo", "Máximo")):
            campo = Adw.SpinRow.new_with_range(0, 40, 0.5)
            campo.set_title(f"{titulo} (turnos)")
            campo.set_digits(1)
            campo.connect("output", mostrar_turnos)
            campo.set_value(medico[clave] / 2)
            campos[clave] = campo
            lista.append(campo)
        dialogo.set_extra_child(lista)
        dialogo.add_response("cancelar", "Cancelar")
        if medico.get("carga_manual"):
            dialogo.add_response("calculado", "Volver al calculado")
        dialogo.add_response("guardar", "Guardar rango")
        dialogo.set_response_appearance("guardar", Adw.ResponseAppearance.SUGGESTED)

        def respuesta(_d, r):
            if r == "guardar":
                minimo, maximo = (round(campos[c].get_value() * 2) for c in ("minimo", "maximo"))
                if maximo < minimo:
                    self.ventana.error("El máximo no puede ser menor que el mínimo")
                    return
                self._enviar("PUT", f"/carga/{medico['id']}", {"minimo": minimo, "maximo": maximo}, "Rango guardado")
            elif r == "calculado":
                self._enviar("PUT", f"/carga/{medico['id']}", {"minimo": None, "maximo": None}, "Rango calculado")

        dialogo.connect("response", respuesta)
        dialogo.present(self.ventana)

    # --- Acciones ---------------------------------------------------------------------

    def _registrar(self) -> None:
        if self.cal and self.cal["estado"] != "SIN_GENERAR":
            self._atras = [*self._atras[-(LIMITE_HISTORIAL - 1):], foto(self.cal)]
            self._adelante = []

    def _cambiar(self, cambios: list[dict]) -> None:
        if not cambios or not self.editable:
            return
        self._registrar()
        self._enviar("POST", "/cambios", cambios)

    def _liberar(self, alcance: dict, aviso: str) -> None:
        self._registrar()
        self._enviar("POST", "/liberar", alcance, aviso)

    def _mover_historial(self, desde: list, hacia: list) -> None:
        if not desde or not self.cal or self._enviando or not self.get_mapped():
            return
        foco = self.ventana.get_focus()
        if isinstance(foco, Gtk.Text):  # Ctrl+Z en un campo de texto es suyo
            return
        objetivo = desde.pop()
        hacia.append(foto(self.cal))
        self._enviar("PUT", "/manual", objetivo)

    def deshacer(self) -> None:
        self._mover_historial(self._atras, self._adelante)

    def rehacer(self) -> None:
        self._mover_historial(self._adelante, self._atras)

    def _generar_mes(self, alternativa: bool) -> None:
        if not self.editable and self.cal:
            return
        self._registrar()
        self._generar.set_sensitive(False)
        self._generar.set_label("Generando…")

        def hecho(cal):
            self._mostrar(cal)
            self.ventana.invalidar(self)
            if not cal["asignaciones"] and any(m["con_carga"] for m in cal["medicos"]):
                self.ventana.error("No se ha podido asignar ningún turno: revisa «Problemas a resolver»")
            else:
                self.ventana.aviso("Alternativa generada" if alternativa else "Calendario generado")

        self._enviar("POST", "/generar", {"alternativa": alternativa}, hecho=hecho)

    def _fallo_accion(self, mensaje: str) -> None:
        self.ventana.error(mensaje)
        if self.cal:
            self._mostrar(self.cal)

    def _publicar_o_reabrir(self) -> None:
        if self.cal and self.cal["estado"] == "PUBLICADO":
            self._enviar("POST", "/reabrir", None, "Calendario reabierto")
            return
        dialogo = Adw.AlertDialog(heading=f"¿Publicar {nombre_mes(self.ventana.mes).lower()}?",
                                  body="El calendario quedará en solo lectura hasta que lo reabras.")
        dialogo.add_response("cancelar", "Cancelar")
        dialogo.add_response("publicar", "Publicar")
        dialogo.set_response_appearance("publicar", Adw.ResponseAppearance.SUGGESTED)
        dialogo.connect("response", lambda _d, r: r == "publicar" and self._enviar("POST", "/publicar", None, "Calendario publicado"))
        dialogo.present(self.ventana)

    def _enviar(self, metodo: str, ruta: str, cuerpo, aviso: str | None = None, hecho=None) -> None:
        """Envía un cambio del mes. Van de uno en uno: cada uno lleva la versión del mes que
        dejó el anterior (X-Version-Mes); si otro usuario lo ha cambiado entretanto, el
        servidor lo rechaza (409) y se muestra la versión actual."""
        self._cola.append((metodo, f"{self._ruta}{ruta}", cuerpo, aviso, hecho))
        if self._enviando == 0:
            self._siguiente()

    def _siguiente(self) -> None:
        if not self._cola:
            return
        metodo, ruta, cuerpo, aviso, al_terminar = self._cola.pop(0)
        self._enviando += 1
        version = {"X-Version-Mes": str(self.cal.get("version", 0))} if self.cal else {}

        def terminar():
            self._enviando -= 1
            self._siguiente()

        def fallo(mensaje):
            self._fallo_accion(mensaje)
            terminar()

        def conflicto(mensaje):
            # Lo que quedaba en la cola se pensó sobre la versión anterior: se descarta.
            self._cola.clear()
            self.cambio_externo()
            self.ventana.error(mensaje)
            terminar()
            self.cargar()

        def hecho(cal):
            if al_terminar:
                al_terminar(cal)
            else:
                self._mostrar(cal)
                self.ventana.invalidar(self)
                if aviso:
                    self.ventana.aviso(aviso)
            terminar()

        self.ventana.cliente.en_segundo_plano(
            metodo, ruta, cuerpo, hecho=hecho, fallo=fallo, conflicto=conflicto, cabeceras=version
        )

    def cambio_externo(self) -> None:
        """Otro usuario ha cambiado este mes: no se deshace lo que hizo otro."""
        self._atras, self._adelante = [], []
        self._deshacer.set_sensitive(False)
        self._rehacer.set_sensitive(False)

    def _exportar_xlsx(self, ruta: str, fichero: str) -> None:
        mes = self.ventana.mes

        def guardar(contenido: bytes) -> None:
            dialogo = Gtk.FileDialog(title="Guardar", initial_name=f"{fichero}-{mes.year}-{mes.month:02d}.xlsx")

            def elegido(d, resultado):
                try:
                    destino = d.save_finish(resultado)
                except GLib.Error:
                    return
                destino.replace_contents(contenido, None, False, Gio.FileCreateFlags.REPLACE_DESTINATION, None)
                self.ventana.aviso(f"Guardado «{destino.get_basename()}»")

            dialogo.save(self.ventana, None, elegido)

        self.ventana.cliente.en_segundo_plano("GET", f"{self._ruta}/{ruta}", hecho=guardar, fallo=self.ventana.error, binario=True)

    def _imprimir(self, informe: str) -> None:
        from turnos.arranque.gnome.imprimir import imprimir

        if not self.cal:
            return
        self.ventana.cliente.en_segundo_plano(
            "GET", "/horarios", hecho=lambda h: imprimir(self.ventana, informe, self.cal, h, self.ventana.mes),
            fallo=self.ventana.error,
        )

    def _abrir_turno(self, fecha: str, turno: str) -> None:
        if not self.cal or self.cal["estado"] == "PUBLICADO":
            self.ventana.aviso("El calendario está publicado: reábrelo para cambiarlo")
            return
        self._dialogo = DialogoTurno(self, fecha, turno)
        self._dialogo.connect("closed", lambda *_: setattr(self, "_dialogo", None))
        self._dialogo.present(self.ventana)


class DialogoTurno(Adw.Dialog):
    """Quién hace un turno: No / ½ / 1 para cada médico y, por la tarde, urgencias o domicilios."""

    def __init__(self, pagina: PaginaCalendario, fecha: str, turno: str) -> None:
        dia = date.fromisoformat(fecha)
        super().__init__(title=f"{DIAS[dia.weekday()]} {dia.day} · {NOMBRE_TURNO[turno]}", content_width=560, content_height=680)
        self.pagina, self.fecha, self.turno = pagina, fecha, turno
        self._actualizando = False
        cabecera = Adw.HeaderBar()
        self._automatico = Gtk.Button(label="Volver a automático", tooltip_text="Quita los cambios a mano de este turno")
        self._automatico.connect("clicked", lambda _b: self.pagina._liberar({"fecha": fecha, "turno": turno}, "Turno devuelto al generador"))
        cabecera.pack_start(self._automatico)
        self._pagina_pref = Adw.PreferencesPage()
        vista = Adw.ToolbarView(content=self._pagina_pref)
        vista.add_top_bar(cabecera)
        self.set_child(vista)
        self._grupo = None
        self.actualizar(pagina.cal)

    def actualizar(self, cal: dict) -> None:
        self._actualizando = True
        if self._grupo is not None:
            self._pagina_pref.remove(self._grupo)
        cobs = [c for c in cal["cobertura"] if c["fecha"] == self.fecha and c["mitad"] in MITADES[self.turno]]
        minimo = max((c["minimo"] for c in cobs), default=0)
        maximo = max((c["maximo"] for c in cobs), default=0)
        mitades = defaultdict(set)
        for a in cal["asignaciones"]:
            if a["fecha"] == self.fecha:
                mitades[a["medico_id"]].add(a["mitad"])
        asignados = sum(valor_en_turno(mitades[m], self.turno) for m in mitades)
        bloqueado = turno_bloqueado(cal, self.fecha, self.turno)
        self._automatico.set_sensitive(bloqueado)
        papeles = {r["medico_id"]: r["rol"] for r in cal.get("roles", []) if r["fecha"] == self.fecha}
        nombres = {m["id"]: m["nombre"] for m in cal["medicos"]}
        texto = f"{cifra(round(asignados * 2))} asignados · mín. {minimo}, máx. {maximo}"
        if self.turno == "TARDE" and papeles:
            quien = {v: nombres.get(k) for k, v in papeles.items()}
            texto += f" · Urgencias: {quien.get('URGENCIAS') or 'nadie'} · Domicilios: {quien.get('DOMICILIOS') or 'nadie'}"
        texto += ". " + ("Bloqueado: el generador lo respeta." if bloqueado else "Cualquier cambio lo bloquea.")
        self._grupo = Adw.PreferencesGroup(description=texto)
        orden = sorted(cal["medicos"], key=lambda m: (not mitades[m["id"]] & set(MITADES[self.turno]), m["nombre"]))
        for m in orden:
            if not m["activo"] and not mitades[m["id"]]:
                continue
            self._grupo.add(self._fila(m, mitades[m["id"]], papeles.get(m["id"])))
        self._pagina_pref.add(self._grupo)
        self._actualizando = False

    def _fila(self, m: dict, mitades: set, papel: str | None) -> Adw.ActionRow:
        no = next((n for n in m["no_elegibles"] if n["fecha"] == self.fecha and n["turno"] == self.turno), None)
        habitual = any(h["fecha"] == self.fecha and h["turno"] == self.turno for h in m.get("habituales", []))
        otro = OTRO_TURNO[self.turno]
        en_otro = valor_en_turno(mitades, otro)
        notas = [
            ("Ausente" if no["motivo"] == "AUSENTE" else "No disponible") if no else ("Turno habitual" if habitual else "Disponible"),
            f"trabaja la {NOMBRE_TURNO[otro].lower()} ({'1' if en_otro == 1 else '½'})" if en_otro else "",
            (f"{cifra(m['asignado'])} turnos" if not self.pagina.cal.get("carga_por_rangos", True)
             else f"{cifra(m['asignado'])} turnos de {cifra(m['minimo'])}–{cifra(m['maximo'])}" if m["con_carga"]
             else "sin carga"),
        ]
        if self.turno == "TARDE" and (m.get("urgencias") or m.get("domicilios")):
            notas.append(f"{m.get('urgencias', 0)} urg. · {m.get('domicilios', 0)} dom. este mes")
        valor = valor_en_turno(mitades, self.turno)
        fila = Adw.ActionRow(title=GLib.markup_escape_text(m["nombre"]), subtitle=" · ".join(n for n in notas if n), subtitle_lines=2)
        fila.add_prefix(Gtk.Box(css_classes=["punto-color", f"color-{m['id']}"], valign=Gtk.Align.CENTER))
        if no and valor > 0:
            fila.add_css_class("error")
        grupo = Adw.ToggleGroup(valign=Gtk.Align.CENTER)
        for nombre, etiqueta in (("0", "No"), ("0.5", "½"), ("1", "1")):
            grupo.add(Adw.Toggle(name=nombre, label=etiqueta))
        grupo.get_toggle_by_name("0.5").set_enabled(en_otro == 1 or valor == 0.5)
        grupo.set_active_name(f"{valor:g}")
        grupo.connect("notify::active-name", self._cambiar_valor, m["id"], mitades)
        fila.add_suffix(grupo)
        if self.turno == "TARDE" and valor == 1:
            selector = Adw.ToggleGroup(valign=Gtk.Align.CENTER, css_classes=["round"])
            selector.add(Adw.Toggle(name="URGENCIAS", label="Urg.", tooltip="Urgencias"))
            selector.add(Adw.Toggle(name="DOMICILIOS", label="Dom.", tooltip="Domicilios"))
            if papel:
                selector.set_active_name(papel)
            else:
                selector.set_active(Gtk.INVALID_LIST_POSITION)
            selector.connect("notify::active-name", self._cambiar_papel, m["id"])
            fila.add_suffix(selector)
        return fila

    def _cambiar_valor(self, grupo, _param, medico_id: int, mitades: set) -> None:
        if self._actualizando:
            return
        nuevas = mitades_con_valor(mitades, self.turno, float(grupo.get_active_name()))
        self.pagina._cambiar([{"medico_id": medico_id, "fecha": self.fecha, "mitades": nuevas}])

    def _cambiar_papel(self, grupo, _param, medico_id: int) -> None:
        if self._actualizando or not grupo.get_active_name():
            return
        self.pagina._cambiar([{"medico_id": medico_id, "fecha": self.fecha, "rol": grupo.get_active_name()}])
