"""Días laborables y festivos (especificaciones, 4.2)."""

import calendar
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date
from enum import Enum


class AmbitoFestivo(Enum):
    NACIONAL = "NACIONAL"
    AUTONOMICO = "AUTONOMICO"
    LOCAL = "LOCAL"
    OTRO = "OTRO"


@dataclass(frozen=True)
class Festivo:
    fecha: date
    descripcion: str
    ambito: AmbitoFestivo = AmbitoFestivo.OTRO


def es_laborable(fecha: date, festivos: Collection[date]) -> bool:
    """De lunes a viernes y no festivo."""
    return fecha.weekday() < 5 and fecha not in festivos


def dias_laborables(anio: int, mes: int, festivos: Collection[date]) -> list[date]:
    """Días laborables de un mes, en orden."""
    _, num_dias = calendar.monthrange(anio, mes)
    dias = (date(anio, mes, dia) for dia in range(1, num_dias + 1))
    return [d for d in dias if es_laborable(d, festivos)]
