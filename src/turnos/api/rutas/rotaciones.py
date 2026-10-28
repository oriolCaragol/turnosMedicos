"""Turnos rotativos entre grupos de médicos (especificaciones, 5.8)."""

from fastapi import APIRouter, HTTPException

from turnos.api import esquemas as e
from turnos.api.dependencias import SesionBD, obtener_o_404
from turnos.datos.tablas import RotacionTabla
from turnos.servicios import rotaciones as s

router = APIRouter(prefix="/api/rotaciones", tags=["turnos rotativos"])


def _salida(r: RotacionTabla) -> e.Rotacion:
    return e.Rotacion(
        id=r.id,
        nombre=r.nombre,
        desde=r.desde,
        activa=r.activa,
        medicos=[m.medico_id for m in r.miembros],
        huecos=[e.HuecoSemanal(dia_semana=h.dia_semana, turno=h.turno) for h in r.huecos],
    )


def _datos(entrada: e.RotacionEntrada) -> s.DatosRotacion:
    return s.DatosRotacion(
        nombre=entrada.nombre,
        desde=entrada.desde,
        activa=entrada.activa,
        medicos=entrada.medicos,
        huecos=[(h.dia_semana, h.turno) for h in entrada.huecos],
    )


@router.get("", response_model=list[e.Rotacion])
def listar(sesion: SesionBD):
    return [_salida(r) for r in s.listar(sesion)]


@router.post("", response_model=e.Rotacion, status_code=201)
def crear(datos: e.RotacionEntrada, sesion: SesionBD):
    try:
        return _salida(s.guardar(sesion, _datos(datos)))
    except s.RotacionNoValida as error:
        raise HTTPException(422, str(error))


@router.put("/{rotacion_id}", response_model=e.Rotacion)
def modificar(rotacion_id: int, datos: e.RotacionEntrada, sesion: SesionBD):
    rotacion = obtener_o_404(sesion, RotacionTabla, rotacion_id, "Turno rotativo")
    try:
        return _salida(s.guardar(sesion, _datos(datos), rotacion))
    except s.RotacionNoValida as error:
        raise HTTPException(422, str(error))


@router.delete("/{rotacion_id}", status_code=204)
def borrar(rotacion_id: int, sesion: SesionBD):
    sesion.delete(obtener_o_404(sesion, RotacionTabla, rotacion_id, "Turno rotativo"))
