"""Aplicación FastAPI: API bajo /api y la interfaz compilada en la raíz."""

import mimetypes
import os
import secrets
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from turnos import __version__
from turnos.api import acceso, eventos
from turnos.servicios.periodos import GENERANDO
from turnos.api.rutas import ausencias, cobertura, configuracion, festivos, medicos, periodos, rotaciones

if TYPE_CHECKING:
    from turnos.api.rutas.servidor import EstadoServidor

def _buscar_interfaz() -> Path:
    """Interfaz web compilada: TURNOS_INTERFAZ, la copia dentro del paquete (rueda
    instalada: servidor, Flatpak) o, en desarrollo, `interfaz/dist` del repositorio."""
    if ruta := os.environ.get("TURNOS_INTERFAZ"):
        return Path(ruta)
    en_paquete = Path(__file__).resolve().parents[1] / "web"
    if (en_paquete / "index.html").exists():
        return en_paquete
    return Path(__file__).resolve().parents[3] / "interfaz" / "dist"


INTERFAZ = _buscar_interfaz()
# El manifiesto de la aplicación instalable (Python no conoce la extensión).
mimetypes.add_type("application/manifest+json", ".webmanifest")


def crear_app(
    motor: Engine,
    interfaz: Path | None = INTERFAZ,
    token: str | None = None,
    nombre_cookie: str = "turnos_sesion",
    servidor: "EstadoServidor | None" = None,
) -> FastAPI:
    """Con `token`, la API exige la sesión (diseño del modo escritorio, 7). Con
    `servidor`, modo servidor: usuarios, roles y sesiones (diseño del modo servidor)."""
    app = FastAPI(title="turnosMedicos", version=__version__)
    app.state.motor = motor
    app.state.cerrojo_escritura = threading.Lock()  # ver api/dependencias.py
    eventos.instalar(app)
    _avisar_si_se_genera(app)
    if token is not None:
        _proteger_con_token(app, token, nombre_cookie)
    if servidor is not None:
        from turnos.api.rutas import servidor as rutas_servidor
        from turnos.api.rutas import solicitudes

        acceso.instalar(app, servidor.config.duracion_sesion_dias, servidor.config.https)
        rutas_servidor.instalar(app, servidor)
        app.include_router(solicitudes.router)
    app.include_router(acceso.router_yo)
    for modulo in (medicos, ausencias, festivos, cobertura, configuracion, periodos, rotaciones):
        app.include_router(modulo.router)
    app.include_router(periodos.router_meses)

    @app.exception_handler(IntegrityError)
    def _conflicto(_: Request, error: IntegrityError):
        mensaje = "Ya existe un registro con esos datos"
        if "medico.codigo" in str(error.orig):
            mensaje = "Ya hay un médico con ese código"
        return JSONResponse({"detail": mensaje}, status_code=409)

    if interfaz is not None and (interfaz / "index.html").exists():
        _servir_interfaz(app, interfaz)
    return app


def _avisar_si_se_genera(app: FastAPI) -> None:
    """Si el mes ya se está generando (otro usuario), se responde al momento en lugar
    de esperar al cerrojo de escritura y generarlo otra vez."""

    @app.middleware("http")
    async def _generando(request: Request, siguiente):
        ruta = request.url.path
        if request.method == "POST" and ruta.endswith("/generar") and ruta.startswith("/api/periodos/"):
            partes = ruta.split("/")
            if (int(partes[3]), int(partes[4])) in GENERANDO:
                return JSONResponse({"detail": "Se está generando el calendario de este mes; espera unos segundos."},
                                    status_code=409)
        return await siguiente(request)


SESION_NO_VALIDA = "Sesión no válida: abre turnosMedicos desde su icono o con la orden «turnos»."


def _proteger_con_token(app: FastAPI, token: str, nombre_cookie: str) -> None:
    """Solo quien abrió la aplicación conoce el token: otro usuario del mismo equipo
    no puede usar la API aunque se conecte al puerto local.

    La primera página se abre con `?token=…`; el servidor lo guarda en una cookie
    (HttpOnly, SameSite=Strict) y redirige a la misma dirección sin él. Las
    peticiones a /api llevan la cookie, o la cabecera X-Turnos-Token."""

    @app.middleware("http")
    async def _sesion(request: Request, siguiente):
        recibido = request.query_params.get("token")
        es_api = request.url.path.startswith("/api/")
        if recibido is not None and not es_api and request.method == "GET":
            if not secrets.compare_digest(recibido, token):
                return JSONResponse({"detail": SESION_NO_VALIDA}, status_code=401)
            sin_token = request.url.remove_query_params("token")
            destino = sin_token.path + (f"?{sin_token.query}" if sin_token.query else "")
            respuesta = RedirectResponse(destino, status_code=303)
            respuesta.set_cookie(nombre_cookie, token, httponly=True, samesite="strict", path="/")
            return respuesta
        if es_api:
            dado = request.cookies.get(nombre_cookie) or request.headers.get("x-turnos-token") or ""
            if not secrets.compare_digest(dado, token):
                return JSONResponse({"detail": SESION_NO_VALIDA}, status_code=401)
        return await siguiente(request)


def _servir_interfaz(app: FastAPI, carpeta: Path) -> None:
    """Ficheros estáticos de la interfaz; cualquier otra ruta devuelve index.html
    (la navegación la resuelve React)."""
    app.mount("/assets", StaticFiles(directory=carpeta / "assets"), name="assets")

    @app.get("/{ruta:path}", include_in_schema=False)
    def _spa(ruta: str):
        if ruta.startswith("api/"):
            return JSONResponse({"detail": "No encontrado"}, status_code=404)
        fichero = (carpeta / ruta).resolve()
        if ruta and fichero.is_file() and fichero.is_relative_to(carpeta.resolve()):
            return FileResponse(fichero)
        return FileResponse(carpeta / "index.html")
