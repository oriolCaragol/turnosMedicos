from datetime import date

from turnos.dominio.calendario import dias_laborables, es_laborable


def test_fin_de_semana_no_es_laborable():
    assert not es_laborable(date(2026, 11, 7), festivos=[])  # sábado
    assert not es_laborable(date(2026, 11, 8), festivos=[])  # domingo


def test_festivo_entre_semana_no_es_laborable():
    assert es_laborable(date(2026, 12, 8), festivos=[])
    assert not es_laborable(date(2026, 12, 8), festivos=[date(2026, 12, 8)])


def test_dias_laborables_del_mes():
    dias = dias_laborables(2026, 11, festivos=[])
    assert len(dias) == 21
    assert dias[0] == date(2026, 11, 2)
    assert dias[-1] == date(2026, 11, 30)
    assert all(d.weekday() < 5 for d in dias)


def test_dias_laborables_excluye_festivos():
    festivos = {date(2026, 12, 8), date(2026, 12, 25), date(2026, 12, 26)}  # el 26 es sábado
    dias = dias_laborables(2026, 12, festivos)
    assert len(dias) == 23 - 2
    assert date(2026, 12, 8) not in dias
    assert date(2026, 12, 25) not in dias
