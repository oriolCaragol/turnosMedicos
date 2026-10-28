"""A qué núcleo se conectan las aplicaciones de escritorio (diseño del modo servidor, 11.2).

- **Este equipo** (modo personal, el de siempre): arrancan su propio servidor interno.
- **Un servidor de la red**: se conectan a `turnos servidor`. La primera vez se descarga
  el certificado de su autoridad y el usuario confirma su huella (como hace SSH); a
  partir de ahí solo se confía en esa autoridad para hablar con ese servidor.

Se guarda en `~/.config/turnosMedicos/conexion.json` (y la autoridad, al lado). La
sesión de la aplicación nativa va en el llavero de GNOME (`llavero.py`).

Dentro de Flatpak los nombres `.local` no suelen resolverse (el runtime no incluye
mDNS): `resolver` los busca con zeroconf y devuelve la dirección IP, que también está
en el certificado del servidor.
"""

import hashlib
import json
import socket
import ssl
import time
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from turnos.config import carpeta_configuracion

TIPO_SERVICIO = "_turnosmedicos._tcp.local."


def carpeta() -> Path:
    return carpeta_configuracion()


@dataclass
class Conexion:
    modo: str = "personal"  # «personal» o «servidor»
    direccion: str = ""  # el último servidor (se recuerda aunque se use este equipo)
    huella: str = ""  # SHA-256 de su autoridad, confirmada
    usuario: str = ""  # el último que entró (para rellenarlo)
    preguntar: bool = True  # al abrir, preguntar dónde trabajar (o usar directamente `modo`)

    @property
    def en_servidor(self) -> bool:
        return self.modo == "servidor" and bool(self.direccion)

    @property
    def https(self) -> bool:
        return self.direccion.startswith("https://")

    @property
    def autoridad(self) -> Path:
        return carpeta() / "conexion-autoridad.pem"


def leer() -> Conexion:
    try:
        datos = json.loads((carpeta() / "conexion.json").read_text(encoding="utf-8"))
        return Conexion(**{
            k: bool(v) if k == "preguntar" else str(v)
            for k, v in datos.items() if k in Conexion.__dataclass_fields__
        })
    except (OSError, ValueError, TypeError):
        return Conexion()


def guardar(conexion: Conexion, autoridad_pem: str | None = None) -> None:
    carpeta().mkdir(parents=True, exist_ok=True)
    if autoridad_pem is not None:
        conexion.autoridad.write_text(autoridad_pem, encoding="ascii")
    (carpeta() / "conexion.json").write_text(json.dumps(asdict(conexion), indent=2), encoding="utf-8")


def normalizar(direccion: str) -> str:
    """«turnos.local» → «https://turnos.local:8443» (lo habitual); quita la barra final."""
    direccion = direccion.strip().rstrip("/")
    if "://" not in direccion:
        direccion = f"https://{direccion}"
    partes = urlsplit(direccion)
    if partes.scheme not in ("http", "https") or not partes.hostname:
        raise ValueError("Dirección no válida: escribe algo como turnos.local:8443")
    netloc = partes.netloc if partes.port else f"{partes.hostname}:8443"
    return urlunsplit((partes.scheme, netloc, "", "", ""))


# --- Certificado ------------------------------------------------------------------------


def huella_pem(pem: str) -> str:
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest().upper()


def formatear_huella(huella: str) -> str:
    return ":".join(huella[i:i + 2] for i in range(0, len(huella), 2))


def descargar_autoridad(direccion: str) -> str:
    """Certificado de la autoridad del servidor, **sin verificar** (aún no se conoce): el
    usuario debe comprobar su huella antes de guardarlo."""
    sin_verificar = ssl._create_unverified_context()  # noqa: S323 — la verificación es la huella
    with urllib.request.urlopen(f"{resolver(direccion)}/certificado/turnos-autoridad.pem",
                                context=sin_verificar, timeout=10) as respuesta:
        return respuesta.read().decode("ascii")


def contexto_ssl(conexion: Conexion) -> ssl.SSLContext | None:
    """Solo se confía en la autoridad confirmada para ese servidor."""
    if not conexion.https:
        return None
    return ssl.create_default_context(cafile=str(conexion.autoridad))


# --- Sesión ----------------------------------------------------------------------------


def entrar(conexion: Conexion, usuario: str, contrasena: str, aplicacion: str) -> dict:
    """Inicia sesión en el servidor y devuelve la respuesta (con el token de la sesión)."""
    dispositivo = f"{aplicacion} en {socket.gethostname().split('.')[0]}"
    datos = json.dumps({"usuario": usuario, "contrasena": contrasena, "aplicacion": True,
                        "dispositivo": dispositivo}).encode()
    peticion = urllib.request.Request(
        f"{resolver(conexion.direccion)}/api/sesion", data=datos, method="POST",
        headers={"Content-Type": "application/json", "X-Cliente": "inicio-de-sesion"},
    )
    with urllib.request.urlopen(peticion, context=contexto_ssl(conexion), timeout=20) as respuesta:
        return json.loads(respuesta.read())


# --- Red: mDNS -------------------------------------------------------------------------


def buscar_servidores(segundos: float = 2.5) -> list[tuple[str, str]]:
    """Servidores anunciados en la red: [(nombre, dirección)]. Vacía sin zeroconf."""
    try:
        from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
    except ImportError:
        return []
    encontrados: dict[str, str] = {}

    class Oyente(ServiceListener):
        def add_service(self, zc, tipo, nombre):
            info = zc.get_service_info(tipo, nombre, timeout=1500)
            if info is None:
                return
            https = (info.properties or {}).get(b"https", b"1") == b"1"
            servidor = (info.server or "").rstrip(".")
            if servidor:
                encontrados[nombre.split(".")[0]] = f"{'https' if https else 'http'}://{servidor}:{info.port}"

        def update_service(self, zc, tipo, nombre):
            self.add_service(zc, tipo, nombre)

        def remove_service(self, zc, tipo, nombre):
            pass

    zc = Zeroconf()
    try:
        ServiceBrowser(zc, TIPO_SERVICIO, Oyente())
        time.sleep(segundos)
    finally:
        zc.close()
    return sorted(encontrados.items())


_resueltos: dict[str, str] = {}


def resolver(direccion: str) -> str:
    """La misma dirección, con la IP en lugar del nombre `.local` si el sistema no lo
    resuelve (Flatpak). Si no se encuentra, la devuelve tal cual."""
    partes = urlsplit(direccion)
    nombre = partes.hostname or ""
    if not nombre.endswith(".local"):
        return direccion
    try:
        socket.getaddrinfo(nombre, partes.port, socket.AF_INET)
        return direccion
    except OSError:
        pass
    ip = _resueltos.get(nombre) or _resolver_mdns(nombre)
    if not ip:
        return direccion
    _resueltos[nombre] = ip
    return urlunsplit((partes.scheme, f"{ip}:{partes.port}" if partes.port else ip, partes.path, partes.query, ""))


def _resolver_mdns(nombre: str) -> str | None:
    try:
        from zeroconf import AddressResolver, Zeroconf
    except ImportError:
        return None
    zc = Zeroconf()
    try:
        resolucion = AddressResolver(f"{nombre}.")
        if resolucion.request(zc, 3000):
            direcciones = resolucion.parsed_addresses()
            return next((d for d in direcciones if ":" not in d), None)
    finally:
        zc.close()
    return None
