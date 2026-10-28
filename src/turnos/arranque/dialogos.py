"""Diálogos comunes a las dos aplicaciones de escritorio (diseño del modo servidor, 11.2):
elegir a qué núcleo conectarse y entrar en un servidor.

Las operaciones de red van en hilos; los resultados vuelven al de la interfaz con
`GLib.idle_add`.
"""

import json
import os
import sys
import threading
import urllib.error
from collections.abc import Callable

from gi.repository import Adw, GLib, Gtk

from turnos.arranque import conexion as cx


def en_hilo(trabajo: Callable[[], object], hecho: Callable[[object], None], fallo: Callable[[str], None]) -> None:
    def correr() -> None:
        try:
            resultado = trabajo()
        except Exception as error:  # noqa: BLE001 — se muestra al usuario
            GLib.idle_add(fallo, _explicar(error))
        else:
            GLib.idle_add(hecho, resultado)

    threading.Thread(target=correr, daemon=True).start()


def _explicar(error: BaseException) -> str:
    if isinstance(error, urllib.error.HTTPError):
        try:
            return json.loads(error.read()).get("detail") or f"Error del servidor ({error.code})"
        except ValueError:
            return f"Error del servidor ({error.code})"
    if isinstance(error, urllib.error.URLError):
        motivo = error.reason
        if "CERTIFICATE_VERIFY_FAILED" in str(motivo):
            return "El certificado del servidor no es el que se confirmó. Vuelve a elegir la conexión."
        return f"No se puede conectar con el servidor ({motivo})."
    return str(error)


def reiniciar(aplicacion: Adw.Application) -> None:
    """Cierra la aplicación (con su limpieza normal) y la vuelve a abrir con la conexión nueva."""
    aplicacion.reiniciar = True
    aplicacion.quit()


def volver_a_abrir_si_hace_falta(aplicacion: Adw.Application) -> None:
    """Tras `run()`: si se pidió reiniciar, se sustituye el proceso por uno nuevo."""
    if getattr(aplicacion, "reiniciar", False):
        os.execv(sys.executable, [sys.executable, *sys.argv])


