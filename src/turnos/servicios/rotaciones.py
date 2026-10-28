"""Turnos rotativos (especificaciones, 5.8)."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from turnos.datos.tablas import Medico, RotacionHueco, RotacionMedico, RotacionTabla
from turnos.dominio.modelos import Turno
from turnos.motor.entrada import Rotacion


class RotacionNoValida(ValueError):
    pass


@dataclass
class DatosRotacion:
    nombre: str
    desde: date
    activa: bool
    medicos: list[int]  # en orden: el primero empieza
    huecos: list[tuple[int, Turno]]  # (día de la semana, turno)


def listar(sesion: Session) -> list[RotacionTabla]:
    return list(sesion.scalars(select(RotacionTabla).order_by(RotacionTabla.id)))


def guardar(sesion: Session, datos: DatosRotacion, rotacion: RotacionTabla | None = None) -> RotacionTabla:
    if len(set(datos.medicos)) != len(datos.medicos):
        raise RotacionNoValida("Un médico no puede estar dos veces en el mismo turno rotativo")
    for medico_id in datos.medicos:
        if sesion.get(Medico, medico_id) is None:
            raise RotacionNoValida("Médico no encontrado")
    rotacion = rotacion or RotacionTabla()
    rotacion.nombre, rotacion.desde, rotacion.activa = datos.nombre, datos.desde, datos.activa
    rotacion.miembros = [RotacionMedico(medico_id=m, orden=i) for i, m in enumerate(datos.medicos)]
    rotacion.huecos = [RotacionHueco(dia_semana=d, turno=t) for d, t in sorted(set(datos.huecos), key=lambda h: (h[0], h[1].value))]
    sesion.add(rotacion)
    sesion.flush()
    return rotacion


def para_el_motor(sesion: Session) -> tuple[Rotacion, ...]:
    """Rotaciones activas y completas (al menos dos médicos y un turno)."""
    return tuple(
        Rotacion(
            medicos=tuple(m.medico_id for m in r.miembros),
            huecos=frozenset((h.dia_semana, h.turno) for h in r.huecos),
            desde=r.desde,
            nombre=r.nombre,
        )
        for r in listar(sesion)
        if r.activa and len(r.miembros) >= 2 and r.huecos
    )
