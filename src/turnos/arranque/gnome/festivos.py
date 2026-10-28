"""Festivos del año del mes elegido: añadir y quitar."""

from datetime import date

from gi.repository import Adw, GLib, Gtk

from turnos.arranque.gnome.comun import AMBITOS, DIAS, fecha_corta


class PaginaFestivos(Adw.PreferencesPage):
    def __init__(self, ventana) -> None:
        super().__init__()
        self.ventana = ventana
        self.pendiente = True
        self._grupos = []

        nuevo = Adw.PreferencesGroup(title="Añadir festivo")
        self._fecha = Adw.EntryRow(title="Fecha (dd/mm/aaaa)")
        self._nombre = Adw.EntryRow(title="Nombre")
        self._ambito = Adw.ComboRow(title="Ámbito", model=Gtk.StringList.new([t for _v, t in AMBITOS]), selected=2)
        boton = Gtk.Button(label="Añadir", css_classes=["suggested-action"], halign=Gtk.Align.END, margin_top=8)
        boton.connect("clicked", lambda _b: self._anadir())
        for fila in (self._fecha, self._nombre, self._ambito):
            nuevo.add(fila)
        nuevo.add(boton)
        self._selector = ventana.selector_mes()
        self.add(nuevo)
        self._nuevo = nuevo

    @property
    def _anio(self) -> int:
        return self.ventana.mes.year

    def cargar(self) -> None:
        cliente = self.ventana.cliente
        cliente.en_segundo_plano(
            "GET", "/festivos/anios",
            hecho=lambda anios: cliente.en_segundo_plano(
                "GET", f"/festivos?anio={self._anio}", hecho=lambda f: self._mostrar(f, anios), fallo=self.ventana.error),
            fallo=self.ventana.error,
        )

    def _mostrar(self, festivos: list[dict], anios: list[dict]) -> None:
        for grupo in self._grupos:
            self.remove(grupo)
        grupo = Adw.PreferencesGroup(
            title=f"Festivos de {self._anio}",
            description="Los festivos entre semana no se planifican. Para buscarlos en las fuentes oficiales, ve a Configuración.",
        )
        carga = next((a for a in anios if a["anio"] == self._anio), None)
        sufijo = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        if carga and carga.get("precargado"):
            restaurar = Gtk.Button(label="Restaurar los precargados", css_classes=["flat"],
                                   tooltip_text="Vuelve a añadir los festivos precargados que se hayan quitado")
            restaurar.connect("clicked", lambda _b: self._restaurar())
            sufijo.append(restaurar)
        if (padre := self._selector.get_parent()) is not None:
            padre.remove(self._selector)
        sufijo.append(self._selector)
        grupo.set_header_suffix(sufijo)
        avisos = []
        if carga and not carga["completo"]:
            avisos.append(Adw.ActionRow(
                title=f"Faltan festivos de {self._anio} por publicar",
                subtitle="Normalmente las dos fiestas locales. Búscalas en Configuración → Festivos oficiales cuando se "
                "publiquen, o añádelas aquí.", subtitle_lines=3, icon_name="dialog-warning-symbolic"))
        elif not carga and not festivos:
            avisos.append(Adw.ActionRow(
                title=f"No se han cargado los festivos de {self._anio}",
                subtitle="Búscalos en Configuración → Festivos oficiales, o añádelos aquí.", icon_name="dialog-warning-symbolic"))
        for aviso in avisos:
            grupo.add(aviso)
        nombres = dict(AMBITOS)
        for f in festivos:
            dia = date.fromisoformat(f["fecha"])
            fila = Adw.ActionRow(
                title=GLib.markup_escape_text(f["descripcion"]),
                subtitle=f"{fecha_corta(f['fecha'])} · {DIAS[dia.weekday()]} · {nombres.get(f['ambito'], f['ambito'])}",
            )
            if dia.weekday() > 4:
                fila.set_sensitive(False)
                fila.set_subtitle(fila.get_subtitle() + " (fin de semana)")
            quitar = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Quitar", css_classes=["flat"], valign=Gtk.Align.CENTER)
            quitar.connect("clicked", lambda _b, i=f["id"]: self._quitar(i))
            fila.add_suffix(quitar)
            grupo.add(fila)
        # La lista (con el selector de mes) arriba y el formulario de añadir debajo.
        self.remove(self._nuevo)
        self.add(grupo)
        self.add(self._nuevo)
        self._grupos = [grupo]

    def _anadir(self) -> None:
        try:
            d, m, a = (int(x) for x in self._fecha.get_text().strip().split("/"))
            fecha = date(a, m, d)
        except ValueError:
            self.ventana.error("Escribe la fecha como dd/mm/aaaa")
            return
        datos = {"fecha": fecha.isoformat(), "descripcion": self._nombre.get_text().strip() or "Festivo",
                 "ambito": AMBITOS[self._ambito.get_selected()][0]}

        def hecho(_f):
            self._fecha.set_text("")
            self._nombre.set_text("")
            self._cambiado("Festivo añadido")

        self.ventana.cliente.en_segundo_plano("POST", "/festivos", datos, hecho=hecho, fallo=self.ventana.error)

    def _restaurar(self) -> None:
        def hecho(restaurados):
            self._cambiado(f"Restaurados {len(restaurados)} festivos" if restaurados else "No faltaba ningún festivo")

        self.ventana.cliente.en_segundo_plano("POST", f"/festivos/restaurar/{self._anio}", hecho=hecho, fallo=self.ventana.error)

    def _quitar(self, festivo_id: int) -> None:
        self.ventana.cliente.en_segundo_plano(
            "DELETE", f"/festivos/{festivo_id}", hecho=lambda _x: self._cambiado("Festivo quitado"), fallo=self.ventana.error
        )

    def _cambiado(self, aviso: str) -> None:
        self.ventana.aviso(aviso)
        self.ventana.invalidar(self)
        self.cargar()
