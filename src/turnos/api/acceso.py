"""Acceso en el modo servidor: inicio de sesión, permisos por rol y cuentas
(diseño del modo servidor, 6.1–6.3 y 13).

Todo pasa por un middleware que, para cada petición a /api:

1. identifica la sesión (cookie `turnos_sesion` o cabecera `Authorization: Bearer`);
2. exige, en las peticiones que modifican, la cabecera `X-Cliente` (un formulario de
   otra web no puede enviarla) y que el origen, si viene, sea el propio servidor;
3. comprueba el permiso del rol con la tabla `_permitido`. Lo que no aparece en ella
   solo lo pueden hacer el planificador y el administrador: una ruta nueva queda
   cerrada a los médicos aunque se olvide añadirla.

En el modo personal nada de esto se instala: quien abre la aplicación es administrador.
"""

import re
from datetime import datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from turnos.api import esquemas as e
from turnos.api.dependencias import SesionBD
from turnos.datos.tablas import Periodo, SesionUsuario, Usuario
from turnos.servicios import usuarios as u

COOKIE = "turnos_sesion"
LECTURA = {"GET", "HEAD", "OPTIONS"}

INICIA_SESION = "Inicia sesión para continuar."
SIN_PERMISO = "No tienes permiso para hacer esto."
CAMBIA_CONTRASENA = "Elige una contraseña nueva para continuar."

limite_usuario = u.LimiteIntentos(maximo=5)
limite_direccion = u.LimiteIntentos(maximo=20)


# --- Permisos -------------------------------------------------------------------------

# Sin sesión.
_PUBLICAS = {("POST", "/api/sesion"), ("GET", "/api/yo"), ("GET", "/api/servidor/publico")}
# Con una contraseña temporal, solo esto.
_CON_TEMPORAL = {("GET", "/api/yo"), ("POST", "/api/yo/contrasena"), ("DELETE", "/api/sesion")}
# Solo el administrador.
_ADMINISTRACION = re.compile(r"^/api/(usuarios|sesiones)(/|$)|^/api/servidor/copias$")

_SOLICITUD_PROPIA = re.compile(r"^/api/solicitudes/\d+/(retirar|aceptar)$")
_MES = re.compile(r"^/api/periodos/(\d+)/(\d+)(?:/(exportar\.xlsx|urgencias-domicilios\.xlsx))?$")
_FICHA = re.compile(r"^/api/medicos/(\d+)(/reglas)?$")
_LECTURAS_MEDICO = re.compile(
    r"^/api/(eventos|yo|horarios|ajustes|medicos|festivos(/anios)?|servidor/publico|periodos/publicados)$"
)


def _permitido(sesion: Session, usuario: dict, metodo: str, ruta: str, consulta: dict) -> bool:
    rol = usuario["rol"]
    if rol == "ADMINISTRADOR":
        return True
    if _ADMINISTRACION.match(ruta):
        return False
    if rol == "PLANIFICADOR":
        return True
    # Médico: consulta su ficha y los meses publicados (D-S2); no modifica nada salvo
    # su contraseña y su sesión. Las solicitudes llegarán en la fase 4.
    if (metodo, ruta) in {("POST", "/api/yo/contrasena"), ("DELETE", "/api/sesion"), ("POST", "/api/solicitudes")}:
        return True
    if metodo == "POST" and _SOLICITUD_PROPIA.match(ruta):  # la ruta comprueba que sea suya
        return True
    if metodo in LECTURA and ruta == "/api/solicitudes":  # solo ve las suyas (lo filtra la ruta)
        return True
    if metodo not in LECTURA:
        return False
    if _LECTURAS_MEDICO.match(ruta):
        return True
    if m := _FICHA.match(ruta):
        return int(m[1]) == usuario["medico_id"]
    if ruta == "/api/ausencias":
        return consulta.get("medico_id") == str(usuario["medico_id"])
    if m := _MES.match(ruta):
        publicado = sesion.scalar(
            select(Periodo.publicado_en).where(Periodo.anio == int(m[1]), Periodo.mes == int(m[2]))
        )
        return publicado is not None
    return False


def _origen_valido(request: Request) -> bool:
    origen = request.headers.get("origin")
    if origen is None:
        return True
    return urlsplit(origen).netloc == request.headers.get("host")


def _token(request: Request) -> str | None:
    cabecera = request.headers.get("authorization", "")
    if cabecera.lower().startswith("bearer "):
        return cabecera[7:].strip()
    return request.cookies.get(COOKIE)


