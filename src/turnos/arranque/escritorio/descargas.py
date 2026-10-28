"""Descargas (XLSX, copia de seguridad): «Guardar como» nativo y aviso al terminar."""

from pathlib import Path

from gi.repository import Adw, Gio, GLib, Gtk, WebKit


class Descargas:
    def __init__(self, ventana: Gtk.Window, avisos: Adw.ToastOverlay) -> None:
        self._ventana = ventana
        self._avisos = avisos
        self._ultima_carpeta: Gio.File | None = None
        self._fallidas: set[WebKit.Download] = set()

    def conectar(self, sesion: WebKit.NetworkSession) -> None:
        sesion.connect("download-started", self._empezada)

    def _empezada(self, _sesion, descarga: WebKit.Download) -> None:
        descarga.set_allow_overwrite(True)  # el diálogo ya ha preguntado si reemplazar
        descarga.connect("decide-destination", self._elegir_destino)
        descarga.connect("finished", self._terminada)
        descarga.connect("failed", self._fallida)

    def _elegir_destino(self, descarga: WebKit.Download, sugerido: str) -> bool:
        dialogo = Gtk.FileDialog(title="Guardar", initial_name=sugerido, modal=True)
        carpeta = self._ultima_carpeta or _carpeta_descargas()
        if carpeta is not None:
            dialogo.set_initial_folder(carpeta)
        dialogo.save(self._ventana, None, self._destino_elegido, descarga)
        return True  # el destino se indica después, al responder el diálogo

    def _destino_elegido(self, dialogo: Gtk.FileDialog, resultado, descarga: WebKit.Download) -> None:
        try:
            fichero = dialogo.save_finish(resultado)
        except GLib.Error:
            fichero = None
        if fichero is None or fichero.get_path() is None:
            descarga.cancel()
            return
        self._ultima_carpeta = fichero.get_parent()
        descarga.set_destination(fichero.get_path())

    def _terminada(self, descarga: WebKit.Download) -> None:
        destino = descarga.get_destination()
        if descarga in self._fallidas or not destino:
            self._fallidas.discard(descarga)
            return  # cancelada o fallida: ya se ha avisado (o no hacía falta)
        aviso = Adw.Toast(title=f"Guardado «{Path(destino).name}»", timeout=6)
        aviso.set_button_label("Abrir")
        aviso.connect("button-clicked", lambda _a: _abrir(self._ventana, destino))
        self._avisos.add_toast(aviso)

    def _fallida(self, descarga: WebKit.Download, error: GLib.Error) -> None:
        self._fallidas.add(descarga)  # después llega también «finished»
        if error.matches(WebKit.download_error_quark(), WebKit.DownloadError.CANCELLED_BY_USER):
            return
        self._avisos.add_toast(Adw.Toast(title=f"No se ha podido guardar: {error.message}", timeout=8))


def _carpeta_descargas() -> Gio.File | None:
    ruta = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
    return Gio.File.new_for_path(ruta) if ruta else None


def _abrir(ventana: Gtk.Window, ruta: str) -> None:
    Gtk.FileLauncher.new(Gio.File.new_for_path(ruta)).launch(ventana, None, None, None)
