from datetime import date

import pytest

from turnos.dominio.modelos import (
    Ausencia,
    Mitad,
    RangoCarga,
    TipoJornada,
    Turno,
    formatear_medios,
    turnos_a_medios,
)


def test_mitades_de_cada_turno():
    assert Turno.MANANA.mitades == (Mitad.M1, Mitad.M2)
    assert Turno.TARDE.mitades == (Mitad.T1, Mitad.T2)
    assert all(m.turno is t for t in Turno for m in t.mitades)


def test_jornadas_especiales_usan_la_mitad_contigua():
    assert TipoJornada.MANANA_MAS_MEDIA.mitades == {Mitad.M1, Mitad.M2, Mitad.T1}
    assert TipoJornada.TARDE_MAS_MEDIA.mitades == {Mitad.M2, Mitad.T1, Mitad.T2}
    assert TipoJornada.DOBLE.mitades == set(Mitad)
    assert TipoJornada.MANANA_MAS_MEDIA.medios_turnos == 3
    assert TipoJornada.DOBLE.medios_turnos == 4


@pytest.mark.parametrize("minimo, maximo", [(-1, 4), (5, 4)])
def test_rango_carga_no_valido(minimo, maximo):
    with pytest.raises(ValueError):
        RangoCarga(minimo, maximo)


def test_ausencia_de_dia_completo_cubre_ambos_turnos():
    ausencia = Ausencia(date(2026, 11, 10), date(2026, 11, 13))
    assert ausencia.cubre(date(2026, 11, 10), Turno.MANANA)
    assert ausencia.cubre(date(2026, 11, 13), Turno.TARDE)
    assert not ausencia.cubre(date(2026, 11, 14), Turno.MANANA)


def test_ausencia_de_un_turno():
    ausencia = Ausencia(date(2026, 11, 10), date(2026, 11, 13), Turno.TARDE)
    assert ausencia.cubre(date(2026, 11, 11), Turno.TARDE)
    assert not ausencia.cubre(date(2026, 11, 11), Turno.MANANA)


def test_ausencia_con_fechas_invertidas():
    with pytest.raises(ValueError):
        Ausencia(date(2026, 11, 13), date(2026, 11, 10))


def test_conversion_de_turnos():
    assert turnos_a_medios(18.5) == 37
    assert turnos_a_medios(16) == 32
    with pytest.raises(ValueError):
        turnos_a_medios(16.25)
    assert formatear_medios(37) == "18,5"
    assert formatear_medios(32) == "16"
    assert formatear_medios(1) == "0,5"