class DialogoConexion(Adw.Dialog):
    """«Este equipo» o «Un servidor de la red» (los anunciados o una dirección)."""

    def __init__(self, aplicacion: Adw.Application) -> None:
        super().__init__(title="Conexión", content_width=460)
        self._aplicacion = aplicacion
        self._actual = cx.leer()

        cabecera = Adw.HeaderBar()
        pagina = Adw.PreferencesPage()
        vista = Adw.ToolbarView(content=pagina)
        vista.add_top_bar(cabecera)
        self.set_child(vista)

        modo = Adw.PreferencesGroup(
            title="¿Dónde están los datos?",
            description="En este equipo, solo para ti; o en el servidor de casa, compartidos con el resto del equipo.",
        )
        self._personal = Gtk.CheckButton()
        self._servidor = Gtk.CheckButton(group=self._personal)
        for boton, titulo, subtitulo in [
            (self._personal, "Este equipo", "Los datos de esta cuenta del ordenador"),
            (self._servidor, "Un servidor de la red", "turnos servidor en un PC o una Raspberry Pi de casa"),
        ]:
            fila = Adw.ActionRow(title=titulo, subtitle=subtitulo, activatable_widget=boton)
            fila.add_prefix(boton)
            modo.add(fila)
        pagina.add(modo)

        self._grupo_servidor = Adw.PreferencesGroup(title="Servidor")
        self._direccion = Adw.EntryRow(title="Dirección (p. ej. turnos.local:8443)")
        self._direccion.set_text(self._actual.direccion or "")
        self._grupo_servidor.add(self._direccion)
        self._encontrados = Adw.ExpanderRow(title="Buscando servidores en la red…", expanded=True)
        self._grupo_servidor.add(self._encontrados)
        pagina.add(self._grupo_servidor)

        abrir = Adw.PreferencesGroup()
        self._preguntar = Adw.SwitchRow(title="Preguntar al abrir la aplicación",
                                        subtitle="Elegir cada vez entre este equipo y un servidor",
                                        active=self._actual.preguntar)
        abrir.add(self._preguntar)
        pagina.add(abrir)

        self._mensaje = Gtk.Label(wrap=True, css_classes=["error"], visible=False, margin_top=6)
        self._boton = Gtk.Button(label="Conectar", css_classes=["pill", "suggested-action"], halign=Gtk.Align.CENTER)
        self._boton.connect("clicked", lambda _b: self._aceptar())
        pie = Adw.PreferencesGroup()
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        caja.append(self._mensaje)
        caja.append(self._boton)
        pie.add(caja)
        pagina.add(pie)

        (self._servidor if self._actual.en_servidor else self._personal).set_active(True)
        self._servidor.connect("toggled", lambda _b: self._actualizar())
        self._actualizar()
        en_hilo(cx.buscar_servidores, self._mostrar_encontrados, lambda _m: self._mostrar_encontrados([]))

    def _actualizar(self) -> None:
        self._grupo_servidor.set_sensitive(self._servidor.get_active())
        self._boton.set_label("Conectar" if self._servidor.get_active() else "Usar este equipo")

    def _mostrar_encontrados(self, encontrados) -> None:
        self._encontrados.set_title("Servidores en la red" if encontrados else "No se ha encontrado ninguno")
        self._encontrados.set_subtitle("" if encontrados else "Escribe la dirección que muestra el servidor al arrancar")
        for nombre, direccion in encontrados:
            fila = Adw.ActionRow(title=nombre, subtitle=direccion, activatable=True)
            fila.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
            fila.connect("activated", lambda _f, d=direccion: self._direccion.set_text(d))
            self._encontrados.add_row(fila)

    def _error(self, texto: str) -> None:
        self._mensaje.set_label(texto)
        self._mensaje.set_visible(bool(texto))  # vacío: cancelado
        self._boton.set_sensitive(True)

    def _aceptar(self) -> None:
        self._mensaje.set_visible(False)
        preguntar = self._preguntar.get_active()
        if not self._servidor.get_active():
            cx.guardar(cx.Conexion("personal", self._actual.direccion, self._actual.huella, self._actual.usuario, preguntar))
            reiniciar(self._aplicacion)
            return
        try:
            direccion = cx.normalizar(self._direccion.get_text())
        except ValueError as error:
            self._error(str(error))
            return
        self._boton.set_sensitive(False)

        def confirmado(pem: str | None) -> None:
            guardar_servidor(direccion, pem, self._actual.usuario, preguntar)
            reiniciar(self._aplicacion)

        confirmar_servidor(self, direccion, self._actual, confirmado, self._error)


def guardar_servidor(direccion: str, pem: str | None, usuario: str, preguntar: bool) -> cx.Conexion:
    conexion = cx.Conexion("servidor", direccion, cx.huella_pem(pem) if pem else "", usuario, preguntar)
    cx.guardar(conexion, pem)
    return conexion


def confirmar_servidor(
    padre: Gtk.Widget, direccion: str, actual: cx.Conexion,
    hecho: Callable[[str | None], None], fallo: Callable[[str], None],
) -> None:
    """Descarga la autoridad del servidor y, como SSH, la primera vez enseña su huella para
    comprobarla en el servidor. Si es la ya confirmada para esa dirección, no pregunta.
    `hecho(pem)` (None sin HTTPS); `fallo(mensaje)` si no se puede o se cancela."""

    def preguntar(pem: str | None) -> None:
        if pem is None:
            cuerpo = "Sin HTTPS, los datos y la contraseña viajarán sin cifrar. Úsalo solo para pruebas."
        else:
            if actual.huella == cx.huella_pem(pem) and actual.direccion == direccion:
                hecho(pem)
                return
            cuerpo = (
                "Comprueba que esta huella coincide con la que muestra el servidor al arrancar o en "
                f"Administración › Servidor:\n\n{cx.formatear_huella(cx.huella_pem(pem))}"
            )
        alerta = Adw.AlertDialog(heading="¿Confiar en este servidor?", body=cuerpo)
        alerta.add_response("cancelar", "Cancelar")
        alerta.add_response("confiar", "Coincide: confiar")
        alerta.set_response_appearance("confiar", Adw.ResponseAppearance.SUGGESTED)
        alerta.set_body_use_markup(False)
        alerta.connect("response", lambda _a, r: hecho(pem) if r == "confiar" else fallo(""))
        alerta.present(padre)

    if not direccion.startswith("https://"):
        preguntar(None)
        return
    en_hilo(lambda: cx.descargar_autoridad(direccion), preguntar, fallo)


