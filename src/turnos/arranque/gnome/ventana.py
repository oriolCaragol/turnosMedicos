"""Ventana principal: mes de trabajo en la cabecera y una pestaña por pantalla."""

from datetime import date

from gi.repository import Adw, Gio, Gtk

from turnos.arranque.escritorio.errores import detalles, explicar
from turnos.arranque.gnome.cliente import ClienteApi
from turnos.arranque.gnome.comun import desplazar, mes_siguiente, nombre_mes


class Ventana(Adw.ApplicationWindow):
    def __init__(self, aplicacion: Adw.Application) -> None:
        super().__init__(application=aplicacion, title="Turnos médicos", default_width=1280, default_height=900)
        self.set_size_request(400, 400)
        self.cliente: ClienteApi | None = None
        self.usuario: dict | None = None  # en un servidor de la red, quién ha entrado
        self.mes: date = mes_siguiente()
        self._paginas: list = []

        self._etiquetas_mes: list[Gtk.Label] = []

        # Arriba a la izquierda: icono y nombre de la aplicación. El mes va en cada pantalla
        # que lo usa (ver `selector_mes`).
        marca = Gtk.Box(spacing=8, margin_start=6)
        marca.append(Gtk.Image(icon_name="io.oriol.TurnosMedicos", pixel_size=22))
        marca.append(Gtk.Label(label="TurnosMedicos", css_classes=["heading"]))
        self._marca = marca

        self._pila = Adw.ViewStack()
        cambiador = Adw.ViewSwitcher(stack=self._pila, policy=Adw.ViewSwitcherPolicy.WIDE)
        cabecera = Adw.HeaderBar(title_widget=cambiador)
        cabecera.pack_start(marca)
        cabecera.pack_end(self._menu())

        barra_inferior = Adw.ViewSwitcherBar(stack=self._pila)
        self._avisos = Adw.ToastOverlay(child=self._pila)
        vista = Adw.ToolbarView(content=self._avisos)
        vista.add_top_bar(cabecera)
        vista.add_bottom_bar(barra_inferior)

        # En ventanas estrechas, las pestañas pasan abajo.
        punto = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 760sp"))
        punto.add_setter(cambiador, "visible", False)
        punto.add_setter(barra_inferior, "reveal", True)
        self.add_breakpoint(punto)
        self._estrecho = punto
        self._ancho = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("min-width: 1700sp"))
        self.add_breakpoint(self._ancho)

        # Colores propios que dependen del tema (claro u oscuro).
        estilo = Adw.StyleManager.get_default()
        estilo.connect("notify::dark", lambda e, _p: self._tema(e.get_dark()))
        self._tema(estilo.get_dark())

        self._cargando = Adw.StatusPage(
            title="Abriendo turnos…", child=Adw.Spinner(width_request=32, height_request=32)
        )
        self.set_content(self._cargando)
        self._vista = vista

        for nombre, accion in [
            ("mes-anterior", lambda *_: self.cambiar_mes(-1)),
            ("mes-siguiente", lambda *_: self.cambiar_mes(1)),
            ("recargar", lambda *_: self.recargar()),
        ]:
            a = Gio.SimpleAction(name=nombre)
            a.connect("activate", accion)
            self.add_action(a)

    def selector_mes(self) -> Gtk.Widget:
        """‹ Noviembre 2026 › — el mes de trabajo, común a todas las pantallas."""
        etiqueta = Gtk.Label(label=nombre_mes(self.mes), css_classes=["mes-actual"], width_chars=13)
        self._etiquetas_mes.append(etiqueta)
        caja = Gtk.Box(css_classes=["linked"], valign=Gtk.Align.CENTER)
        for icono, texto, paso in [("go-previous-symbolic", "Mes anterior (Alt+←)", -1), ("go-next-symbolic", "Mes siguiente (Alt+→)", 1)]:
            boton = Gtk.Button(icon_name=icono, tooltip_text=texto)
            boton.connect("clicked", lambda _b, p=paso: self.cambiar_mes(p))
            caja.append(boton)
            if paso == -1:
                caja.append(etiqueta)
        return caja

    def _tema(self, oscuro: bool) -> None:
        (self.add_css_class if oscuro else self.remove_css_class)("oscuro")

    def _menu(self) -> Gtk.MenuButton:
        menu = Gio.Menu()
        menu.append("Recargar", "win.recargar")
        conexion = Gio.Menu()
        conexion.append("Conexión…", "app.conexion")
        conexion.append("Salir de la sesión", "app.cerrar-sesion")  # activa solo con un servidor
        menu.append_section(None, conexion)
        acerca = Gio.Menu()
        acerca.append("Acerca de Turnos médicos", "app.acerca-de")
        menu.append_section(None, acerca)
        return Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, tooltip_text="Menú principal")

    # --- Servidor de la red -----------------------------------------------------------

    def mostrar_cargando(self) -> None:
        self.set_content(self._cargando)

    def mostrar_servidor(self, conexion) -> None:
        self._cargando.set_title("Conectando con el servidor…")
        self._cargando.set_description(conexion.direccion)

    def _pagina_estado(self, titulo: str, descripcion: str, botones: list[tuple[str, object, bool]]) -> None:
        pagina = Adw.StatusPage(icon_name="network-server-symbolic", title=titulo, description=descripcion)
        caja = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        for texto, accion, principal in botones:
            boton = Gtk.Button(label=texto, css_classes=["pill", *(["suggested-action"] if principal else [])])
            boton.connect("clicked", lambda _b, a=accion: a())
            caja.append(boton)
        pagina.set_child(caja)
        self.set_content(pagina)

    def mostrar_error_servidor(self, texto: str, reintentar) -> None:
        from turnos.arranque.dialogos import DialogoConexion

        def otra_vez() -> None:
            self.set_content(self._cargando)
            reintentar()

        self._pagina_estado("No se puede conectar con el servidor", texto, [
            ("Cambiar la conexión…", lambda: DialogoConexion(self.get_application()).present(self), False),
            ("Reintentar", otra_vez, True),
        ])

    def mostrar_solo_web(self, direccion: str, yo: dict) -> None:
        """Médicos y contraseñas temporales: en el navegador (D-S10)."""
        if yo.get("debe_cambiar"):
            titulo, texto = "Elige tu contraseña", "Tienes una contraseña temporal: entra una vez desde el navegador para elegir la tuya."
        else:
            titulo, texto = f"Hola, {yo['nombre_visible']}", "Tus turnos, el calendario y tu ficha están en el navegador, también en el móvil."
        abrir = lambda: Gtk.UriLauncher.new(direccion + "/").launch(self, None, None, None)  # noqa: E731
        self._pagina_estado(titulo, f"{texto}\n{direccion}", [
            ("Salir de la sesión", lambda: self.get_application().activate_action("cerrar-sesion", None), False),
            ("Abrir en el navegador", abrir, True),
        ])

    # --- Arranque -----------------------------------------------------------------

    def conectar(self, cliente: ClienteApi) -> None:
        from turnos.arranque.gnome.calendario import PaginaCalendario
        from turnos.arranque.gnome.configuracion import PaginaConfiguracion
        from turnos.arranque.gnome.festivos import PaginaFestivos
        from turnos.arranque.gnome.cobertura import PaginaCobertura
        from turnos.arranque.gnome.medicos import PaginaEquipo

        self.cliente = cliente
        if self.usuario:  # en un servidor: quién y dónde
            servidor = self.get_application().conexion.direccion.split("://")[-1]
            self._marca.append(Gtk.Label(label=f"{self.usuario['nombre_visible']} · {servidor}",
                                         css_classes=["dim-label", "caption"]))
        cliente.escuchar(self._evento)
        for clase, nombre, titulo, icono in [
            (PaginaCalendario, "calendario", "Calendario", "x-office-calendar-symbolic"),
            (PaginaEquipo, "medicos", "Médicos y reglas", "system-users-symbolic"),
            (PaginaCobertura, "cobertura", "Cobertura", "view-grid-symbolic"),
            (PaginaFestivos, "festivos", "Festivos", "starred-symbolic"),
            (PaginaConfiguracion, "configuracion", "Configuración", "emblem-system-symbolic"),
        ]:
            pagina = clase(self)
            self._paginas.append(pagina)
            self._pila.add_titled_with_icon(pagina, nombre, titulo, icono)
        self.solicitudes = None
        if self.usuario:  # en un servidor: la bandeja de solicitudes de los médicos (D-S10)
            from turnos.arranque.gnome.solicitudes import PaginaSolicitudes

            self.solicitudes = PaginaSolicitudes(self)
            self._paginas.append(self.solicitudes)
            self.solicitudes.pagina_pila = self._pila.add_titled_with_icon(
                self.solicitudes, "solicitudes", "Solicitudes", "mail-unread-symbolic")
            self.solicitudes.actualizar_contador()
        calendario = self._paginas[0]
        self._estrecho.add_setter(calendario.cuadricula, "visible", False)
        self._estrecho.add_setter(calendario.lista, "visible", True)
        self._estrecho.add_setter(calendario.barra, "orientation", Gtk.Orientation.VERTICAL)
        self._estrecho.add_setter(calendario.barra_vista, "visible", False)
        self._estrecho.add_setter(self._paginas[1].medicos.cabecera, "orientation", Gtk.Orientation.VERTICAL)
        # Monitores anchos: problemas y carga al lado del calendario; más tarjetas de médicos.
        self._ancho.add_setter(calendario.contenido, "orientation", Gtk.Orientation.HORIZONTAL)
        self._ancho.add_setter(calendario.contenido, "spacing", 48)  # aire entre el calendario y la columna
        self._ancho.add_setter(calendario.clamp, "maximum-size", 2400)
        self._ancho.add_setter(calendario.clamp, "tightening-threshold", 2400)
        self._ancho.add_setter(calendario.lateral, "width-request", 600)
        self._pila.connect("notify::visible-child", lambda *_: self._entrar_en_pagina())
        self.set_content(self._vista)
        self._mostrar_visible()

    def mostrar_error(self, error: BaseException) -> None:
        titulo, descripcion = explicar(error)
        pagina = Adw.StatusPage(icon_name="dialog-error-symbolic", title=titulo, description=descripcion)
        copiar = Gtk.Button(label="Copiar detalles", css_classes=["pill"], halign=Gtk.Align.CENTER)
        copiar.connect("clicked", lambda _b: self.get_clipboard().set(detalles(error)))
        pagina.set_child(copiar)
        self.set_content(pagina)

    # --- Estado compartido ------------------------------------------------------------

    def cambiar_mes(self, paso: int) -> None:
        self.mes = desplazar(self.mes, paso)
        for etiqueta in self._etiquetas_mes:
            etiqueta.set_label(nombre_mes(self.mes))
        for pagina in self._paginas:
            pagina.pendiente = True
        self._mostrar_visible()

    def recargar(self) -> None:
        for pagina in self._paginas:
            pagina.pendiente = True
        self._mostrar_visible()

    def _entrar_en_pagina(self) -> None:
        pagina = self._pila.get_visible_child()
        if (al_entrar := getattr(pagina, "al_entrar", None)) is not None:
            al_entrar()
        self._mostrar_visible()

    def _mostrar_visible(self) -> None:
        """Cada pantalla se recarga al verla, si algo ha cambiado desde la última vez."""
        pagina = self._pila.get_visible_child()
        if pagina is not None and getattr(pagina, "pendiente", True):
            pagina.pendiente = False
            pagina.cargar()

    def _evento(self, evento: dict) -> None:
        """Un cambio de otro usuario (diseño del modo servidor, 9). El calendario visible
        se recarga en el acto; las demás pantallas, al volver a verlas (para no perder lo
        que se esté escribiendo en un formulario)."""
        calendario = self._paginas[0] if self._paginas else None
        if evento.get("tipo") == "solicitudes":
            if self.solicitudes is not None:
                self.solicitudes.pendiente = True
                self.solicitudes.actualizar_contador()
                if self._pila.get_visible_child() is self.solicitudes:
                    self._mostrar_visible()
            return
        if evento.get("tipo") == "calendario":
            if (evento.get("anio"), evento.get("mes")) != (self.mes.year, self.mes.month):
                return
            calendario.cambio_externo()
            calendario.pendiente = True
        else:
            for pagina in self._paginas:
                pagina.pendiente = True
        if calendario is not None and calendario.pendiente and self._pila.get_visible_child() is calendario:
            if not calendario._enviando:
                self._mostrar_visible()

    def invalidar(self, *excepto) -> None:
        """Algo ha cambiado: las demás pantallas se recargarán al verlas."""
        for pagina in self._paginas:
            if pagina not in excepto:
                pagina.pendiente = True

    def aviso(self, texto: str) -> None:
        self._avisos.add_toast(Adw.Toast(title=texto, timeout=3))

    def error(self, texto: str) -> None:
        self._avisos.add_toast(Adw.Toast(title=texto, timeout=8))
