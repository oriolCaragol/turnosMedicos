from datetime import date, timedelta

from turnos.dominio.modelos import (
    Asignacion,
    Ausencia,
    Elegibilidad,
    Mitad,
    RangoCarga,
    TipoJornada,
    Turno,
)
from turnos.motor.entrada import Cobertura, Problema, ReglasMedico
from turnos.motor.modelo_cpsat import generar
from turnos.motor.validacion import validar

M, T = Turno.MANANA, Turno.TARDE
LUNES = date(2026, 11, 2)
DIAS = tuple(LUNES + timedelta(d) for d in range(5))


def medico(id_, minimo=0, maximo=100, **kw):
    return ReglasMedico(id=id_, nombre=f"Médico {id_}", carga=RangoCarga(minimo, maximo), **kw)


def problema(medicos):
    cob = {(d, h): Cobertura(1, 1) for d in DIAS for h in Mitad}
    return Problema(dias=DIAS, cobertura=cob, medicos=tuple(medicos))


def turno(medico_id, fecha, t):
    return {Asignacion(medico_id, fecha, h) for h in t.mitades}


def test_un_calendario_generado_valido_no_tiene_avisos():
    p = problema([medico(1), medico(2), medico(3)])
    assert validar(p, generar(p).asignaciones) == []


def test_cobertura_y_carga_tras_quitar_un_medico():
    p = problema([medico(1, 4, 100), medico(2), medico(3)])
    asignaciones = set(generar(p).asignaciones)
    # Se quita al médico 1 de todos sus turnos.
    asignaciones = {a for a in asignaciones if a.medico_id != 1}
    mensajes = [a.mensaje for a in validar(p, asignaciones)]
    assert any("falta 1 médico" in m for m in mensajes)
    assert "Médico 1 tiene 0 turnos, por debajo de su mínimo de 2." in mensajes


def test_sobra_personal():
    p = problema([medico(1), medico(2), medico(3)])
    asignaciones = set(generar(p).asignaciones)
    extra = next(m for m in (1, 2, 3) if not any(a.medico_id == m and a.fecha == LUNES for a in asignaciones))
    mensajes = [a.mensaje for a in validar(p, asignaciones | turno(extra, LUNES, M))]
    assert "El lunes 2/11 por la mañana sobra 1 médico." in mensajes


def test_asignado_sin_estar_disponible_o_ausente():
    p = problema([
        medico(1, elegibilidad={(0, T): Elegibilidad.NO_DISPONIBLE}),
        medico(2, ausencias=(Ausencia(LUNES, LUNES),)),
    ])
    mensajes = [a.mensaje for a in validar(p, turno(1, LUNES, T) | turno(2, LUNES, M))]
    assert "Médico 1 está asignado el lunes 2/11 por la tarde pero no está disponible en ese turno." in mensajes
    assert "Médico 2 está asignado el lunes 2/11 por la mañana pero está ausente." in mensajes


def test_jornada_especial_no_se_considera_no_disponible():
    reglas = medico(
        1,
        elegibilidad={(0, T): Elegibilidad.NO_DISPONIBLE},
        jornadas={0: TipoJornada.MANANA_MAS_MEDIA},
    )
    asignaciones = {Asignacion(1, LUNES, h) for h in TipoJornada.MANANA_MAS_MEDIA.mitades}
    mensajes = [a.mensaje for a in validar(problema([reglas]), asignaciones)]
    assert not any("no está disponible" in m for m in mensajes)


def test_dia_no_laborable():
    sabado = date(2026, 11, 7)
    mensajes = [a.mensaje for a in validar(problema([medico(1)]), turno(1, sabado, M))]
    assert "Médico 1 está asignado el sábado 7/11 por la mañana pero es festivo o fin de semana." in mensajes
