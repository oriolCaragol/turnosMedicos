"""Arranque del servidor, compartido por el modo web y el de escritorio
(diseño del modo escritorio, sección 6)."""

import secrets
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import uvicorn

from turnos.api.app import crear_app
from turnos.config import ruta_datos
from turnos.datos.bd import inicializar


@dataclass
class Servidor:
    """Servidor preparado (con el puerto ya reservado) pero aún sin arrancar."""

    puerto: int
    token: str | None
    _uvicorn: uvicorn.Server
    _socket: socket.socket
    _hilo: threading.Thread | None = None
    error: BaseException | None = field(default=None, repr=False)

    @property
    def url(self) -> str:
        """Dirección para abrir la interfaz (con el token, si lo hay)."""
        base = f"http://127.0.0.1:{self.puerto}/"
        return f"{base}?token={self.token}" if self.token else base

    def ejecutar(self) -> None:
        """Arranca y bloquea hasta que se detiene (modo web: Ctrl+C)."""
        try:
            self._uvicorn.run(sockets=[self._socket])
        finally:
            self._uvicorn.config.app.state.motor.dispose()

    def iniciar_en_hilo(self, espera: float = 20.0) -> None:
        """Arranca en un hilo y vuelve cuando ya acepta conexiones (modo escritorio)."""

        def correr() -> None:
            try:
                self.ejecutar()
            except BaseException as e:  # noqa: BLE001 — se muestra en la ventana
                self.error = e

        self._hilo = threading.Thread(target=correr, name="servidor-turnos", daemon=True)
        self._hilo.start()
        limite = time.monotonic() + espera
        while not self._uvicorn.started:
            if self.error is not None or not self._hilo.is_alive():
                raise RuntimeError(f"El servidor no ha podido arrancar: {self.error}") from self.error
            if time.monotonic() > limite:
                raise TimeoutError("El servidor tarda demasiado en arrancar")
            time.sleep(0.02)

    def esperar_peticiones(self, minimo: float = 0.3, maximo: float = 5.0) -> None:
        """Espera a que terminen las peticiones en curso (los guardados que la página
        envía al cerrarse); `minimo` da tiempo a que lleguen."""
        time.sleep(minimo)
        limite = time.monotonic() + maximo
        while self._uvicorn.server_state.tasks and time.monotonic() < limite:
            time.sleep(0.05)

    def detener(self, espera: float = 5.0) -> None:
        # Las conexiones de eventos no terminan solas: se cierran para no esperarlas.
        self._uvicorn.config.app.state.difusor.cerrar()
        self._uvicorn.should_exit = True
        if self._hilo is not None:
            self._hilo.join(espera)
        # Cierra las conexiones a la base (con WAL, así se vuelcan los cambios al fichero).
        self._uvicorn.config.app.state.motor.dispose()


def preparar(*, puerto: int = 0, con_token: bool = True, ruta: Path | None = None) -> Servidor:
    """Inicializa los datos (migraciones con copia previa), reserva el puerto en
    127.0.0.1 (0 = uno libre al azar) y crea la aplicación.

    Puede lanzar `DatosMasNuevos` (datos de una versión más reciente) u `OSError`
    (puerto ocupado)."""
    motor = inicializar(ruta or ruta_datos())
    conexion = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    conexion.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    conexion.bind(("127.0.0.1", puerto))
    puerto_real = conexion.getsockname()[1]
    token = secrets.token_urlsafe(32) if con_token else None
    app = crear_app(motor, token=token, nombre_cookie=f"turnos_sesion_{puerto_real}")
    config = uvicorn.Config(app, log_level="warning", timeout_graceful_shutdown=3)
    return Servidor(puerto_real, token, uvicorn.Server(config), conexion)