def instalar(app: FastAPI, dias_sesion: int, https: bool) -> None:
    app.state.dias_sesion = dias_sesion
    app.state.https = https

    def identificar(token: str | None, metodo: str, ruta: str, consulta: dict) -> tuple[dict | None, bool]:
        """(usuario, permitido), en un hilo: consulta la base."""
        with Session(app.state.motor) as sesion:
            abierta = u.buscar_sesion(sesion, token, dias_sesion) if token else None
            usuario = None
            if abierta is not None:
                us = abierta.usuario
                usuario = {"id": us.id, "nombre": us.nombre, "rol": us.rol, "medico_id": us.medico_id,
                           "debe_cambiar": us.debe_cambiar, "sesion_id": abierta.id}
            permitido = usuario is not None and _permitido(sesion, usuario, metodo, ruta, consulta)
            if sesion.dirty or sesion.deleted:
                with app.state.cerrojo_escritura:
                    sesion.commit()
            return usuario, permitido

    @app.middleware("http")
    async def _acceso(request: Request, siguiente):
        ruta, metodo = request.url.path, request.method
        if not ruta.startswith("/api/"):
            return await siguiente(request)
        if metodo not in LECTURA and (not request.headers.get("x-cliente") or not _origen_valido(request)):
            return JSONResponse({"detail": "Petición rechazada: no viene de la aplicación."}, status_code=403)
        usuario, permitido = await run_in_threadpool(
            identificar, _token(request), metodo, ruta, dict(request.query_params)
        )
        request.state.usuario = usuario
        if (metodo, ruta) in _PUBLICAS:
            return await siguiente(request)
        if usuario is None:
            return JSONResponse({"detail": INICIA_SESION}, status_code=401)
        if usuario["debe_cambiar"] and (metodo, ruta) not in _CON_TEMPORAL:
            return JSONResponse({"detail": CAMBIA_CONTRASENA}, status_code=403)
        if not permitido:
            return JSONResponse({"detail": SIN_PERMISO}, status_code=403)
        return await siguiente(request)

    app.include_router(router_sesion)
    app.include_router(router_cuentas)


# --- Sesión y «yo» ---------------------------------------------------------------------

router_sesion = APIRouter(prefix="/api", tags=["sesión"])
router_yo = APIRouter(prefix="/api", tags=["sesión"])


def _yo(usuario: Usuario) -> dict:
    return {"modo": "servidor", "id": usuario.id, "nombre": usuario.nombre,
            "nombre_visible": usuario.nombre_visible, "rol": usuario.rol,
            "medico_id": usuario.medico_id, "debe_cambiar": usuario.debe_cambiar}


def _actual(request: Request, sesion: Session) -> Usuario:
    datos = getattr(request.state, "usuario", None)
    if datos is None:
        raise HTTPException(401, INICIA_SESION)
    return sesion.get(Usuario, datos["id"])


@router_yo.get("/yo", response_model=e.Yo)
def yo(request: Request, sesion: SesionBD):
    """Quién está usando la aplicación (en el modo personal, un administrador sin cuenta)."""
    if not hasattr(request.state, "usuario"):  # modo personal: no hay middleware de acceso
        return e.Yo(modo="personal", rol="ADMINISTRADOR")
    return _yo(_actual(request, sesion))


def _dispositivo(request: Request, dado: str | None) -> str:
    if dado:
        return dado
    agente = request.headers.get("user-agent", "")
    for nombre in ("Android", "iPhone", "iPad", "Windows", "Macintosh", "Linux"):
        if nombre in agente:
            navegador = next((n for n in ("Firefox", "Edg", "Chrome", "Safari") if n in agente), "Navegador")
            return f"{navegador.replace('Edg', 'Edge')} en {nombre.replace('Macintosh', 'Mac')}"
    return agente[:200] or "Desconocido"


@router_sesion.post("/sesion", response_model=e.SesionIniciada)
def iniciar_sesion(datos: e.InicioSesion, request: Request, response: Response, sesion: SesionBD):
    claves_usuario = (datos.usuario.strip().lower(),)
    claves_dir = (request.client.host if request.client else "?",)
    if limite_usuario.bloqueado(*claves_usuario) or limite_direccion.bloqueado(*claves_dir):
        raise HTTPException(429, "Demasiados intentos. Espera un minuto y vuelve a probar.")
    usuario = u.autenticar(sesion, datos.usuario, datos.contrasena)
    if usuario is None:
        limite_usuario.fallo(*claves_usuario)
        limite_direccion.fallo(*claves_dir)
        raise HTTPException(401, "Usuario o contraseña incorrectos.")
    limite_usuario.acierto(*claves_usuario)
    u.borrar_caducadas(sesion)
    dias = request.app.state.dias_sesion
    token = u.abrir_sesion(sesion, usuario, _dispositivo(request, datos.dispositivo), dias)
    response.set_cookie(COOKIE, token, max_age=dias * 86400, httponly=True, secure=request.app.state.https,
                        samesite="lax", path="/")
    return {**_yo(usuario), "token": token if datos.aplicacion else None}


