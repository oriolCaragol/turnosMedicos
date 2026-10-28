"""Cliente de la API (la local o la de un servidor de la red), con las peticiones en un
hilo para no bloquear la ventana."""

import json
import ssl
import threading
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from typing import Any

from gi.repository import GLib


class ErrorApi(RuntimeError):
    """Error que devuelve la API, con su mensaje para el usuario y el código HTTP."""

    def __init__(self, mensaje: str, estado: int | None = None) -> None:
        super().__init__(mensaje)
        self.estado = estado


class ClienteApi:
    """`token`: el del servidor interno (modo personal). `sesion` y `contexto`: los de un
    servidor de la red (diseño del modo servidor, 11.2); `sin_sesion` se llama (en el hilo
    de la interfaz) si el servidor responde 401: la sesión ha caducado o la han cerrado."""

    def __init__(
        self,
        base: str,
        token: str | None,
        *,
        sesion: str | None = None,
        contexto: ssl.SSLContext | None = None,
        sin_sesion: Callable[[], None] | None = None,
    ) -> None:
        self.base = base.rstrip("/")
        self.token = token
        self.sesion = sesion
        self.contexto = contexto
        self.sin_sesion = sin_sesion
        # Identifica a esta ventana en los eventos del servidor (diseño del modo servidor, 9).
        self.id = uuid.uuid4().hex
        self._parar = threading.Event()

    def _cabeceras(self) -> dict[str, str]:
        cabeceras = {"X-Cliente": self.id}
        if self.token:
            cabeceras["X-Turnos-Token"] = self.token
        if self.sesion:
            cabeceras["Authorization"] = f"Bearer {self.sesion}"
        return cabeceras

    def pedir(
        self, metodo: str, ruta: str, cuerpo: Any = None, *, binario: bool = False, cabeceras: dict | None = None
    ) -> Any:
        """Petición síncrona (en un hilo, no en el de la interfaz)."""
        datos, cabeceras = None, {**self._cabeceras(), **(cabeceras or {})}
        if isinstance(cuerpo, bytes):
            datos, cabeceras["Content-Type"] = cuerpo, "application/octet-stream"
        elif cuerpo is not None:
            datos, cabeceras["Content-Type"] = json.dumps(cuerpo).encode(), "application/json"
        peticion = urllib.request.Request(f"{self.base}/api{ruta}", data=datos, method=metodo, headers=cabeceras)
        try:
            with urllib.request.urlopen(peticion, timeout=120, context=self.contexto) as respuesta:
                contenido = respuesta.read()
        except urllib.error.HTTPError as error:
            if error.code == 401 and self.sin_sesion:
                GLib.idle_add(self.sin_sesion)
            raise ErrorApi(_mensaje(error), error.code) from error
        except urllib.error.URLError as error:
            donde = "el servidor" if self.sesion else "el servidor interno"
            raise ErrorApi(f"No se puede conectar con {donde} ({error.reason}).") from error
        if binario:
            return contenido
        return json.loads(contenido) if contenido else None

    def en_segundo_plano(
        self,
        metodo: str,
        ruta: str,
        cuerpo: Any = None,
        *,
        hecho: Callable[[Any], None],
        fallo: Callable[[str], None],
        binario: bool = False,
        cabeceras: dict | None = None,
        conflicto: Callable[[str], None] | None = None,
    ) -> None:
        """Hace la petición en un hilo y llama a `hecho` o `fallo` en el hilo de la interfaz
        (o a `conflicto`, si se indica y el servidor responde 409)."""

        def trabajar() -> None:
            try:
                resultado = self.pedir(metodo, ruta, cuerpo, binario=binario, cabeceras=cabeceras)
            except ErrorApi as error:
                GLib.idle_add(conflicto if conflicto and error.estado == 409 else fallo, str(error))
            else:
                GLib.idle_add(hecho, resultado)

        threading.Thread(target=trabajar, daemon=True).start()

    def escuchar(self, evento: Callable[[dict], None]) -> None:
        """Escucha en un hilo los cambios del servidor (GET /api/eventos) y llama a `evento`
        en el hilo de la interfaz con los de otros clientes. Si se pierde la conexión,
        reconecta y avisa con {"tipo": "todo"}: pueden haberse perdido eventos."""

        def trabajar() -> None:
            perdida = False
            while not self._parar.is_set():
                peticion = urllib.request.Request(f"{self.base}/api/eventos", headers=self._cabeceras())
                try:
                    # El servidor envía un latido cada 15 s: sin nada en 40 s, la conexión se da por perdida.
                    with urllib.request.urlopen(peticion, timeout=40, context=self.contexto) as respuesta:
                        if perdida:
                            GLib.idle_add(evento, {"tipo": "todo"})
                            perdida = False
                        for linea in respuesta:
                            if self._parar.is_set():
                                return
                            if not linea.startswith(b"data:"):
                                continue
                            try:
                                datos = json.loads(linea[5:])
                            except ValueError:
                                continue
                            if datos.get("origen") != self.id:
                                GLib.idle_add(evento, datos)
                except (OSError, urllib.error.URLError):
                    pass
                perdida = True
                self._parar.wait(3)

        threading.Thread(target=trabajar, daemon=True).start()

    def parar(self) -> None:
        """Deja de escuchar los eventos."""
        self._parar.set()


def _mensaje(error: urllib.error.HTTPError) -> str:
    try:
        detalle = json.loads(error.read()).get("detail")
    except (ValueError, AttributeError):
        detalle = None
    if isinstance(detalle, str):
        return detalle
    if isinstance(detalle, list) and detalle:
        return ". ".join(str(d.get("msg", d)).removeprefix("Value error, ") for d in detalle)
    return f"Error del servidor ({error.code})"
