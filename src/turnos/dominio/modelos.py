"""Tipos básicos del dominio (especificaciones, secciones 3, 4 y 5).

Las cargas se expresan siempre en **medios turnos** (enteros): 18,5 turnos se
representan como 37.
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum


class Turno(Enum):
    MANANA = "MANANA"
    TARDE = "TARDE"

    @property
    def mitades(self) -> tuple["Mitad", "Mitad"]:
        if self is Turno.MANANA:
            return (Mitad.M1, Mitad.M2)
        return (Mitad.T1, Mitad.T2)


class Mitad(Enum):
    """Cada turno se divide en dos mitades (especificaciones, 5.3)."""

    M1 = "M1"
    M2 = "M2"
    T1 = "T1"
    T2 = "T2"

    @property
    def turno(self) -> Turno:
        return Turno.MANANA if self in (Mitad.M1, Mitad.M2) else Turno.TARDE


class Elegibilidad(Enum):
    """Valor de una celda de la cuadrícula de elegibilidad (5.1).

    HABITUAL: disponible y, si ese día trabaja, preferentemente en ese turno.
    No obliga a trabajar ese día (a diferencia de FIJO).
    """

    FIJO = "FIJO"
    HABITUAL = "HABITUAL"
    DISPONIBLE = "DISPONIBLE"
    NO_DISPONIBLE = "NO_DISPONIBLE"

    @property
    def asignable(self) -> bool:
        """El generador puede decidir asignar este turno."""
        return self in (Elegibilidad.DISPONIBLE, Elegibilidad.HABITUAL)


class TipoJornada(Enum):
    """Jornadas de más de un turno; solo las define el planificador (5.3)."""

    MANANA_MAS_MEDIA = "MANANA_MAS_MEDIA"  # mañana + primera mitad de la tarde
    TARDE_MAS_MEDIA = "TARDE_MAS_MEDIA"  # segunda mitad de la mañana + tarde
    DOBLE = "DOBLE"  # mañana y tarde completas

    @property
    def mitades(self) -> frozenset[Mitad]:
        if self is TipoJornada.MANANA_MAS_MEDIA:
            return frozenset({Mitad.M1, Mitad.M2, Mitad.T1})
        if self is TipoJornada.TARDE_MAS_MEDIA:
            return frozenset({Mitad.M2, Mitad.T1, Mitad.T2})
        return frozenset(Mitad)

    @property
    def medios_turnos(self) -> int:
        return len(self.mitades)


class Rol(Enum):
    """Papel de un médico en la tarde de un día: urgencias en el centro o domicilios.

    Cada tarde con servicio, un médico distinto para cada papel, y solo entre los
    que hacen la tarde completa.
    """

    URGENCIAS = "URGENCIAS"
    DOMICILIOS = "DOMICILIOS"

    @property
    def nombre(self) -> str:
        return "urgencias" if self is Rol.URGENCIAS else "domicilios"


class Preferencia(Enum):
    """Preferencia de un médico por un hueco semanal (5.4)."""

    PREFIERE = "PREFIERE"
    EVITA = "EVITA"


class OrigenAsignacion(Enum):
    GENERADOR = "GENERADOR"  # decidida por el motor
    FIJO = "FIJO"  # hueco Fijo o jornada especial de las reglas del médico
    MANUAL = "MANUAL"  # puesta o bloqueada por el planificador


@dataclass(frozen=True)
class Asignacion:
    """Un médico en una mitad de turno de una fecha. Un turno completo son dos."""

    medico_id: int
    fecha: date
    mitad: Mitad


@dataclass(frozen=True)
class RangoCarga:
    """Carga mensual mínima y máxima, en medios turnos (5.2)."""

    minimo: int
    maximo: int

    def __post_init__(self) -> None:
        if self.minimo < 0 or self.maximo < self.minimo:
            raise ValueError(f"Rango de carga no válido: {self.minimo}–{self.maximo}")


@dataclass(frozen=True)
class Ausencia:
    """Ausencia de un médico entre dos fechas, ambas incluidas (4.5).

    Si `turno` es None, la ausencia es de día completo.
    """

    desde: date
    hasta: date
    turno: Turno | None = None

    def __post_init__(self) -> None:
        if self.hasta < self.desde:
            raise ValueError(f"Ausencia no válida: {self.desde} – {self.hasta}")

    def cubre(self, fecha: date, turno: Turno) -> bool:
        return self.desde <= fecha <= self.hasta and self.turno in (None, turno)


def turnos_a_medios(turnos: float) -> int:
    """Convierte un número de turnos (múltiplo de 0,5) a medios turnos."""
    medios = turnos * 2
    if medios != int(medios):
        raise ValueError(f"{turnos} no es múltiplo de medio turno")
    return int(medios)


def formatear_medios(medios: int) -> str:
    """Muestra una carga en turnos con coma decimal: 37 → '18,5', 32 → '16'."""
    enteros, resto = divmod(medios, 2)
    return f"{enteros},5" if resto else str(enteros)
