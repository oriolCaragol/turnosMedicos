"""Lectura y guardado de las reglas de un médico, con versiones por fecha.

Cada guardado escribe una "foto" completa de las reglas versionadas
(elegibilidad, jornadas especiales y carga) con su fecha `vigente_desde`.
Para una fecha dada, vale la última foto con `vigente_desde` anterior o igual
(diseño, 4.2). Las preferencias no se versionan.
"""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from turnos.datos.tablas import Carga, JornadaSemanal, ReglaElegibilidad, ReglaPreferencia
from turnos.dominio.modelos import Elegibilidad, Preferencia, RangoCarga, TipoJornada, Turno

DIAS_SEMANA = range(5)


@dataclass
class Reglas:
    """Reglas de un médico. Las cargas van en medios turnos.

    - `elegibilidad`: las 10 celdas de la cuadrícula (por defecto Disponible).
    - `jornadas`: solo los días con jornada especial.
    - `carga`: None si nunca se ha definido.
    - `carga_por_turno`: solo los turnos con límite; máximo None = sin límite.
    """

    elegibilidad: dict[tuple[int, Turno], Elegibilidad] = field(
        default_factory=lambda: {(d, t): Elegibilidad.DISPONIBLE for d in DIAS_SEMANA for t in Turno}
    )
    jornadas: dict[int, TipoJornada] = field(default_factory=dict)
    carga: RangoCarga | None = None
    carga_por_turno: dict[Turno, tuple[int, int | None]] = field(default_factory=dict)
    preferencias: dict[tuple[int, Turno], Preferencia] = field(default_factory=dict)
    vigente_desde: date | None = None  # versión aplicada (None = sin reglas guardadas)


def _vigentes(sesion: Session, tabla, medico_id: int, fecha: date, clave) -> list:
    """Filas de la última versión anterior o igual a `fecha`, una por clave."""
    filas = sesion.scalars(
        select(tabla)
        .where(tabla.medico_id == medico_id, tabla.vigente_desde <= fecha)
        .order_by(tabla.vigente_desde)
    )
    ultimas = {}
    for fila in filas:
        ultimas[clave(fila)] = fila
    return list(ultimas.values())


def leer_reglas(sesion: Session, medico_id: int, fecha: date) -> Reglas:
    reglas = Reglas()
    versiones = []
    for fila in _vigentes(sesion, ReglaElegibilidad, medico_id, fecha,
                          lambda f: (f.dia_semana, f.turno)):
        reglas.elegibilidad[fila.dia_semana, fila.turno] = fila.valor
        versiones.append(fila.vigente_desde)
    for fila in _vigentes(sesion, JornadaSemanal, medico_id, fecha, lambda f: f.dia_semana):
        if fila.tipo is not None:
            reglas.jornadas[fila.dia_semana] = fila.tipo
        versiones.append(fila.vigente_desde)
    for fila in _vigentes(sesion, Carga, medico_id, fecha, lambda f: f.turno):
        if fila.turno is None:
            reglas.carga = RangoCarga(fila.minimo, fila.maximo)
        elif fila.minimo or fila.maximo is not None:
            reglas.carga_por_turno[fila.turno] = (fila.minimo, fila.maximo)
        versiones.append(fila.vigente_desde)
    for fila in sesion.scalars(select(ReglaPreferencia).where(ReglaPreferencia.medico_id == medico_id)):
        reglas.preferencias[fila.dia_semana, fila.turno] = fila.valor
    reglas.vigente_desde = max(versiones, default=None)
    return reglas


def guardar_reglas(sesion: Session, medico_id: int, vigente_desde: date, reglas: Reglas) -> None:
    """Guarda las reglas como una versión válida desde `vigente_desde`.

    Si ya existía una versión con esa misma fecha, se sustituye. Si
    `reglas.carga` es None (p. ej. un médico recién dado de alta al que aún no
    se le ha puesto), se guarda todo lo demás y la carga total no se toca: sigue
    valiendo la de una versión anterior, o queda sin definir.
    """
    for tabla in (ReglaElegibilidad, JornadaSemanal):
        sesion.execute(delete(tabla).where(
            tabla.medico_id == medico_id, tabla.vigente_desde == vigente_desde
        ))
    borrar_cargas = delete(Carga).where(Carga.medico_id == medico_id, Carga.vigente_desde == vigente_desde)
    if reglas.carga is None:
        borrar_cargas = borrar_cargas.where(Carga.turno.is_not(None))
    sesion.execute(borrar_cargas)
    for d in DIAS_SEMANA:
        for t in Turno:
            sesion.add(ReglaElegibilidad(
                medico_id=medico_id, vigente_desde=vigente_desde, dia_semana=d, turno=t,
                valor=reglas.elegibilidad.get((d, t), Elegibilidad.DISPONIBLE),
            ))
        sesion.add(JornadaSemanal(
            medico_id=medico_id, vigente_desde=vigente_desde, dia_semana=d,
            tipo=reglas.jornadas.get(d),
        ))
    if reglas.carga is not None:
        sesion.add(Carga(
            medico_id=medico_id, vigente_desde=vigente_desde, turno=None,
            minimo=reglas.carga.minimo, maximo=reglas.carga.maximo,
        ))
    for t in Turno:
        minimo, maximo = reglas.carga_por_turno.get(t, (0, None))
        if maximo is not None and maximo < minimo:
            raise ValueError("El máximo por turno no puede ser menor que el mínimo")
        sesion.add(Carga(
            medico_id=medico_id, vigente_desde=vigente_desde, turno=t, minimo=minimo, maximo=maximo,
        ))
    sesion.execute(delete(ReglaPreferencia).where(ReglaPreferencia.medico_id == medico_id))
    for (d, t), valor in reglas.preferencias.items():
        sesion.add(ReglaPreferencia(medico_id=medico_id, dia_semana=d, turno=t, valor=valor))
    sesion.flush()
