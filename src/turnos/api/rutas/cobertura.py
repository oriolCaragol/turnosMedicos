"""Médicos necesarios por turno (especificaciones, 4.4)."""

from datetime import date

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, select

from turnos.api import esquemas as e
from turnos.api.dependencias import SesionBD
from turnos.datos.tablas import CoberturaFecha, CoberturaSemanal
from turnos.dominio.modelos import Mitad

router = APIRouter(prefix="/api/cobertura", tags=["cobertura"])


@router.get("/semanal", response_model=list[e.CoberturaSemanal])
def semanal(sesion: SesionBD):
    """Las 20 combinaciones día × mitad; las no definidas valen 0–0."""
    guardadas = {(c.dia_semana, c.mitad): c for c in sesion.scalars(select(CoberturaSemanal))}
    return [
        guardadas.get((d, h)) or e.CoberturaSemanal(dia_semana=d, mitad=h, minimo=0, maximo=0)
        for d in range(5) for h in Mitad
    ]


@router.put("/semanal", response_model=list[e.CoberturaSemanal])
def guardar_semanal(datos: list[e.CoberturaSemanal], sesion: SesionBD):
    claves = {(c.dia_semana, c.mitad) for c in datos}
    if len(claves) != len(datos):
        raise HTTPException(422, "Hay combinaciones de día y mitad repetidas")
    sesion.execute(delete(CoberturaSemanal))
    sesion.add_all(CoberturaSemanal(**c.model_dump()) for c in datos)
    sesion.flush()
    return semanal(sesion)


@router.get("/fechas", response_model=list[e.CoberturaFecha])
def fechas(sesion: SesionBD, desde: date | None = None, hasta: date | None = None):
    consulta = select(CoberturaFecha).order_by(CoberturaFecha.fecha)
    if desde is not None:
        consulta = consulta.where(CoberturaFecha.fecha >= desde)
    if hasta is not None:
        consulta = consulta.where(CoberturaFecha.fecha <= hasta)
    return sesion.scalars(consulta).all()


@router.put("/fechas/{fecha}", response_model=list[e.CoberturaFecha])
def guardar_fecha(fecha: date, datos: list[e.CoberturaMitad], sesion: SesionBD):
    """Excepción para una fecha concreta: sustituye la cobertura semanal ese día."""
    if {c.mitad for c in datos} != set(Mitad) or len(datos) != len(Mitad):
        raise HTTPException(422, "Hay que indicar las cuatro mitades del día")
    sesion.execute(delete(CoberturaFecha).where(CoberturaFecha.fecha == fecha))
    sesion.add_all(CoberturaFecha(fecha=fecha, **c.model_dump()) for c in datos)
    sesion.flush()
    return fechas(sesion, fecha, fecha)


@router.delete("/fechas/{fecha}", status_code=204)
def borrar_fecha(fecha: date, sesion: SesionBD):
    sesion.execute(delete(CoberturaFecha).where(CoberturaFecha.fecha == fecha))
