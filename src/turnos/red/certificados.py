"""Autoridad de certificación propia y certificado del servidor (diseño del modo servidor, 7; D-S1).

- La **autoridad** dura 10 años y lleva **restricciones de nombre**: solo vale para
  nombres `.local`, `localhost` y direcciones de redes privadas. Aunque alguien se
  hiciera con su clave, no serviría para suplantar ninguna web de internet.
- El **certificado del servidor** dura un año (los iPhone no aceptan más de 825 días)
  y se renueva solo: al arrancar y cada día, si le queda menos de un mes o si el equipo
  tiene una dirección que no incluye (otra IP de la red).
- Las claves son ECDSA P-256 y se guardan con permisos 600.
"""

import ipaddress
import os
import plistlib
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

NOMBRE_AUTORIDAD = "Autoridad de Turnos médicos"
REDES_PERMITIDAS = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "169.254.0.0/16"]
DURACION_AUTORIDAD = timedelta(days=3650)
DURACION_SERVIDOR = timedelta(days=365)
RENOVAR_ANTES = timedelta(days=30)


@dataclass(frozen=True)
class Ficheros:
    carpeta: Path

    @property
    def clave_autoridad(self) -> Path:
        return self.carpeta / "autoridad.key"

    @property
    def autoridad(self) -> Path:
        return self.carpeta / "autoridad.crt"

    @property
    def clave_servidor(self) -> Path:
        return self.carpeta / "servidor.key"

    @property
    def servidor(self) -> Path:
        return self.carpeta / "servidor.crt"


def _guardar_clave(ruta: Path, clave) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = clave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
    descriptor = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as fichero:
        fichero.write(datos)


def _leer_clave(ruta: Path):
    return serialization.load_pem_private_key(ruta.read_bytes(), password=None)


def leer_certificado(ruta: Path) -> x509.Certificate:
    return x509.load_pem_x509_certificate(ruta.read_bytes())


def huella(certificado: x509.Certificate) -> str:
    """SHA-256 en hexadecimal por parejas (como la muestran navegadores y móviles)."""
    return certificado.fingerprint(hashes.SHA256()).hex(":").upper()


def crear_autoridad(ficheros: Ficheros) -> x509.Certificate:
    clave = ec.generate_private_key(ec.SECP256R1())
    nombre = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, f"{NOMBRE_AUTORIDAD} ({socket.gethostname()})"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Turnos médicos"),
    ])
    ahora = datetime.now(timezone.utc)
    restricciones = x509.NameConstraints(
        permitted_subtrees=[
            x509.DNSName("local"),
            x509.DNSName("localhost"),
            *(x509.IPAddress(ipaddress.ip_network(red)) for red in REDES_PERMITIDAS),
        ],
        excluded_subtrees=None,
    )
    certificado = (
        x509.CertificateBuilder()
        .subject_name(nombre).issuer_name(nombre)
        .public_key(clave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - timedelta(minutes=5))
        .not_valid_after(ahora + DURACION_AUTORIDAD)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                     content_commitment=False, key_encipherment=False, data_encipherment=False,
                                     key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(restricciones, critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(clave.public_key()), critical=False)
        .sign(clave, hashes.SHA256())
    )
    _guardar_clave(ficheros.clave_autoridad, clave)
    ficheros.autoridad.write_bytes(certificado.public_bytes(serialization.Encoding.PEM))
    return certificado


def direcciones_locales() -> list[str]:
    """Direcciones IPv4 de este equipo en la red (sin la de bucle local)."""
    encontradas: list[str] = []
    try:  # la de la ruta por defecto (no envía nada)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))
            encontradas.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            encontradas.append(info[4][0])
    except OSError:
        pass
    vistas = []
    for d in encontradas:
        ip = ipaddress.ip_address(d)
        if not ip.is_loopback and d not in vistas and any(ip in ipaddress.ip_network(r) for r in REDES_PERMITIDAS):
            vistas.append(d)
    return vistas


def nombres_del_servidor(nombre: str) -> tuple[list[str], list[str]]:
    """(nombres, direcciones) que debe incluir el certificado del servidor."""
    equipo = socket.gethostname().split(".")[0].lower()
    nombres = list(dict.fromkeys([f"{nombre}.local", f"{equipo}.local", "localhost"]))
    return nombres, ["127.0.0.1", *direcciones_locales()]


