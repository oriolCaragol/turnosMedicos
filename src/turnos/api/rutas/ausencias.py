"""Ausencias de los médicos (especificaciones, 4.5)."""

from datetime import date

from fastapi import APIRouter
from sqlalchemy import select

from turnos.api import esquemas as e
from turnos.api.dependencias import SesionBD, obtener_o_404
from turnos.datos.tablas import AusenciaMedico, Medico

router = APIRouter(prefix="/api/ausencias", tags=["ausencias"])


@router.get("", response_model=list[e.Ausencia])
def listar(
    sesion: SesionBD,
    medico_id: int | None = None,
    desde: date | None = None,
    hasta: date | None = None,
):
    """Ausencias que se solapan con el rango [desde, hasta]."""
    consulta = select(AusenciaMedico).order_by(AusenciaMedico.desde, AusenciaMedico.medico_id)
    if medico_id is not None:
        consulta = consulta.where(AusenciaMedico.medico_id == medico_id)
    if desde is not None:
        consulta = consulta.where(AusenciaMedico.hasta >= desde)
    if hasta is not None:
        consulta = consulta.where(AusenciaMedico.desde <= hasta)
    return sesion.scalars(consulta).all()


@router.post("", response_model=e.Ausencia, status_code=201)
def crear(datos: e.AusenciaEntrada, sesion: SesionBD):
    obtener_o_404(sesion, Medico, datos.medico_id, "Médico")
    ausencia = AusenciaMedico(**datos.model_dump())
    sesion.add(ausencia)
    sesion.flush()
    return ausencia


@router.put("/{ausencia_id}", response_model=e.Ausencia)
def modificar(ausencia_id: int, datos: e.AusenciaEntrada, sesion: SesionBD):
    ausencia = obtener_o_404(sesion, AusenciaMedico, ausencia_id, "Ausencia")
    obtener_o_404(sesion, Medico, datos.medico_id, "Médico")
    for campo, valor in datos.model_dump().items():
        setattr(ausencia, campo, valor)
    sesion.flush()
    return ausencia


@router.delete("/{ausencia_id}", status_code=204)
def borrar(ausencia_id: int, sesion: SesionBD):
    sesion.delete(obtener_o_404(sesion, AusenciaMedico, ausencia_id, "Ausencia"))
