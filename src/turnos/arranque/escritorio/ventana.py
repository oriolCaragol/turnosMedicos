"""Ventana principal: la interfaz web en un WebView, con pantallas de carga y error
(diseño del modo escritorio, 9.1–9.3)."""

import os
import ssl
import threading
from pathlib import Path
from urllib.parse import urlsplit

from gi.repository import Adw, Gdk, Gio, GLib, Gtk, WebKit

from turnos.arranque import conexion as cx
from turnos.arranque.escritorio import estado
from turnos.arranque.escritorio.descargas import Descargas
from turnos.arranque.escritorio.errores import detalles, explicar

# Entradas del menú contextual de WebKit que no tienen sentido en la aplicación.
_SOBRANTES = {
    WebKit.ContextMenuAction.GO_BACK,
    WebKit.ContextMenuAction.GO_FORWARD,
    WebKit.ContextMenuAction.STOP,
    WebKit.ContextMenuAction.RELOAD,
    WebKit.ContextMenuAction.OPEN_LINK_IN_NEW_WINDOW,
    WebKit.ContextMenuAction.DOWNLOAD_LINK_TO_DISK,
    WebKit.ContextMenuAction.OPEN_IMAGE_IN_NEW_WINDOW,
    WebKit.ContextMenuAction.DOWNLOAD_IMAGE_TO_DISK,
    WebKit.ContextMenuAction.OPEN_FRAME_IN_NEW_WINDOW,
    WebKit.ContextMenuAction.INSPECT_ELEMENT,
}
ZOOM = (0.67, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0)


