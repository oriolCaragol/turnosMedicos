"""Usuarios, contraseñas y sesiones del modo servidor (diseño del modo servidor, 6.1–6.3).

Las contraseñas se guardan con scrypt (biblioteca estándar) y las sesiones por el
resumen SHA-256 de su token: quien lea la base de datos no puede entrar con ellas.
"""

import base64
import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from turnos.datos.tablas import Medico, SesionUsuario, Usuario

ROLES = ("ADMINISTRADOR", "PLANIFICADOR", "MEDICO")
LONGITUD_MINIMA = 8
# scrypt: 16 MiB de memoria por comprobación (≈0,1 s en una Raspberry Pi 3).
_N, _R, _P = 2**14, 8, 1


class ErrorUsuario(ValueError):
    """Dato de usuario no válido (el mensaje es para mostrarlo tal cual)."""


# --- Contraseñas --------------------------------------------------------------------


def resumir_contrasena(contrasena: str) -> str:
    sal = secrets.token_bytes(16)
    resumen = hashlib.scrypt(contrasena.encode(), salt=sal, n=_N, r=_R, p=_P, dklen=32)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${_N}${_R}${_P}${b64(sal)}${b64(resumen)}"


def comprobar_contrasena(contrasena: str, guardado: str) -> bool:
    try:
        tipo, n, r, p, sal, resumen = guardado.split("$")
        assert tipo == "scrypt"
        calculado = hashlib.scrypt(contrasena.encode(), salt=base64.b64decode(sal),
                                   n=int(n), r=int(r), p=int(p), dklen=32)
    except (ValueError, AssertionError):
        return False
    return hmac.compare_digest(calculado, base64.b64decode(resumen))


# Resumen de una contraseña cualquiera: para tardar lo mismo si el usuario no existe.
_RESUMEN_FALSO = resumir_contrasena(secrets.token_urlsafe(16))


def validar_contrasena(contrasena: str) -> None:
    if len(contrasena) < LONGITUD_MINIMA:
        raise ErrorUsuario(f"La contraseña debe tener al menos {LONGITUD_MINIMA} caracteres")


def contrasena_temporal() -> str:
    """Fácil de dictar o copiar: cuatro grupos de cuatro letras y números sin ambiguos."""
    letras = "abcdefghjkmnpqrstuvwxyz23456789"
    return "-".join("".join(secrets.choice(letras) for _ in range(4)) for _ in range(4))


# --- Usuarios -----------------------------------------------------------------------


def normalizar_nombre(nombre: str) -> str:
    nombre = nombre.strip().lower()
    if not nombre or len(nombre) > 40 or not all(c.isalnum() or c in "._-" for c in nombre):
        raise ErrorUsuario("El nombre de usuario solo puede tener letras, números, «.», «_» y «-» (hasta 40)")
    return nombre


def crear_usuario(
    sesion: Session,
    nombre: str,
    nombre_visible: str,
    rol: str,
    contrasena: str,
    *,
    medico_id: int | None = None,
    temporal: bool = False,
) -> Usuario:
    nombre = normalizar_nombre(nombre)
    if rol not in ROLES:
        raise ErrorUsuario(f"Rol desconocido: {rol}")
    if sesion.scalar(select(Usuario).where(Usuario.nombre == nombre)) is not None:
        raise ErrorUsuario(f"Ya existe el usuario «{nombre}»")
    if not temporal:
        validar_contrasena(contrasena)
    _comprobar_medico(sesion, rol, medico_id)
    usuario = Usuario(
        nombre=nombre, nombre_visible=nombre_visible.strip() or nombre, rol=rol,
        hash_contrasena=resumir_contrasena(contrasena), medico_id=medico_id if rol == "MEDICO" else None,
        activo=True, debe_cambiar=temporal, creado=datetime.now(),
    )
    sesion.add(usuario)
    sesion.flush()
    return usuario


def _comprobar_medico(sesion: Session, rol: str, medico_id: int | None, excepto: int | None = None) -> None:
    if rol != "MEDICO":
        return
    if medico_id is None or sesion.get(Medico, medico_id) is None:
        raise ErrorUsuario("Una cuenta de médico debe estar vinculada a su ficha")
    otro = sesion.scalar(select(Usuario).where(Usuario.medico_id == medico_id, Usuario.id != (excepto or 0)))
    if otro is not None:
        raise ErrorUsuario(f"Esa ficha ya está vinculada a la cuenta «{otro.nombre}»")


def modificar_usuario(
    sesion: Session, usuario: Usuario, *, nombre_visible: str, rol: str, medico_id: int | None, activo: bool
) -> None:
    if rol not in ROLES:
        raise ErrorUsuario(f"Rol desconocido: {rol}")
    _comprobar_medico(sesion, rol, medico_id, excepto=usuario.id)
    deja_de_ser_admin = usuario.rol == "ADMINISTRADOR" and (rol != "ADMINISTRADOR" or not activo)
    if deja_de_ser_admin and administradores_activos(sesion) <= 1:
        raise ErrorUsuario("Debe quedar al menos un administrador activo")
    usuario.nombre_visible = nombre_visible.strip() or usuario.nombre
    usuario.rol = rol
    usuario.medico_id = medico_id if rol == "MEDICO" else None
    usuario.activo = activo
    if not activo:
        cerrar_sesiones(sesion, usuario.id)