def crear_certificado_servidor(ficheros: Ficheros, nombre: str) -> x509.Certificate:
    autoridad = leer_certificado(ficheros.autoridad)
    clave_autoridad = _leer_clave(ficheros.clave_autoridad)
    clave = ec.generate_private_key(ec.SECP256R1())
    nombres, ips = nombres_del_servidor(nombre)
    ahora = datetime.now(timezone.utc)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, nombres[0])]))
        .issuer_name(autoridad.subject)
        .public_key(clave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - timedelta(minutes=5))
        .not_valid_after(min(ahora + DURACION_SERVIDOR, autoridad.not_valid_after_utc))
        .add_extension(x509.SubjectAlternativeName(
            [x509.DNSName(n) for n in nombres] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
        ), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=False, crl_sign=False,
                                     content_commitment=False, key_encipherment=False, data_encipherment=False,
                                     key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(clave_autoridad.public_key()),
                       critical=False)
        .sign(clave_autoridad, hashes.SHA256())
    )
    _guardar_clave(ficheros.clave_servidor, clave)
    ficheros.servidor.write_bytes(certificado.public_bytes(serialization.Encoding.PEM))
    return certificado


def _necesita_renovarse(ficheros: Ficheros, nombre: str) -> bool:
    if not (ficheros.servidor.exists() and ficheros.clave_servidor.exists()):
        return True
    actual = leer_certificado(ficheros.servidor)
    if actual.not_valid_after_utc - datetime.now(timezone.utc) < RENOVAR_ANTES:
        return True
    if actual.issuer != leer_certificado(ficheros.autoridad).subject:
        return True
    incluidos = actual.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    nombres, ips = nombres_del_servidor(nombre)
    tiene_ips = {str(i) for i in incluidos.get_values_for_type(x509.IPAddress)}
    return not (set(nombres) <= set(incluidos.get_values_for_type(x509.DNSName)) and set(ips) <= tiene_ips)


def preparar(carpeta: Path, nombre: str, *, nueva_autoridad: bool = False) -> tuple[Ficheros, bool]:
    """Crea lo que falte y renueva el certificado del servidor si hace falta.
    Devuelve los ficheros y si se ha (re)creado el del servidor."""
    ficheros = Ficheros(carpeta)
    if nueva_autoridad or not (ficheros.autoridad.exists() and ficheros.clave_autoridad.exists()):
        crear_autoridad(ficheros)
    if nueva_autoridad or _necesita_renovarse(ficheros, nombre):
        crear_certificado_servidor(ficheros, nombre)
        return ficheros, True
    return ficheros, False


def autoridad_der(ficheros: Ficheros) -> bytes:
    return leer_certificado(ficheros.autoridad).public_bytes(serialization.Encoding.DER)


def perfil_ios(ficheros: Ficheros) -> bytes:
    """Perfil de configuración (.mobileconfig) que instala la autoridad en un iPhone o iPad.
    Después hay que activar la confianza total en Ajustes › General › Información ›
    Ajustes de confianza de certificados."""
    autoridad = leer_certificado(ficheros.autoridad)
    identificador = uuid.uuid5(uuid.NAMESPACE_URL, huella(autoridad))
    perfil = {
        "PayloadType": "Configuration",
        "PayloadVersion": 1,
        "PayloadIdentifier": f"local.turnos.autoridad.{identificador}",
        "PayloadUUID": str(identificador).upper(),
        "PayloadDisplayName": "Turnos médicos",
        "PayloadDescription": "Permite abrir el servidor de turnos de la red de casa sin avisos de seguridad.",
        "PayloadOrganization": "Turnos médicos",
        "PayloadContent": [{
            "PayloadType": "com.apple.security.root",
            "PayloadVersion": 1,
            "PayloadIdentifier": f"local.turnos.autoridad.{identificador}.certificado",
            "PayloadUUID": str(uuid.uuid5(identificador, "certificado")).upper(),
            "PayloadDisplayName": NOMBRE_AUTORIDAD,
            "PayloadCertificateFileName": "turnos-autoridad.cer",
            "PayloadContent": autoridad_der(ficheros),
        }],
    }
    return plistlib.dumps(perfil)