@router_sesion.delete("/sesion", status_code=204)
def cerrar_sesion(request: Request, response: Response, sesion: SesionBD):
    datos = request.state.usuario
    abierta = sesion.get(SesionUsuario, datos["sesion_id"]) if datos else None
    if abierta is not None:
        sesion.delete(abierta)
    response.delete_cookie(COOKIE, path="/")


@router_sesion.post("/yo/contrasena", status_code=204)
def cambiar_contrasena(datos: e.CambioContrasena, request: Request, sesion: SesionBD):
    usuario = _actual(request, sesion)
    try:
        u.cambiar_contrasena(sesion, usuario, datos.actual, datos.nueva, conservar=request.state.usuario["sesion_id"])
    except u.ErrorUsuario as error:
        raise HTTPException(422, str(error))


# --- Cuentas y sesiones (administrador) ------------------------------------------------

router_cuentas = APIRouter(prefix="/api", tags=["cuentas"])


def _usuario_o_404(sesion: Session, usuario_id: int) -> Usuario:
    usuario = sesion.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(404, "Usuario no encontrado")
    return usuario


@router_cuentas.get("/usuarios", response_model=list[e.UsuarioSalida])
def listar_usuarios(sesion: SesionBD):
    return sesion.scalars(select(Usuario).order_by(Usuario.activo.desc(), Usuario.nombre_visible)).all()


@router_cuentas.post("/usuarios", response_model=e.ContrasenaTemporal, status_code=201)
def crear_usuario(datos: e.UsuarioNuevo, sesion: SesionBD):
    """Cuenta nueva con una contraseña temporal, que se muestra solo esta vez."""
    temporal = u.contrasena_temporal()
    try:
        usuario = u.crear_usuario(sesion, datos.nombre, datos.nombre_visible, datos.rol, temporal,
                                  medico_id=datos.medico_id, temporal=True)
    except u.ErrorUsuario as error:
        raise HTTPException(422, str(error))
    usuario.activo = datos.activo
    return {"usuario": usuario, "contrasena_temporal": temporal}


@router_cuentas.put("/usuarios/{usuario_id}", response_model=e.UsuarioSalida)
def modificar_usuario(usuario_id: int, datos: e.UsuarioEntrada, request: Request, sesion: SesionBD):
    usuario = _usuario_o_404(sesion, usuario_id)
    if usuario.id == request.state.usuario["id"] and (not datos.activo or datos.rol != "ADMINISTRADOR"):
        raise HTTPException(422, "No puedes quitarte a ti mismo el acceso de administrador")
    try:
        u.modificar_usuario(sesion, usuario, nombre_visible=datos.nombre_visible, rol=datos.rol,
                            medico_id=datos.medico_id, activo=datos.activo)
    except u.ErrorUsuario as error:
        raise HTTPException(422, str(error))
    return usuario


@router_cuentas.post("/usuarios/{usuario_id}/restablecer", response_model=e.ContrasenaTemporal)
def restablecer(usuario_id: int, sesion: SesionBD):
    """Contraseña temporal nueva (para quien la ha olvidado); cierra sus sesiones."""
    usuario = _usuario_o_404(sesion, usuario_id)
    return {"usuario": usuario, "contrasena_temporal": u.restablecer_contrasena(sesion, usuario)}


@router_cuentas.get("/sesiones", response_model=list[e.SesionAbierta])
def listar_sesiones(request: Request, sesion: SesionBD):
    """Dispositivos conectados."""
    actual = request.state.usuario["sesion_id"]
    ahora = datetime.now()
    abiertas = sesion.scalars(
        select(SesionUsuario).where(SesionUsuario.caduca > ahora).order_by(SesionUsuario.ultimo_uso.desc())
    )
    return [
        {"id": s.id, "usuario": s.usuario.nombre, "nombre_visible": s.usuario.nombre_visible,
         "dispositivo": s.dispositivo, "creada": s.creada, "ultimo_uso": s.ultimo_uso, "caduca": s.caduca,
         "actual": s.id == actual}
        for s in abiertas
    ]


@router_cuentas.delete("/sesiones/{sesion_id}", status_code=204)
def cerrar_otra_sesion(sesion_id: int, sesion: SesionBD):
    abierta = sesion.get(SesionUsuario, sesion_id)
    if abierta is None:
        raise HTTPException(404, "Sesión no encontrada")
    sesion.delete(abierta)

