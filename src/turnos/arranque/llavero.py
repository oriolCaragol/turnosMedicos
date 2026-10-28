"""La sesión de la aplicación nativa en un servidor, guardada en el llavero de GNOME
(libsecret), no en un fichero (diseño del modo servidor, 11.2).

Si no hay llavero disponible (otro escritorio, pruebas), no se guarda: habrá que
volver a entrar al abrir la aplicación.
"""

import gi

try:
    gi.require_version("Secret", "1")
    from gi.repository import Secret
except (ImportError, ValueError):  # sin libsecret
    Secret = None

_ESQUEMA = (
    Secret.Schema.new(
        "io.oriol.TurnosMedicos.Sesion",
        Secret.SchemaFlags.NONE,
        {"servidor": Secret.SchemaAttributeType.STRING, "usuario": Secret.SchemaAttributeType.STRING},
    )
    if Secret
    else None
)


def guardar(servidor: str, usuario: str, token: str) -> bool:
    if _ESQUEMA is None:
        return False
    try:
        return Secret.password_store_sync(
            _ESQUEMA, {"servidor": servidor, "usuario": usuario}, Secret.COLLECTION_DEFAULT,
            f"Turnos médicos: sesión de {usuario} en {servidor}", token, None,
        )
    except Exception:  # noqa: BLE001 — sin servicio de secretos
        return False


def leer(servidor: str, usuario: str) -> str | None:
    if _ESQUEMA is None or not usuario:
        return None
    try:
        return Secret.password_lookup_sync(_ESQUEMA, {"servidor": servidor, "usuario": usuario}, None)
    except Exception:  # noqa: BLE001
        return None


def borrar(servidor: str, usuario: str) -> None:
    if _ESQUEMA is None or not usuario:
        return
    try:
        Secret.password_clear_sync(_ESQUEMA, {"servidor": servidor, "usuario": usuario}, None)
    except Exception:  # noqa: BLE001
        pass
