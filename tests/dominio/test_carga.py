from datetime import date, timedelta
from fractions import Fraction

from turnos.dominio.carga import ajustar_rango, factor_disponibilidad, medios_dias_ausente
from turnos.dominio.modelos import Ausencia, RangoCarga, Turno


def laborables(n: int) -> list[date]:
    """n días laborables consecutivos (sin fines de semana), desde el lunes 2026-11-02."""
    dias, dia = [], date(2026, 11, 2)
    while len(dias) < n:
        if dia.weekday() < 5:
            dias.append(dia)
        dia += timedelta(days=1)
    return dias


def test_sin_ausencias_el_rango_no_cambia():
    rango = RangoCarga(32, 36)
    assert ajustar_rango(rango, laborables(20), []) == rango


def test_ejemplo_de_las_especificaciones():
    # 16–18 turnos, 20 días laborables, 5 de vacaciones → 12–13,5 turnos.
    dias = laborables(20)
    vacaciones = Ausencia(dias[0], dias[4])
    assert ajustar_rango(RangoCarga(32, 36), dias, [vacaciones]) == RangoCarga(24, 27)


def test_ausencia_de_un_turno_cuenta_medio_dia():
    dias = laborables(20)
    solo_tardes = Ausencia(dias[0], dias[1], Turno.TARDE)
    assert medios_dias_ausente(dias, [solo_tardes]) == 2
    assert factor_disponibilidad(dias, [solo_tardes]) == Fraction(19, 20)


def test_mananas_y_tardes_el_mismo_dia_cuentan_como_dia_completo():
    dias = laborables(5)
    ausencias = [
        Ausencia(dias[0], dias[0], Turno.MANANA),
        Ausencia(dias[0], dias[0], Turno.TARDE),
        Ausencia(dias[0], dias[0]),
    ]
    assert medios_dias_ausente(dias, ausencias) == 2


def test_las_ausencias_fuera_del_mes_o_en_festivo_no_cuentan():
    dias = laborables(20)
    antes = Ausencia(date(2026, 10, 1), date(2026, 10, 31))
    fin_de_semana = Ausencia(date(2026, 11, 7), date(2026, 11, 8))
    assert medios_dias_ausente(dias, [antes, fin_de_semana]) == 0


def test_redondeo_al_medio_turno_mas_cercano():
    dias = laborables(20)
    # factor 19/20: 33 × 0,95 = 31,35 → 31; 35 × 0,95 = 33,25 → 33.
    un_dia = Ausencia(dias[0], dias[0])
    assert ajustar_rango(RangoCarga(33, 35), dias, [un_dia]) == RangoCarga(31, 33)


def test_redondeo_de_empates_hacia_arriba():
    dias = laborables(4)
    # factor 3/4: 2 × 0,75 = 1,5 → 2; 6 × 0,75 = 4,5 → 5.
    un_dia = Ausencia(dias[0], dias[0])
    assert ajustar_rango(RangoCarga(2, 6), dias, [un_dia]) == RangoCarga(2, 5)


def test_ausente_todo_el_mes():
    dias = laborables(20)
    assert ajustar_rango(RangoCarga(32, 36), dias, [Ausencia(dias[0], dias[-1])]) == RangoCarga(0, 0)


def test_mes_sin_dias_laborables():
    assert ajustar_rango(RangoCarga(32, 36), [], []) == RangoCarga(0, 0)
