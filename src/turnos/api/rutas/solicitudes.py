"""Solicitudes de los médicos (diseño del modo servidor, 6.4). Solo en el modo servidor.

Quién puede qué lo decide, en general, `api/acceso.py`; aquí se comprueba además de
quién es cada solicitud (un médico solo ve y retira las suyas, y solo acepta los
intercambios que le proponen)."""

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from turnos.api import esquemas as e
from turnos.api.dependencias import SesionBD
from turnos.datos.tablas import Solicitud, Usuario
from turnos.servicios import solicitudes as s

router = APIRouter(prefix="/api/solicitudes", tags=["solicitudes"])


def _usuario(request: Request, sesion: Session) -> Usuario:
    return sesion.get(Usuario, request.state.usuario["id"])


def _salida(sesion: Session, solicitud: Solicitud, usuario: Usuario) -> dict:
    return {
        "id": solicitud.id, "tipo": solicitud.tipo, "estado": solicitud.estado,
        "medico_id": solicitud.medico_id, "medico": solicitud.medico.nombre,
        "companero_id": solicitud.companero_id,
        "companero": solicitud.companero.nombre if solicitud.companero else None,
        "propuesta": s.propuesta(solicitud), "descripcion": s.describir(sesion, solicitud),
        "comentario": solicitud.comentario, "respuesta_companero": solicitud.respuesta_companero,
        "creada": solicitud.creada,
        "resuelta_por": solicitud.resuelta_por.nombre_visible if solicitud.resuelta_por else None,
        "resuelta_en": solicitud.resuelta_en, "comentario_resolucion": solicitud.comentario_resolucion,
        "mia": usuario.medico_id is not None and solicitud.medico_id == usuario.medico_id,
        "me_toca_aceptar": solicitud.estado == "ESPERA_COMPANERO" and usuario.medico_id is not None
        and solicitud.companero_id == usuario.medico_id,
    }


def _visible(sesion: Session, solicitud_id: int, usuario: Usuario) -> Solicitud:
    solicitud = sesion.get(Solicitud, solicitud_id)
    if solicitud is None:
        raise HTTPException(404, "Solicitud no encontrada")
    if usuario.rol == "MEDICO" and usuario.medico_id not in (solicitud.medico_id, solicitud.companero_id):
        raise HTTPException(404, "Solicitud no encontrada")  # como si no existiera
    return solicitud


def _avisar(request: Request, *eventos: dict) -> None:
    """Eventos que se publican tras confirmar (además del de «solicitudes»)."""
    request.state.eventos = [*getattr(request.state, "eventos", []), *eventos]


@router.get("", response_model=list[e.SolicitudSalida])
def listar(request: Request, sesion: SesionBD, estado: str | None = None):
    """Médico: las suyas y los intercambios que le proponen. Planificador: todas. Las
    abiertas primero; después, las más recientes."""
    usuario = _usuario(request, sesion)
    consulta = select(Solicitud).order_by(Solicitud.id.desc())
    if usuario.rol == "MEDICO":
        consulta = consulta.where(or_(Solicitud.medico_id == usuario.medico_id,
                                      Solicitud.companero_id == usuario.medico_id))
    if estado:
        consulta = consulta.where(Solicitud.estado.in_(estado.split(",")))
    lista = sesion.scalars(consulta.limit(500)).all()
    lista = sorted(lista, key=lambda x: x.estado not in s.ABIERTAS)
    return [_salida(sesion, x, usuario) for x in lista]


@router.post("", response_model=e.SolicitudSalida, status_code=201)
def crear(datos: e.SolicitudEntrada, request: Request, sesion: SesionBD):
    usuario = _usuario(request, sesion)
    propuesta = datos.propuesta.model_dump(mode="json", exclude={"tipo"})
    try:
        solicitud = s.crear(sesion, usuario, datos.propuesta.tipo, propuesta, datos.comentario)
    except s.SolicitudNoValida as error:
        raise HTTPException(422, str(error))
    return _salida(sesion, solicitud, usuario)


@router.post("/{solicitud_id}/retirar", response_model=e.SolicitudSalida)
def retirar(solicitud_id: int, request: Request, sesion: SesionBD):
    usuario = _usuario(request, sesion)
    solicitud = _visible(sesion, solicitud_id, usuario)
    try:
        s.retirar(solicitud, usuario)
    except PermissionError:
        raise HTTPException(403, "Solo quien la pidió puede retirarla")
    except s.SolicitudNoValida as error:
        raise HTTPException(409, str(error))
    return _salida(sesion, solicitud, usuario)


@router.post("/{solicitud_id}/aceptar", response_model=e.SolicitudSalida)
def aceptar(solicitud_id: int, datos: e.RespuestaCompanero, request: Request, sesion: SesionBD):
    """El otro médico de un intercambio acepta (llega al planificador) o no (D-S8)."""
    usuario = _usuario(request, sesion)
    solicitud = _visible(sesion, solicitud_id, usuario)
    try:
        s.responder_companero(solicitud, usuario, datos.acepta, datos.comentario)
    except PermissionError:
        raise HTTPException(403, "Solo el compañero del intercambio puede responder")
    except s.SolicitudNoValida as error:
        raise HTTPException(409, str(error))
    return _salida(sesion, solicitud, usuario)


@router.get("/{solicitud_id}/efectos", response_model=e.EfectosSolicitud)
def efectos(solicitud_id: int, request: Request, sesion: SesionBD):
    """Qué avisos produciría aprobarla (se prueba y se deshace)."""
    usuario = _usuario(request, sesion)
    solicitud = _visible(sesion, solicitud_id, usuario)
    # Se escribe (y se deshace) en la base: con el cerrojo, como una escritura.
    with request.app.state.cerrojo_escritura:
        resultado = s.efectos(sesion, solicitud)
    return {"avisos": resultado.avisos, "meses": resultado.meses}


@router.post("/{solicitud_id}/aprobar", response_model=e.SolicitudSalida)
def aprobar(solicitud_id: int, datos: e.Resolucion, request: Request, sesion: SesionBD):
    usuario = _usuario(request, sesion)
    solicitud = _visible(sesion, solicitud_id, usuario)
    try:
        meses = s.aprobar(sesion, solicitud, usuario, datos.comentario, datos.aplicar)
    except s.SolicitudNoValida as error:
        raise HTTPException(409, str(error))
    if datos.aplicar:
        tipo = {"DISPONIBILIDAD": "medicos", "AUSENCIA": "ausencias"}.get(solicitud.tipo)
        _avisar(request, *([{"tipo": tipo}] if tipo else []),
                *({"tipo": "calendario", "anio": a, "mes": m} for a, m in meses))
    return _salida(sesion, solicitud, usuario)


@router.post("/{solicitud_id}/rechazar", response_model=e.SolicitudSalida)
def rechazar(solicitud_id: int, datos: e.Resolucion, request: Request, sesion: SesionBD):
    usuario = _usuario(request, sesion)
    solicitud = _visible(sesion, solicitud_id, usuario)
    try:
        s.rechazar(solicitud, usuario, datos.comentario)
    except s.SolicitudNoValida as error:
        raise HTTPException(409, str(error))
    return _salida(sesion, solicitud, usuario)
