import sqlite3
from datetime import date, time

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from turnos.dominio.calendario import AmbitoFestivo
from turnos.dominio.calendario import Festivo as FestivoDominio
from turnos.dominio.modelos import Turno
from turnos.datos import bd
from turnos.datos.bd import crear_motor, inicializar, migrar
from turnos.datos.tablas import Ajuste, AusenciaMedico, CargaFestivos, Festivo, HorarioTurno, Medico
from turnos.servicios.ajustes import leer_ajustes
from turnos.recursos import CalendarioFestivos


@pytest.fixture
def ruta(tmp_path):
    return tmp_path / "datos" / "turnos.sqlite"


def num_festivos(motor, anio: int | None = None) -> int:
    consulta = select(func.count()).select_from(Festivo)
    if anio is not None:
        consulta = consulta.where(Festivo.fecha.between(date(anio, 1, 1), date(anio, 12, 31)))
    with Session(motor) as s:
        return s.scalar(consulta)


def test_inicializar_crea_la_base_con_todas_las_tablas(ruta):
    motor = inicializar(ruta)
    assert ruta.exists()
    tablas = set(inspect(motor).get_table_names())
    assert {"medico", "festivo", "asignacion", "veto", "alembic_version"} <= tablas


def test_festivos_y_horarios_cargados(ruta):
    motor = inicializar(ruta)
    assert num_festivos(motor, 2026) == 14
    assert num_festivos(motor, 2027) == 12
    with Session(motor) as s:
        cargas = {c.anio: c.completo for c in s.scalars(select(CargaFestivos))}
        assert cargas[2026] is True and cargas[2027] is False
        manana = s.get(HorarioTurno, Turno.MANANA)
        assert (manana.inicio, manana.corte, manana.fin) == (time(8), time(11, 30), time(15))


def test_reinicializar_no_duplica_ni_deshace_cambios(ruta):
    motor = inicializar(ruta)
    with Session(motor) as s, s.begin():
        s.delete(s.scalar(select(Festivo).where(Festivo.fecha == date(2026, 5, 15))))
    motor.dispose()
    motor = inicializar(ruta)
    assert num_festivos(motor, 2026) == 13


def test_completar_un_anio_incompleto_solo_anade_los_locales(ruta, monkeypatch):
    motor = inicializar(ruta)
    # El planificador quita un festivo autonómico de 2027.
    with Session(motor) as s, s.begin():
        s.delete(s.scalar(select(Festivo).where(Festivo.fecha == date(2027, 3, 19))))
    motor.dispose()

    original = bd.calendarios_festivos

    def con_locales(calendario="madrid"):
        calendarios = []
        for cal in original(calendario):
            if cal.anio == 2027:
                locales = (
                    FestivoDominio(date(2027, 5, 15), "San Isidro Labrador", AmbitoFestivo.LOCAL),
                    FestivoDominio(date(2027, 11, 9), "Nuestra Señora de la Almudena", AmbitoFestivo.LOCAL),
                )
                cal = CalendarioFestivos(cal.calendario, 2027, True, cal.festivos + locales)
            calendarios.append(cal)
        return calendarios

    monkeypatch.setattr(bd, "calendarios_festivos", con_locales)
    motor = inicializar(ruta)
    with Session(motor) as s:
        fechas = set(s.scalars(select(Festivo.fecha)))
        assert {date(2027, 5, 15), date(2027, 11, 9)} <= fechas
        assert date(2027, 3, 19) not in fechas
        assert s.get(CargaFestivos, 2027).completo


def test_claves_ajenas_activas(ruta):
    motor = inicializar(ruta)
    with Session(motor) as s, s.begin():
        medico = Medico(nombre="Dra. García", codigo="GAR")
        medico.ausencias.append(AusenciaMedico(desde=date(2026, 11, 2), hasta=date(2026, 11, 6)))
        s.add(medico)
    with motor.begin() as conexion:
        conexion.exec_driver_sql("DELETE FROM medico")
    with Session(motor) as s:
        assert s.scalar(select(func.count()).select_from(AusenciaMedico)) == 0