class SelectorInicio(Adw.Bin):
    """Al abrir la aplicación: ¿trabajar en este equipo (datos y motor aquí) o contra un
    servidor de la red? `elegido(conexion)` recibe la elección, ya guardada."""

    def __init__(self, ventana: Gtk.Window, elegido: Callable[[cx.Conexion], None]) -> None:
        super().__init__()
        self._ventana, self._elegido = ventana, elegido
        self._actual = cx.leer()
        self.filas_servidor: dict[str, Adw.ActionRow] = {}  # dirección → fila (también para las pruebas)

        pagina = Adw.PreferencesPage(title="Dónde trabajar")
        cabecera = Adw.PreferencesGroup()
        cabecera.add(Gtk.Image(icon_name="io.oriol.TurnosMedicos", pixel_size=64, margin_bottom=6))
        cabecera.add(Gtk.Label(label="¿Dónde quieres trabajar?", css_classes=["title-2"]))
        pagina.add(cabecera)

        local = Adw.PreferencesGroup()
        self.fila_local = Adw.ActionRow(
            title="En este equipo", subtitle="Los datos y el motor en este ordenador, solo para ti",
            icon_name="computer-symbolic", activatable=True,
        )
        self.fila_local.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
        self.fila_local.connect("activated", lambda _f: self.elegir_local())
        local.add(self.fila_local)
        pagina.add(local)

        self._servidores = Adw.PreferencesGroup(
            title="En un servidor de la red",
            description="Los datos compartidos con el resto del equipo (turnos servidor en un PC o una Raspberry Pi)",
        )
        self._buscando = Adw.ActionRow(title="Buscando servidores en la red…")
        self._buscando.add_prefix(Adw.Spinner())
        self._servidores.add(self._buscando)
        if self._actual.direccion:
            self._fila_servidor("Último usado", self._actual.direccion)
        self.direccion = Adw.EntryRow(title="Otra dirección (p. ej. turnos.local:8443)", show_apply_button=True)
        self.direccion.connect("apply", lambda e: self.elegir_servidor(e.get_text()))
        self.direccion.connect("entry-activated", lambda e: self.elegir_servidor(e.get_text()))
        self._servidores.add(self.direccion)
        pagina.add(self._servidores)

        pie = Adw.PreferencesGroup()
        self.recordar = Gtk.CheckButton(label="Recordar mi elección y no volver a preguntar", halign=Gtk.Align.CENTER,
                                        tooltip_text="Se puede cambiar en el menú › Conexión…")
        self._mensaje = Gtk.Label(wrap=True, css_classes=["error"], visible=False)
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        caja.append(self._mensaje)
        caja.append(self.recordar)
        pie.add(caja)
        pagina.add(pie)
        self.set_child(pagina)
        en_hilo(cx.buscar_servidores, self._encontrados, lambda _m: self._encontrados([]))

    def _fila_servidor(self, nombre: str, direccion: str) -> None:
        if direccion in self.filas_servidor:
            return
        fila = Adw.ActionRow(title=GLib.markup_escape_text(nombre), subtitle=direccion,
                             icon_name="network-server-symbolic", activatable=True)
        fila.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
        fila.connect("activated", lambda _f: self.elegir_servidor(direccion))
        self.filas_servidor[direccion] = fila
        self._servidores.add(fila)

    def _encontrados(self, encontrados) -> None:
        self._servidores.remove(self._buscando)
        for nombre, direccion in encontrados:
            self._fila_servidor(nombre, cx.normalizar(direccion))
        if not encontrados and not self.filas_servidor:
            self._servidores.set_description(
                "No se ha encontrado ninguno en la red: escribe la dirección que muestra el servidor al arrancar.")

    def _error(self, texto: str) -> None:
        self._mensaje.set_label(texto)
        self._mensaje.set_visible(bool(texto))
        self.set_sensitive(True)

    def elegir_local(self) -> None:
        a = self._actual
        conexion = cx.Conexion("personal", a.direccion, a.huella, a.usuario, not self.recordar.get_active())
        cx.guardar(conexion)
        self._elegido(conexion)

    def elegir_servidor(self, texto: str) -> None:
        try:
            direccion = cx.normalizar(texto)
        except ValueError as error:
            self._error(str(error))
            return
        self._error("")
        self.set_sensitive(False)

        def confirmado(pem: str | None) -> None:
            self._elegido(guardar_servidor(direccion, pem, self._actual.usuario, not self.recordar.get_active()))

        confirmar_servidor(self._ventana, direccion, self._actual, confirmado, self._error)