class Ventana(Adw.ApplicationWindow):
    def __init__(self, aplicacion: Adw.Application) -> None:
        super().__init__(application=aplicacion, title="Turnos médicos")
        self._origen: str | None = None  # http://127.0.0.1:<puerto> o el servidor de la red
        self._conexion: cx.Conexion | None = None  # con un servidor de la red
        self._cerrando = False
        self.al_cerrar = lambda: None  # lo pone la aplicación: detener el servidor y salir

        guardado = estado.leer()
        self.set_default_size(guardado["ancho"], guardado["alto"])
        if guardado["maximizada"]:
            self.maximize()

        self._titulo = Adw.WindowTitle(title="Turnos médicos")
        cabecera = Adw.HeaderBar(title_widget=self._titulo)
        cabecera.pack_end(self._menu())

        # El visor web se crea al saber dónde se trabaja (`preparar_web`): su sesión es
        # efímera con los datos en este equipo y persistente con un servidor.
        self._web: WebKit.WebView | None = None
        self._paginas = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self._paginas.add_named(self._pagina_cargando(), "cargando")
        self._error = Adw.StatusPage(icon_name="dialog-error-symbolic")
        self._paginas.add_named(self._error, "error")

        self._avisos = Adw.ToastOverlay(child=self._paginas)
        vista = Adw.ToolbarView(content=self._avisos)
        vista.add_top_bar(cabecera)
        self.set_content(vista)

        self._descargas = Descargas(self, self._avisos)
        self.connect("close-request", self._pedir_cierre)

    def mostrar_inicio(self, selector: Gtk.Widget) -> None:
        """La pantalla de elegir dónde trabajar (al abrir)."""
        self._paginas.add_named(selector, "inicio")
        self._paginas.set_visible_child_name("inicio")

    def preparar_web(self, en_servidor: bool) -> None:
        if self._web is not None:
            return
        self._web = self._crear_web(en_servidor)
        self._paginas.add_named(self._web, "web")
        self._descargas.conectar(self._web.get_network_session())
        self._paginas.set_visible_child_name("cargando")

    # --- Construcción --------------------------------------------------------------

    def _menu(self) -> Gtk.MenuButton:
        menu = Gio.Menu()
        seccion = Gio.Menu()
        seccion.append("Recargar", "win.recargar")
        seccion.append("Imprimir…", "win.imprimir")
        menu.append_section(None, seccion)
        zoom = Gio.Menu()
        zoom.append("Ampliar", "win.ampliar")
        zoom.append("Reducir", "win.reducir")
        zoom.append("Tamaño normal", "win.zoom-normal")
        menu.append_section(None, zoom)
        acerca = Gio.Menu()
        acerca.append("Conexión…", "app.conexion")
        acerca.append("Acerca de Turnos médicos", "app.acerca-de")
        menu.append_section(None, acerca)
        for nombre, accion in [
            ("recargar", lambda *_: self._web and self._web.reload()),
            ("imprimir", lambda *_: self.imprimir()),
            ("ampliar", lambda *_: self._web and self._zoom(+1)),
            ("reducir", lambda *_: self._web and self._zoom(-1)),
            ("zoom-normal", lambda *_: self._web and self._web.set_zoom_level(1.0)),
        ]:
            a = Gio.SimpleAction(name=nombre)
            a.connect("activate", accion)
            self.add_action(a)
        return Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, tooltip_text="Menú principal")

    def _crear_web(self, en_servidor: bool) -> WebKit.WebView:
        if en_servidor:
            # Con un servidor de la red, la cookie de la sesión se guarda: no hay que entrar
            # cada vez que se abre la aplicación.
            datos = Path(GLib.get_user_data_dir()) / "turnosMedicos" / "navegador"
            sesion = WebKit.NetworkSession.new(str(datos), str(Path(GLib.get_user_cache_dir()) / "turnosMedicos"))
            sesion.get_cookie_manager().set_persistent_storage(
                str(datos / "cookies.sqlite"), WebKit.CookiePersistentStorage.SQLITE
            )
        else:
            # Sesión efímera: no hace falta caché ni cookies en disco (los datos están en SQLite).
            sesion = WebKit.NetworkSession.new_ephemeral()
        # Sin proxy: solo se habla con 127.0.0.1 o con la red de casa. Además, en Flatpak sin
        # permiso de red el portal que resuelve el proxy rechaza la consulta y la página no
        # llegaría a cargar.
        sesion.set_proxy_settings(WebKit.NetworkProxyMode.NO_PROXY, None)
        web = WebKit.WebView(network_session=sesion)
        ajustes = web.get_settings()
        ajustes.set_enable_developer_extras(bool(os.environ.get("TURNOS_DEPURAR")))
        ajustes.set_javascript_can_open_windows_automatically(False)
        ajustes.set_enable_back_forward_navigation_gestures(False)
        web.connect("notify::title", self._titulo_cambiado)
        web.connect("decide-policy", self._decidir)
        web.connect("context-menu", self._menu_contextual)
        web.connect("load-changed", self._carga_cambiada)
        web.connect("web-process-terminated", self._proceso_terminado)
        web.connect("load-failed-with-tls-errors", self._certificado)
        web.connect("load-failed", self._fallo_de_carga)
        return web

    @staticmethod
    def _pagina_cargando() -> Adw.StatusPage:
        return Adw.StatusPage(title="Abriendo turnos…", child=Adw.Spinner(width_request=32, height_request=32))

    # --- Estados ---------------------------------------------------------------------

    def cargar(self, url: str) -> None:
        partes = urlsplit(url)
        self._origen = f"{partes.scheme}://{partes.netloc}"
        self._web.load_uri(url)
        self._paginas.set_visible_child_name("web")

    def cargar_servidor(self, conexion: cx.Conexion) -> None:
        """Interfaz web de un servidor de la red (diseño del modo servidor, 11.2)."""
        self._conexion = conexion
        self._paginas.get_child_by_name("cargando").set_title("Conectando con el servidor…")
        self._paginas.set_visible_child_name("cargando")

        # Fuera de la interfaz: resolver «turnos.local» puede tardar (en Flatpak, por mDNS).
        def preparar() -> None:
            url = cx.resolver(conexion.direccion)
            certificado = None
            if conexion.https:
                partes = urlsplit(url)
                try:
                    certificado = ssl.get_server_certificate((partes.hostname, partes.port), timeout=10)
                except OSError as error:
                    GLib.idle_add(self._error_servidor, f"{error}\n{conexion.direccion}")
                    return
            GLib.idle_add(self._abrir_servidor, url, certificado)

        threading.Thread(target=preparar, daemon=True).start()

    def _confiar(self, certificado: Gio.TlsCertificate, host: str) -> bool:
        """El servidor usa una autoridad propia: se acepta su certificado si lo firma la
        autoridad que el usuario confirmó al elegir la conexión (y solo para ese servidor).
        Se hace antes de cargar: así valen también las peticiones de la página aunque el
        documento salga de la caché."""
        try:
            autoridad = Gio.TlsCertificate.new_from_file(str(self._conexion.autoridad))
        except GLib.Error:
            return False
        if int(certificado.verify(None, autoridad)) != 0:
            return False
        self._web.get_network_session().allow_tls_certificate_for_host(certificado, host)
        return True

    def _abrir_servidor(self, url: str, pem: str | None) -> None:
        if pem is not None and not self._confiar(Gio.TlsCertificate.new_from_pem(pem, -1), urlsplit(url).hostname):
            self._error_servidor("El certificado del servidor no es el que se confirmó. Vuelve a elegir la conexión.")
            return
        self.cargar(url + "/")

    def _certificado(self, web: WebKit.WebView, uri: str, certificado: Gio.TlsCertificate, _errores) -> bool:
        """Por si el servidor renueva su certificado con la ventana abierta."""
        if self._conexion is None or not self._origen or not uri.startswith(self._origen):
            return False
        if not self._confiar(certificado, urlsplit(uri).hostname):
            self._error_servidor("El certificado del servidor no es el que se confirmó. Vuelve a elegir la conexión.")
            return True
        web.load_uri(uri)
        return True

    def _fallo_de_carga(self, _web, _evento, uri: str, error: GLib.Error) -> bool:
        if self._conexion is None or self._cerrando or not self._origen or not uri.startswith(self._origen):
            return False
        if error.matches(WebKit.network_error_quark(), WebKit.NetworkError.CANCELLED):
            return False
        self._error_servidor(f"{error.message}\n{self._conexion.direccion}")
        return True

    def _error_servidor(self, texto: str) -> None:
        from turnos.arranque.dialogos import DialogoConexion

        self._error.set_icon_name("network-server-symbolic")
        self._error.set_title("No se puede conectar con el servidor")
        self._error.set_description(texto)
        botones = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        otra = Gtk.Button(label="Cambiar la conexión…", css_classes=["pill"])
        otra.connect("clicked", lambda _b: DialogoConexion(self.get_application()).present(self))
        reintentar = Gtk.Button(label="Reintentar", css_classes=["pill", "suggested-action"])
        reintentar.connect("clicked", lambda _b: self.cargar_servidor(self._conexion))
        botones.append(otra)
        botones.append(reintentar)
        self._error.set_child(botones)
        self._paginas.set_visible_child_name("error")

    def mostrar_error(self, error: BaseException) -> None:
        titulo, descripcion = explicar(error)
        texto = detalles(error)
        self._error.set_title(titulo)
        self._error.set_description(descripcion)
        botones = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        copiar = Gtk.Button(label="Copiar detalles", css_classes=["pill"])
        copiar.connect("clicked", lambda _b: self._copiar(texto))
        salir = Gtk.Button(label="Cerrar", css_classes=["pill", "suggested-action"])
        salir.connect("clicked", lambda _b: self.close())
        botones.append(copiar)
        botones.append(salir)
        self._error.set_child(botones)
        self._paginas.set_visible_child_name("error")

    def _copiar(self, texto: str) -> None:
        Gdk.Display.get_default().get_clipboard().set(texto)
        self._avisos.add_toast(Adw.Toast(title="Detalles copiados", timeout=3))

    # --- Acciones --------------------------------------------------------------------

    def imprimir(self) -> None:
        """Como el botón «Imprimir / PDF» de la interfaz: `window.print()` con su hoja de estilos."""
        if self._paginas.get_visible_child_name() == "web":
            self._web.evaluate_javascript("window.print()", -1, None, None, None, None, None)

    def _zoom(self, paso: int) -> None:
        actual = self._web.get_zoom_level()
        cercano = min(range(len(ZOOM)), key=lambda i: abs(ZOOM[i] - actual))
        self._web.set_zoom_level(ZOOM[max(0, min(len(ZOOM) - 1, cercano + paso))])

    # --- Señales del WebView -----------------------------------------------------------

    def _titulo_cambiado(self, web: WebKit.WebView, _param) -> None:
        titulo = web.get_title() or "Turnos médicos"
        self._titulo.set_title(titulo)
        self.set_title(titulo)

    def _decidir(self, _web, decision, tipo) -> bool:
        if tipo not in (WebKit.PolicyDecisionType.NAVIGATION_ACTION, WebKit.PolicyDecisionType.NEW_WINDOW_ACTION):
            return False
        uri = decision.get_navigation_action().get_request().get_uri()
        if uri == "about:blank":
            return False  # al cerrar (ver `_pedir_cierre`)
        if self._origen and (uri.startswith(self._origen + "/") or uri == self._origen):
            if tipo is WebKit.PolicyDecisionType.NEW_WINDOW_ACTION:
                decision.ignore()
                self._web.load_uri(uri)  # sin ventanas nuevas: en la misma
                return True
            return False
        # Cualquier otra dirección, en el navegador del sistema.
        decision.ignore()
        if urlsplit(uri).scheme in ("http", "https", "mailto"):
            Gtk.UriLauncher.new(uri).launch(self, None, None, None)
        return True

    def _menu_contextual(self, _web, menu: WebKit.ContextMenu, _evento, _resultado) -> bool:
        for item in list(menu.get_items()):
            if item.get_stock_action() in _SOBRANTES:
                menu.remove(item)
        return len(menu.get_items()) == 0  # sin entradas útiles, no se muestra

    def _proceso_terminado(self, web: WebKit.WebView, _motivo) -> None:
        if not self._cerrando:
            self._avisos.add_toast(Adw.Toast(title="La página se ha recargado tras un error", timeout=5))
            web.reload()

    # --- Cierre ----------------------------------------------------------------------

    def _pedir_cierre(self, _ventana) -> bool:
        """Antes de cerrar, la vista sale de la página (a about:blank): así la página
        recibe «pagehide» y envía los guardados pendientes, como al cerrar una pestaña
        en el modo web. Cuando ha salido, se cierra de verdad."""
        if self._cerrando:
            return False
        estado.guardar(*self.get_default_size(), self.is_maximized())
        self._cerrando = True
        if self._paginas.get_visible_child_name() != "web":
            self._terminar()
            return False
        self.set_visible(False)
        self._web.load_uri("about:blank")
        # Por si la página no llegara a responder (proceso colgado).
        GLib.timeout_add_seconds(5, self._terminar)
        return True

    def _carga_cambiada(self, web: WebKit.WebView, evento) -> None:
        if self._cerrando and evento is WebKit.LoadEvent.FINISHED and web.get_uri() == "about:blank":
            self._terminar()

    def _terminar(self) -> bool:
        al_cerrar, self.al_cerrar = self.al_cerrar, lambda: None
        al_cerrar()
        return False
