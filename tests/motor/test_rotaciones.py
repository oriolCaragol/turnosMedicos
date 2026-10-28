"""Turnos rotativos: unos turnos de la semana que un grupo hace por semanas alternas."""

from datetime import date, timedelta

from turnos.dominio.modelos import Asignacion, Ausencia, Mitad, RangoCarga, Turno
from turnos.motor.entrada import Cobertura, Problema, ReglasMedico, Rotacion, preparar
from turnos.motor.modelo_cpsat import generar
from turnos.motor.validacion import validar

M, T = Turno.MANANA, Turno.TARDE
LUNES = date(2026, 11, 2)
DIAS = tuple(LUNES + timedelta(days=7 * s + d) for s in range(4) for d in range(5))


def medico(id_, **kw):
    return ReglasMedico(id=id_, nombre=f"Médico {id_}", carga=RangoCarga(0, 100), **kw)


def problema(medicos, rotaciones, **kw):
    cob = {(d, h): Cobertura(1, 3) for d in DIAS for h in Mitad}
    return Problema(dias=DIAS, cobertura=cob, medicos=tuple(medicos), rotaciones=tuple(rotaciones), **kw)


def tiene(r, medico_id, dia, turno):
    return any(a.medico_id == medico_id and a.fecha == dia and a.mitad.turno is turno for a in r.asignaciones)


# Lunes por la mañana y jueves por la tarde, alternando entre los médicos 1 y 2.
ROT = Rotacion(medicos=(1, 2), huecos=frozenset({(0, M), (3, T)}), desde=LUNES, nombre="Lun-Jue")


def test_alterna_por_semanas_sin_coincidir():
    r = generar(problema([medico(i) for i in range(1, 5)], [ROT]))
    assert r.valido
    for semana in range(4):
        lunes, jueves = DIAS[semana * 5], DIAS[semana * 5 + 3]
        titular, otro = (1, 2) if semana % 2 == 0 else (2, 1)
        assert tiene(r, titular, lunes, M) and tiene(r, titular, jueves, T)
        assert not tiene(r, otro, lunes, M) and not tiene(r, otro, jueves, T)


def test_tres_medicos_y_semana_de_inicio_posterior():
    rot = Rotacion(medicos=(3, 1, 2), huecos=frozenset({(2, M)}), desde=LUNES + timedelta(days=7 + 2))  # miércoles 11
    r = generar(problema([medico(i) for i in range(1, 5)], [rot]))
    miercoles = [d for d in DIAS if d.weekday() == 2]
    assert tiene(r, 3, miercoles[1], M) and tiene(r, 1, miercoles[2], M) and tiene(r, 2, miercoles[3], M)
    assert rot.titular(miercoles[0], M) is None  # antes de empezar no hay rotación


def test_si_al_titular_le_falta_el_turno_queda_libre_para_los_demas():
    ausente = (Ausencia(LUNES, LUNES),)
    p = problema([medico(1, ausencias=ausente), medico(2), medico(3)], [ROT])
    prep = preparar(p)
    # El lunes 2 le tocaba a 1, que está ausente: 2 puede hacerlo.
    assert (2, LUNES, M) in prep.candidatos
    # El jueves 5 le toca a 1 (presente): 2 no puede coincidir con él.
    assert (2, LUNES + timedelta(days=3), T) not in prep.candidatos
    r = generar(p)
    assert r.valido and not tiene(r, 1, LUNES, M)


def test_validacion_avisa_si_coinciden():
    p = problema([medico(i) for i in range(1, 4)], [ROT])
    r = generar(p)
    extra = {Asignacion(2, LUNES, h) for h in M.mitades}
    mensajes = [a.mensaje for a in validar(p, set(r.asignaciones) | extra)]
    assert "Médico 2 coincide con Médico 1 en el turno rotativo «Lun-Jue» el lunes 2/11 por la mañana." in mensajes


def test_la_rotacion_manda_sobre_el_fijo_de_la_tarjeta():
    # El médico 2 tiene los lunes por la mañana como Fijo en su tarjeta, pero la
    # semana que le toca al 1 no puede coincidir con él.
    from turnos.dominio.modelos import Elegibilidad
    p = problema([medico(1), medico(2, elegibilidad={(0, M): Elegibilidad.FIJO}), medico(3)], [ROT])
    r = generar(p)
    assert tiene(r, 1, LUNES, M) and not tiene(r, 2, LUNES, M)
    assert tiene(r, 2, LUNES + timedelta(days=7), M)
