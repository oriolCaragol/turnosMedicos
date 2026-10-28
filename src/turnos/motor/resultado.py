"""Salida del motor: asignaciones y avisos legibles (diseño, 6.6)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from turnos.dominio.modelos import Asignacion, Mitad, OrigenAsignacion, RangoCarga, Rol, Turno, formatear_medios

_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_TURNOS = {Turno.MANANA: "por la mañana", Turno.TARDE: "por la tarde"}
_MITADES = {
    Mitad.M1: "en la primera mitad de la mañana",
    Mitad.M2: "en la segunda mitad de la mañana",
    Mitad.T1: "en la primera mitad de la tarde",
    Mitad.T2: "en la segunda mitad de la tarde",
}


def fmt_fecha(fecha: date) -> str:
    return f"{_DIAS[fecha.weekday()]} {fecha.day}/{fecha.month}"


def fmt_turno(turno: Turno) -> str:
    return _TURNOS[turno]


def fmt_mitad(mitad: Mitad) -> str:
    return _MITADES[mitad]


class TipoAviso(Enum):
    CAUSA = "CAUSA"  # comprobación previa: por qué no puede haber solución válida
    INCUMPLIMIENTO = "INCUMPLIMIENTO"  # regla que el calendario entregado no cumple


@dataclass(frozen=True)
class Aviso:
    tipo: TipoAviso
    mensaje: str
    fecha: date | None = None
    medico_id: int | None = None


@dataclass(frozen=True)
class Resultado:
    """Calendario generado.

    - `asignaciones`: todas, con su origen (fijadas y generadas).
    - `valido`: cumple todas las reglas estrictas.
    - `optimo`: todas las pasadas demostraron su óptimo dentro del límite.
    - `carga`: medios turnos asignados por médico.
    - `roles`: (fecha, rol) → médico de urgencias y de domicilios de cada tarde.
    """

    asignaciones: Mapping[Asignacion, OrigenAsignacion]
    valido: bool
    optimo: bool
    avisos: tuple[Aviso, ...]
    carga: Mapping[int, int]
    roles: Mapping[tuple[date, Rol], int] = field(default_factory=dict)


def agrupar_mitades[T](valores: Mapping[Mitad, T]) -> list[tuple[str, T]]:
    """Agrupa valores por mitad en textos legibles.

    Si las dos mitades de un turno tienen el mismo valor se habla del turno
    ("por la mañana"); si no, de cada mitad. Las mitades sin valor se omiten.
    """
    grupos = []
    for turno in Turno:
        a, b = (valores.get(h) for h in turno.mitades)
        if a == b:
            if a is not None:
                grupos.append((fmt_turno(turno), a))
        else:
            grupos += [(fmt_mitad(h), v) for h, v in zip(turno.mitades, (a, b)) if v is not None]
    return grupos


def medicos_txt(n: int) -> str:
    return f"{n} médico" if n == 1 else f"{n} médicos"


# --- Avisos de incumplimiento (compartidos por el motor y la validación) -------


def avisos_cobertura(dia: date, faltas: Mapping[Mitad, int], sobras: Mapping[Mitad, int]) -> list[Aviso]:
    avisos = []
    for lugar, n in agrupar_mitades({h: v for h, v in faltas.items() if v}):
        verbo = "falta" if n == 1 else "faltan"
        avisos.append(Aviso(
            TipoAviso.INCUMPLIMIENTO, f"El {fmt_fecha(dia)} {lugar} {verbo} {medicos_txt(n)}.", fecha=dia
        ))
    for lugar, n in agrupar_mitades({h: v for h, v in sobras.items() if v}):
        verbo = "sobra" if n == 1 else "sobran"
        avisos.append(Aviso(
            TipoAviso.INCUMPLIMIENTO, f"El {fmt_fecha(dia)} {lugar} {verbo} {medicos_txt(n)}.", fecha=dia
        ))
    return avisos


def avisos_carga(
    medico_id: int, nombre: str, unidad: str, carga: int, rango: RangoCarga
) -> list[Aviso]:
    if carga < rango.minimo:
        limite = f"por debajo de su mínimo de {formatear_medios(rango.minimo)}"
    elif carga > rango.maximo:
        limite = f"por encima de su máximo de {formatear_medios(rango.maximo)}"
    else:
        return []
    return [Aviso(
        TipoAviso.INCUMPLIMIENTO,
        f"{nombre} tiene {formatear_medios(carga)} {unidad}, {limite}.",
        medico_id=medico_id,
    )]


def aviso_rol_sin_cubrir(dia: date, rol: Rol) -> Aviso:
    return Aviso(TipoAviso.INCUMPLIMIENTO, f"El {fmt_fecha(dia)} por la tarde nadie hace {rol.nombre}.", fecha=dia)


def aviso_sin_turno(dia: date, medico_id: int, nombre: str) -> Aviso:
    return Aviso(
        TipoAviso.INCUMPLIMIENTO, f"{nombre} no tiene turno el {fmt_fecha(dia)}.", fecha=dia, medico_id=medico_id
    )
