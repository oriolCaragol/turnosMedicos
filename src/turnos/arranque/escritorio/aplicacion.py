"""Aplicación GNOME de una sola instancia: volver a abrirla enfoca la ventana
(diseño del modo escritorio, 9.1 y 9.2)."""

import threading

from gi.repository import Adw, Gio, GLib, Gtk

from turnos import __version__
from turnos.arranque import conexion as cx
from turnos.arranque.dialogos import DialogoConexion, SelectorInicio
from turnos.arranque.escritorio import ID_APLICACION
from turnos.arranque.escritorio.ventana import Ventana
from turnos.arranque.servidor import Servidor, preparar


class Aplicacion(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=ID_APLICACION, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        GLib.set_application_name("Turnos médicos")
        self._ventana: Ventana | None = None
        self._servidor: Servidor | None = None
        self.connect("activate", self._activar)
        self.connect("shutdown", lambda _a: self._detener_servidor())
        self.conexion = cx.leer()
        for nombre, accion, atajos in [
            ("salir", lambda *_: self._ventana and self._ventana.close(), ["<Control>q"]),
            ("acerca-de", lambda *_: self._acerca_de(), []),
            ("conexion", lambda *_: DialogoConexion(self).present(self._ventana), []),
        ]:
            a = Gio.SimpleAction(name=nombre)
            a.connect("activate", accion)
            self.add_action(a)
            if atajos:
                self.set_accels_for_action(f"app.{nombre}", atajos)
        for accion, atajos in [
            ("win.recargar", ["<Control>r", "F5"]),
            ("win.imprimir", ["<Control>p"]),
            ("win.ampliar", ["<Control>plus", "<Control>equal", "<Control>KP_Add"]),
            ("win.reducir", ["<Control>minus", "<Control>KP_Subtract"]),
            ("win.zoom-normal", ["<Control>0", "<Control>KP_0"]),
        ]:
            self.set_accels_for_action(accion, atajos)

    def _activar(self, _app) -> None:
        if self._ventana is not None:
            self._ventana.present()
            return
        self._ventana = Ventana(self)
        self._ventana.al_cerrar = self._cerrar
        self._ventana.present()
        if self.conexion.preguntar:
            self._ventana.mostrar_inicio(SelectorInicio(self._ventana, self._iniciar))
        else:
            self._iniciar(self.conexion)

    def _iniciar(self, conexion: cx.Conexion) -> None:
        """Ya se sabe dónde se trabaja (elegido al abrir o recordado)."""
        self.conexion = conexion
        self._ventana.preparar_web(conexion.en_servidor)
        if conexion.en_servidor:
            # Cliente de un servidor de la red: su interfaz web, con su inicio de sesión.
            self._ventana.cargar_servidor(conexion)
            return
        # Migraciones y arranque fuera del hilo de la interfaz: la ventana no se congela.
        threading.Thread(target=self._arrancar_servidor, name="arranque", daemon=True).start()

    def _arrancar_servidor(self) -> None:
        try:
            servidor = preparar(puerto=0)
            servidor.iniciar_en_hilo()
        except BaseException as error:  # noqa: BLE001 — se muestra en la ventana
            GLib.idle_add(self._ventana.mostrar_error, error)
            return
        self._servidor = servidor
        GLib.idle_add(self._ventana.cargar, servidor.url)

    def _cerrar(self) -> None:
        """La página ya se ha cerrado (y ha enviado lo pendiente): se espera a que el
        servidor termine esas peticiones y se sale."""
        servidor = self._servidor
        if servidor is None:
            self.quit()
            return

        def esperar() -> None:
            servidor.esperar_peticiones()
            GLib.idle_add(self.quit)

        threading.Thread(target=esperar, name="cierre", daemon=True).start()

    def _detener_servidor(self) -> None:
        if self._servidor is not None:
            self._servidor.detener()
            self._servidor = None

    def _acerca_de(self) -> None:
        Adw.AboutDialog(
            application_name="Turnos médicos",
            application_icon=ID_APLICACION,
            version=__version__,
            developer_name="Oriol",
            license_type=Gtk.License.GPL_3_0,
            comments="Asigna los turnos de mañana y tarde del equipo médico.",
        ).present(self._ventana)
