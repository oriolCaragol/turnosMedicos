"""Médicos y sus reglas (especificaciones, 4.3 y 5)."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import exists, select

from turnos.api import esquemas as e
from turnos.api.dependencias import SesionBD, obtener_o_404
from turnos.datos.tablas import AsignacionPeriodo, Medico
from turnos.dominio.modelos import RangoCarga
from turnos.servicios.reglas import Reglas, guardar_reglas, leer_reglas

router = APIRouter(prefix="/api/medicos", tags=["médicos"])


@router.get("", response_model=list[e.Medico])
def listar(sesion: SesionBD):
    return sesion.scalars(select(Medico).order_by(Medico.activo.desc(), Medico.nombre)).all()


@router.post("", response_model=e.Medico, status_code=201)
def crear(datos: e.MedicoEntrada, sesion: SesionBD):
    medico = Medico(**datos.model_dump())  # incluye el color, opcional
    sesion.add(medico)
    sesion.flush()
    return medico


@router.get("/{medico_id}", response_model=e.Medico)
def obtener(medico_id: int, sesion: SesionBD):
    return obtener_o_404(sesion, Medico, medico_id, "Médico")


@router.put("/{medico_id}", response_model=e.Medico)
def modificar(medico_id: int, datos: e.MedicoEntrada, sesion: SesionBD):
    medico = obtener_o_404(sesion, Medico, medico_id, "Médico")
    for campo, valor in datos.model_dump().items():
        setattr(medico, campo, valor)
    sesion.flush()
    return medico


@router.delete("/{medico_id}", status_code=204)
def borrar(medico_id: int, sesion: SesionBD):
    medico = obtener_o_404(sesion, Medico, medico_id, "Médico")
    if sesion.scalar(select(exists().where(AsignacionPeriodo.medico_id == medico_id))):
        raise HTTPException(
            409, "El médico tiene turnos asignados; desactívalo en lugar de borrarlo"
        )
    sesion.delete(medico)


@router.get("/{medico_id}/reglas", response_model=e.ReglasLeidas)
def obtener_reglas(
    medico_id: int,
    sesion: SesionBD,
    fecha: date = Query(default_factory=date.today, description="Fecha de vigencia"),
):
    obtener_o_404(sesion, Medico, medico_id, "Médico")
    reglas = leer_reglas(sesion, medico_id, fecha)
    return e.ReglasLeidas(
        vigente_desde=reglas.vigente_desde,
        elegibilidad=[
            e.CeldaElegibilidad(dia_semana=d, turno=t, valor=v)
            for (d, t), v in sorted(reglas.elegibilidad.items(), key=lambda i: (i[0][0], i[0][1].value))
        ],
        jornadas=[e.JornadaDia(dia_semana=d, tipo=t) for d, t in sorted(reglas.jornadas.items())],
        carga=(
            e.RangoCarga(minimo=reglas.carga.minimo, maximo=reglas.carga.maximo)
            if reglas.carga else None
        ),
        carga_por_turno=[
            e.RangoCargaTurno(turno=t, minimo=mi, maximo=ma)
            for t, (mi, ma) in reglas.carga_por_turno.items()
        ],
        preferencias=[
            e.PreferenciaHueco(dia_semana=d, turno=t, valor=v)
            for (d, t), v in sorted(reglas.preferencias.items(), key=lambda i: (i[0][0], i[0][1].value))
        ],
    )


@router.put("/{medico_id}/reglas", response_model=e.ReglasLeidas)
def guardar(medico_id: int, datos: e.ReglasGuardar, sesion: SesionBD):
    obtener_o_404(sesion, Medico, medico_id, "Médico")
    reglas = Reglas(
        jornadas={j.dia_semana: j.tipo for j in datos.jornadas},
        carga=RangoCarga(datos.carga.minimo, datos.carga.maximo) if datos.carga else None,
        carga_por_turno={c.turno: (c.minimo, c.maximo) for c in datos.carga_por_turno},
        preferencias={(p.dia_semana, p.turno): p.valor for p in datos.preferencias},
    )
    for celda in datos.elegibilidad:
        reglas.elegibilidad[celda.dia_semana, celda.turno] = celda.valor
    guardar_reglas(sesion, medico_id, datos.vigente_desde, reglas)
    return obtener_reglas(medico_id, sesion, datos.vigente_desde)