class DialogoEntrar(Adw.Dialog):
    """Usuario y contraseña del servidor. `hecho(respuesta)` recibe la sesión iniciada."""

    def __init__(self, aplicacion: Adw.Application, conexion: cx.Conexion, hecho: Callable[[dict, str], None],
                 nombre_aplicacion: str) -> None:
        super().__init__(title="Entrar", content_width=400, can_close=False)
        self._aplicacion, self._conexion, self._hecho, self._nombre = aplicacion, conexion, hecho, nombre_aplicacion

        pagina = Adw.PreferencesPage()
        vista = Adw.ToolbarView(content=pagina)
        vista.add_top_bar(Adw.HeaderBar(show_end_title_buttons=False))
        self.set_child(vista)

        grupo = Adw.PreferencesGroup(title="Entrar en el servidor", description=conexion.direccion)
        self.usuario = Adw.EntryRow(title="Usuario")
        self.usuario.set_text(conexion.usuario)
        self.contrasena = Adw.PasswordEntryRow(title="Contraseña")
        self.contrasena.connect("entry-activated", lambda _e: self.enviar())
        self.usuario.connect("entry-activated", lambda _e: self.contrasena.grab_focus())
        grupo.add(self.usuario)
        grupo.add(self.contrasena)
        pagina.add(grupo)

        self._mensaje = Gtk.Label(wrap=True, css_classes=["error"], visible=False)
        self._boton = Gtk.Button(label="Entrar", css_classes=["pill", "suggested-action"], halign=Gtk.Align.CENTER)
        self._boton.connect("clicked", lambda _b: self.enviar())
        otra = Gtk.Button(label="Cambiar la conexión…", css_classes=["flat"], halign=Gtk.Align.CENTER)
        otra.connect("clicked", lambda _b: DialogoConexion(aplicacion).present(self))
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for w in (self._mensaje, self._boton, otra):
            caja.append(w)
        pie = Adw.PreferencesGroup()
        pie.add(caja)
        pagina.add(pie)
        (self.contrasena if conexion.usuario else self.usuario).grab_focus()

    def enviar(self) -> None:
        usuario, contrasena = self.usuario.get_text().strip(), self.contrasena.get_text()
        if not usuario or not contrasena:
            return
        self._boton.set_sensitive(False)
        self._mensaje.set_visible(False)

        def fallo(texto: str) -> None:
            self._mensaje.set_label(texto)
            self._mensaje.set_visible(True)
            self._boton.set_sensitive(True)

        def hecho(respuesta) -> None:
            self.force_close()
            self._hecho(respuesta, usuario)

        en_hilo(lambda: cx.entrar(self._conexion, usuario, contrasena, self._nombre), hecho, fallo)