def administradores_activos(sesion: Session) -> int:
    return sesion.scalar(
        select(func.count()).select_from(Usuario).where(Usuario.rol == "ADMINISTRADOR", Usuario.activo)
    )


def hay_usuarios(sesion: Session) -> bool:
    return sesion.scalar(select(func.count()).select_from(Usuario)) > 0


def restablecer_contrasena(sesion: Session, usuario: Usuario) -> str:
    """Contraseña temporal nueva (se muestra una vez); cierra sus sesiones."""
    temporal = contrasena_temporal()
    usuario.hash_contrasena = resumir_contrasena(temporal)
    usuario.debe_cambiar = True
    cerrar_sesiones(sesion, usuario.id)
    return temporal


def cambiar_contrasena(sesion: Session, usuario: Usuario, actual: str, nueva: str, *, conservar: int | None) -> None:
    """El propio usuario. Cierra sus demás sesiones (no la `conservar`)."""
    if not comprobar_contrasena(actual, usuario.hash_contrasena):
        raise ErrorUsuario("La contraseña actual no es correcta")
    validar_contrasena(nueva)
    if nueva == actual:
        raise ErrorUsuario("La contraseña nueva debe ser distinta de la actual")
    usuario.hash_contrasena = resumir_contrasena(nueva)
    usuario.debe_cambiar = False
    cerrar_sesiones(sesion, usuario.id, excepto=conservar)


def autenticar(sesion: Session, nombre: str, contrasena: str) -> Usuario | None:
    try:
        nombre = normalizar_nombre(nombre)
    except ErrorUsuario:
        nombre = ""
    usuario = sesion.scalar(select(Usuario).where(Usuario.nombre == nombre)) if nombre else None
    if usuario is None:
        comprobar_contrasena(contrasena, _RESUMEN_FALSO)
        return None
    if not comprobar_contrasena(contrasena, usuario.hash_contrasena) or not usuario.activo:
        return None
    return usuario


# --- Sesiones -----------------------------------------------------------------------


def resumir_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def abrir_sesion(sesion: Session, usuario: Usuario, dispositivo: str, dias: int) -> str:
    """Crea la sesión y devuelve su token (solo lo conoce el cliente)."""
    token = secrets.token_urlsafe(32)
    ahora = datetime.now()
    sesion.add(SesionUsuario(
        hash_token=resumir_token(token), usuario_id=usuario.id, dispositivo=(dispositivo or "Desconocido")[:200],
        creada=ahora, ultimo_uso=ahora, caduca=ahora + timedelta(days=dias),
    ))
    sesion.flush()
    return token


def buscar_sesion(sesion: Session, token: str, dias: int) -> SesionUsuario | None:
    """La sesión de ese token si sigue valiendo; alarga su caducidad con el uso."""
    abierta = sesion.scalar(select(SesionUsuario).where(SesionUsuario.hash_token == resumir_token(token)))
    ahora = datetime.now()
    if abierta is None:
        return None
    if abierta.caduca <= ahora or not abierta.usuario.activo:
        sesion.delete(abierta)
        return None
    if ahora - abierta.ultimo_uso > timedelta(minutes=5):  # no escribir en cada petición
        abierta.ultimo_uso = ahora
        abierta.caduca = ahora + timedelta(days=dias)
    return abierta


def cerrar_sesiones(sesion: Session, usuario_id: int, excepto: int | None = None) -> None:
    for s in sesion.scalars(select(SesionUsuario).where(SesionUsuario.usuario_id == usuario_id)):
        if s.id != excepto:
            sesion.delete(s)


def borrar_caducadas(sesion: Session) -> None:
    for s in sesion.scalars(select(SesionUsuario).where(SesionUsuario.caduca <= datetime.now())):
        sesion.delete(s)


# --- Límite de intentos -------------------------------------------------------------


class LimiteIntentos:
    """Como mucho `maximo` intentos fallidos por minuto para cada usuario (y para cada
    dirección), para que no se puedan probar contraseñas a ciegas."""

    def __init__(self, maximo: int = 5, ventana: float = 60.0) -> None:
        self.maximo, self.ventana = maximo, ventana
        self._fallos: dict[str, deque[float]] = defaultdict(deque)
        self._cerrojo = threading.Lock()

    def _vigentes(self, clave: str, ahora: float) -> deque[float]:
        fallos = self._fallos[clave]
        while fallos and ahora - fallos[0] > self.ventana:
            fallos.popleft()
        return fallos

    def bloqueado(self, *claves: str) -> bool:
        ahora = time.monotonic()
        with self._cerrojo:
            return any(len(self._vigentes(c, ahora)) >= self.maximo for c in claves)

    def fallo(self, *claves: str) -> None:
        ahora = time.monotonic()
        with self._cerrojo:
            for c in claves:
                self._vigentes(c, ahora).append(ahora)

    def acierto(self, *claves: str) -> None:
        with self._cerrojo:
            for c in claves:
                self._fallos.pop(c, None)