def test_sin_migraciones_pendientes_no_hace_copia(ruta):
    motor = inicializar(ruta)
    assert migrar(motor, ruta) is None


def test_migrar_de_0001_a_la_ultima_conserva_los_datos(ruta):
    """Una base creada con la versión 0001 se actualiza (color de los médicos) sin perder datos."""
    from alembic import command

    from turnos.datos.bd import _config_alembic

    ruta.parent.mkdir(parents=True)
    motor = crear_motor(ruta)
    config = _config_alembic()
    with motor.begin() as conexion:
        config.attributes["conexion"] = conexion
        command.upgrade(config, "0001")
        conexion.exec_driver_sql("INSERT INTO medico (nombre, codigo, activo) VALUES ('Ana', '1', 1)")
    motor.dispose()
    motor = inicializar(ruta)  # aplica las migraciones pendientes
    with Session(motor) as s:
        ana = s.scalar(select(Medico))
        assert (ana.nombre, ana.color) == ("Ana", None)
    assert list(ruta.parent.glob("*.sqlite.bak")), "debe hacer copia antes de migrar"


def test_copia_de_seguridad_antes_de_migrar_una_base_con_datos(ruta):
    ruta.parent.mkdir(parents=True)
    with sqlite3.connect(ruta) as conexion:
        conexion.execute("CREATE TABLE previa (valor TEXT)")
        conexion.execute("INSERT INTO previa VALUES ('dato')")
    copia = migrar(crear_motor(ruta), ruta)
    assert copia is not None and copia.exists()
    with sqlite3.connect(copia) as conexion:
        assert conexion.execute("SELECT valor FROM previa").fetchall() == [("dato",)]


def test_espera_si_la_base_esta_ocupada(ruta):
    motor = inicializar(ruta)
    with motor.connect() as conexion:
        assert conexion.exec_driver_sql("PRAGMA busy_timeout").scalar() == 5000


def test_datos_de_una_version_mas_reciente_no_se_tocan(ruta):
    inicializar(ruta).dispose()
    with sqlite3.connect(ruta) as conexion:
        conexion.execute("UPDATE alembic_version SET version_num = '9999_futura'")
    antes = ruta.read_bytes()
    with pytest.raises(bd.DatosMasNuevos, match="versión más reciente"):
        inicializar(ruta)
    assert ruta.read_bytes() == antes
    assert not list(ruta.parent.glob("*.copia*"))


def test_otro_municipio_no_recibe_los_festivos_precargados_de_madrid(ruta):
    ruta.parent.mkdir(parents=True)
    motor = crear_motor(ruta)
    migrar(motor, ruta)
    with motor.begin() as conexion:
        conexion.exec_driver_sql("INSERT INTO ajuste (clave, valor) VALUES ('municipio', '\"28005\"')")  # Alcalá
    inicializar(ruta)
    assert num_festivos(motor) == 0


def test_datos_con_otro_calendario_precargado_conservan_su_municipio(ruta):
    """Antes de la 2.14 los festivos precargados podían ser de otro municipio: al
    actualizar, la base que nunca guardó su municipio lo conserva (no pasa a Madrid)."""
    from alembic import command

    ruta.parent.mkdir(parents=True)
    motor = crear_motor(ruta)
    config = bd._config_alembic()
    with motor.begin() as conexion:
        config.attributes["conexion"] = conexion
        command.upgrade(config, "0008")
        conexion.exec_driver_sql(
            "INSERT INTO carga_festivos (anio, calendario, completo, cargado_en) VALUES (2026, 'alcobendas', 1, '2026-01-01')")
    inicializar(ruta)
    with Session(motor) as s:
        assert leer_ajustes(s).municipio == "28006"  # Alcobendas
        assert num_festivos(motor) == 0  # y no recibe los precargados de Madrid


def test_datos_nuevos_o_ya_con_municipio_no_cambian(ruta):
    inicializar(ruta)  # nueva: Madrid por defecto, sin guardarlo
    with Session(crear_motor(ruta)) as s:
        assert leer_ajustes(s).municipio == "28079"
        assert s.get(Ajuste, "municipio") is None
