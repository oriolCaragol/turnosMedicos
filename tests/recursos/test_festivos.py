from datetime import date

from turnos.dominio.calendario import AmbitoFestivo, dias_laborables
from turnos.recursos import CALENDARIO_PRECARGADO, MUNICIPIO_POR_DEFECTO, calendarios_festivos, municipios


def test_el_calendario_precargado_es_el_del_municipio_por_defecto():
    assert CALENDARIO_PRECARGADO == "madrid"
    assert municipios()[MUNICIPIO_POR_DEFECTO].nombre == "Madrid"


def test_hay_calendarios_de_madrid_para_2026_y_2027():
    calendarios = {c.anio: c for c in calendarios_festivos()}
    assert set(calendarios) >= {2026, 2027}
    assert calendarios[2026].completo
    assert not calendarios[2027].completo and calendarios[2027].pendiente


def test_festivos_coherentes():
    for cal in calendarios_festivos():
        fechas = [f.fecha for f in cal.festivos]
        assert len(fechas) == len(set(fechas)), cal.anio
        assert all(f.year == cal.anio for f in fechas), cal.anio
        locales = [f for f in cal.festivos if f.ambito is AmbitoFestivo.LOCAL]
        assert len(locales) == (2 if cal.completo else 0), cal.anio


def test_festivos_locales_de_madrid_2026():
    (cal,) = [c for c in calendarios_festivos() if c.anio == 2026]
    locales = {f.fecha: f.descripcion for f in cal.festivos if f.ambito is AmbitoFestivo.LOCAL}
    assert locales == {date(2026, 5, 15): "San Isidro Labrador", date(2026, 11, 9): "Nuestra Señora de la Almudena"}


def test_noviembre_2026_en_madrid():
    (cal,) = [c for c in calendarios_festivos() if c.anio == 2026]
    dias = dias_laborables(2026, 11, {f.fecha for f in cal.festivos})
    assert date(2026, 11, 2) not in dias  # traslado de Todos los Santos
    assert date(2026, 11, 9) not in dias  # la Almudena
    assert len(dias) == 19


def test_calendario_inexistente():
    assert calendarios_festivos("no-existe") == []
