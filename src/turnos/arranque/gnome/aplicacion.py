"""Aplicación GNOME nativa: una instancia. Con los datos en este equipo, servidor interno
en un hilo; con un servidor de la red, cliente suyo (diseño del modo servidor, 11.2)."""

import threading
from pathlib import Path

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from turnos import __version__
from turnos.arranque import conexion as cx
from turnos.arranque import llavero
from turnos.arranque.dialogos import DialogoConexion, DialogoEntrar, SelectorInicio
from turnos.arranque.gnome import ID_APLICACION
from turnos.arranque.gnome.cliente import ClienteApi, ErrorApi
from turnos.arranque.gnome.ventana import Ventana
from turnos.arranque.servidor import Servidor, preparar


class Aplicacion(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=ID_APLICACION, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        GLib.set_application_name("Turnos médicos")
        self._ventana: Ventana | None = None
        self._servidor: Servidor | None = None
        self.connect("activate", self._activar)
        self.connect("shutdown", lambda _a: self._cerrar())
        self.conexion = cx.leer()
        for nombre, accion, atajos in [
            ("salir", lambda *_: self.quit(), ["<Control>q"]),
            ("acerca-de", lambda *_: self._acerca_de(), []),
            ("conexion", lambda *_: DialogoConexion(self).present(self._ventana), []),
            ("cerrar-sesion", lambda *_: self._cerrar_sesion(), []),
        ]:
            a = Gio.SimpleAction(name=nombre)
            a.connect("activate", accion)
            self.add_action(a)
            if atajos:
                self.set_accels_for_action(f"app.{nombre}", atajos)
        self.set_accels_for_action("win.mes-anterior", ["<Alt>Left", "<Control>Page_Up"])
        self.set_accels_for_action("win.mes-siguiente", ["<Alt>Right", "<Control>Page_Down"])
        self.set_accels_for_action("win.recargar", ["<Control>r", "F5"])

    def _activar(self, _app) -> None:
        if self._ventana is not None:
            self._ventana.present()
            return
        estilos = Gtk.CssProvider()
        estilos.load_from_path(str(Path(__file__).with_name("estilos.css")))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), estilos, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        # El icono de la aplicación, también sin instalar (en Flatpak ya está en el tema).
        Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(str(Path(__file__).with_name("iconos")))
        self._ventana = Ventana(self)
        self._ventana.present()
        if self.conexion.preguntar:
            self._ventana.set_content(SelectorInicio(self._ventana, self._iniciar))
        else:
            self._iniciar(self.conexion)

    def _iniciar(self, conexion: cx.Conexion) -> None:
        """Ya se sabe dónde se trabaja (elegido al abrir o recordado)."""
        self.conexion = conexion
        self.lookup_action("cerrar-sesion").set_enabled(conexion.en_servidor)
        self._ventana.mostrar_cargando()
        if conexion.en_servidor:
            self._ventana.mostrar_servidor(conexion)
            self._conectar_servidor()
        else:
            threading.Thread(target=self._arrancar_servidor, daemon=True).start()

    def _arrancar_servidor(self) -> None:
        try:
            servidor = preparar(puerto=0)
            servidor.iniciar_en_hilo()
        except BaseException as error:  # noqa: BLE001 — se muestra en la ventana
            GLib.idle_add(self._ventana.mostrar_error, error)
            return
        self._servidor = servidor
        GLib.idle_add(self._ventana.conectar, ClienteApi(f"http://127.0.0.1:{servidor.puerto}", servidor.token))

    # --- Servidor de la red -------------------------------------------------------------

    def _cliente(self, sesion: str) -> ClienteApi:
        return ClienteApi(cx.resolver(self.conexion.direccion), None, sesion=sesion,
                          contexto=cx.contexto_ssl(self.conexion), sin_sesion=self._sesion_caducada)

    def _conectar_servidor(self) -> None:
        """Con la sesión del llavero, si sigue valiendo; si no, se pide usuario y contraseña."""
        sesion = llavero.leer(self.conexion.direccion, self.conexion.usuario)
        if not sesion:
            self._pedir_entrada()
            return

        def comprobar() -> None:
            cliente = self._cliente(sesion)
            try:
                yo = cliente.pedir("GET", "/yo")
            except ErrorApi as error:
                if error.estado == 401:  # caducada o cerrada desde Administración
                    GLib.idle_add(self._pedir_entrada)
                else:
                    GLib.idle_add(self._ventana.mostrar_error_servidor, str(error), self._conectar_servidor)
                return
            GLib.idle_add(self._entrar, cliente, yo)

        threading.Thread(target=comprobar, daemon=True).start()

    def _pedir_entrada(self) -> bool:
        def hecho(respuesta: dict, usuario: str) -> None:
            self.conexion.usuario = usuario
            cx.guardar(self.conexion)
            llavero.guardar(self.conexion.direccion, usuario, respuesta["token"])
            self._entrar(self._cliente(respuesta["token"]), respuesta)

        self.dialogo_entrar = DialogoEntrar(self, self.conexion, hecho, "Turnos médicos (GNOME)")
        self.dialogo_entrar.present(self._ventana)
        return False

    def _entrar(self, cliente: ClienteApi, yo: dict) -> None:
        if yo["rol"] == "MEDICO":
            # Las vistas de médico están en la web (D-S10).
            self._ventana.mostrar_solo_web(self.conexion.direccion, yo)
            return
        if yo.get("debe_cambiar"):
            self._ventana.mostrar_solo_web(self.conexion.direccion, yo)
            return
        self._ventana.usuario = yo
        self._ventana.conectar(cliente)

    def _sesion_caducada(self) -> bool:
        if getattr(self, "_pidiendo", False):
            return False
        self._pidiendo = True
        llavero.borrar(self.conexion.direccion, self.conexion.usuario)
        self._ventana.error("La sesión ha terminado: vuelve a entrar")

        def hecho(respuesta: dict, usuario: str) -> None:
            self._pidiendo = False
            llavero.guardar(self.conexion.direccion, usuario, respuesta["token"])
            if self._ventana.cliente is not None and usuario == self.conexion.usuario:
                self._ventana.cliente.sesion = respuesta["token"]
                self._ventana.recargar()
            else:  # otro usuario: se empieza de nuevo
                self.conexion.usuario = usuario
                cx.guardar(self.conexion)
                from turnos.arranque.dialogos import reiniciar

                reiniciar(self)

        DialogoEntrar(self, self.conexion, hecho, "Turnos médicos (GNOME)").present(self._ventana)
        return False

    def _cerrar_sesion(self) -> None:
        cliente = self._ventana.cliente if self._ventana else None
        if cliente is not None and cliente.sesion:
            try:
                cliente.pedir("DELETE", "/sesion")
            except ErrorApi:
                pass
        llavero.borrar(self.conexion.direccion, self.conexion.usuario)
        from turnos.arranque.dialogos import reiniciar

        reiniciar(self)

    def _cerrar(self) -> None:
        if self._ventana is not None and self._ventana.cliente is not None:
            self._ventana.cliente.parar()
        if self._servidor is not None:
            self._servidor.detener()

    def _acerca_de(self) -> None:
        Adw.AboutDialog(
            application_name="Turnos médicos",
            application_icon="io.oriol.TurnosMedicos",
            version=f"{__version__} (interfaz nativa, prototipo)",
            developer_name="Oriol",
            license_type=Gtk.License.GPL_3_0,
            comments="Asigna los turnos de mañana y tarde del equipo médico.",
        ).present(self._ventana)
