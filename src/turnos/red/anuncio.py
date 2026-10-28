"""Anuncio del servidor en la red con mDNS (diseño del modo servidor, 10.2).

Se publican dos servicios: `_https._tcp` (o `_http._tcp`), para que aparezca en
exploradores de la red, y `_turnosmedicos._tcp`, que buscarán las aplicaciones de
escritorio. El nombre `turnos.local` apunta a las direcciones del equipo.

Necesita la biblioteca `zeroconf` (extra «servidor»); sin ella, no se anuncia y se
avisa: el servidor sigue accesible por su dirección IP.
"""

import socket

from turnos import __version__

TIPO_APLICACION = "_turnosmedicos._tcp.local."


class Anuncio:
    def __init__(self, nombre: str, puerto: int, https: bool, direcciones: list[str]) -> None:
        self.nombre, self.puerto, self.https, self.direcciones = nombre, puerto, https, direcciones
        self._zeroconf = None
        self._servicios = []

    def iniciar(self) -> str | None:
        """Publica los servicios. Devuelve un aviso si no ha sido posible."""
        try:
            from zeroconf import ServiceInfo, Zeroconf
        except ImportError:
            return "No se anuncia en la red: falta la biblioteca zeroconf (pip install 'turnos[servidor]')."
        if not self.direcciones:
            return "No se anuncia en la red: este equipo no tiene ninguna dirección de red local."
        propiedades = {"version": __version__, "https": "1" if self.https else "0", "ruta": "/"}
        servidor = f"{self.nombre}.local."
        direcciones = [socket.inet_aton(d) for d in self.direcciones]
        web = "_https._tcp.local." if self.https else "_http._tcp.local."
        try:
            self._zeroconf = Zeroconf()
            for tipo in (web, TIPO_APLICACION):
                info = ServiceInfo(tipo, f"Turnos médicos.{tipo}", addresses=direcciones, port=self.puerto,
                                   properties=propiedades, server=servidor)
                self._zeroconf.register_service(info, allow_name_change=True)
                self._servicios.append(info)
        except Exception as error:  # noqa: BLE001 — la red no debe impedir arrancar
            self.detener()
            return f"No se anuncia en la red ({error})."
        return None

    def detener(self) -> None:
        if self._zeroconf is None:
            return
        try:
            for info in self._servicios:
                self._zeroconf.unregister_service(info)
            self._zeroconf.close()
        finally:
            self._zeroconf, self._servicios = None, []
