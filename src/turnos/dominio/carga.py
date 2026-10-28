"""Ajuste proporcional de la carga mensual por ausencias (especificaciones, 5.2).

rango ajustado = rango × (días laborables disponibles / días laborables del mes)

- Una ausencia de un solo turno cuenta como medio día.
- El resultado se redondea al medio turno más cercano; los empates, hacia
  arriba.
"""

from collections.abc import Iterable, Sequence
from datetime import date
from fractions import Fraction
from math import floor

from turnos.dominio.modelos import Ausencia, RangoCarga, Turno


def medios_dias_ausente(dias: Iterable[date], ausencias: Sequence[Ausencia]) -> int:
    """Medios días de ausencia dentro de `dias` (2 = día completo, 1 = un turno).

    Si un mismo día hay ausencias de mañana y de tarde, cuenta como día completo.
    """
    total = 0
    for dia in dias:
        total += sum(
            1 for turno in Turno if any(a.cubre(dia, turno) for a in ausencias)
        )
    return total


def factor_disponibilidad(
    dias_laborables: Sequence[date], ausencias: Sequence[Ausencia]
) -> Fraction:
    """Fracción del mes en la que el médico está disponible (entre 0 y 1)."""
    if not dias_laborables:
        return Fraction(0)
    medios_dias = 2 * len(dias_laborables)
    return Fraction(medios_dias - medios_dias_ausente(dias_laborables, ausencias), medios_dias)


def _redondear(valor: Fraction) -> int:
    return floor(valor + Fraction(1, 2))


def ajustar_rango(
    rango: RangoCarga, dias_laborables: Sequence[date], ausencias: Sequence[Ausencia]
) -> RangoCarga:
    """Rango de carga del mes reducido en proporción a las ausencias."""
    factor = factor_disponibilidad(dias_laborables, ausencias)
    return RangoCarga(_redondear(rango.minimo * factor), _redondear(rango.maximo * factor))
