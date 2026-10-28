"""Opción «todos trabajan cada día laborable» (salvo ausencia)."""

from datetime import date, timedelta

from turnos.dominio.modelos import Ausencia, Elegibilidad, Mitad, RangoCarga, Turno
from turnos.motor.entrada import Cobertura, Problema, ReglasMedico
from turnos.motor.modelo_cpsat import generar
from turnos.motor.resultado import TipoAviso
from turnos.motor.validacion import validar

M, T = Turno.MANANA, Turno.TARDE
LUNES = date(2026, 11, 2)
DIAS = tuple(LUNES + timedelta(days=7 * s + d) for s in range(2) for d in range(5))


def problema(medicos, manana=(1, 3), tarde=(1, 3), todos=True):
    cob = {(d, h): Cobertura(*(manana if h.turno is M else tarde)) for d in DIAS for h in Mitad}
    return Problema(dias=DIAS, cobertura=cob, medicos=tuple(medicos), todos_trabajan=todos)


def medico(id_, **kw):
    return ReglasMedico(id=id_, nombre=f"Médico {id_}", carga=RangoCarga(0, 100), **kw)


def dias_trabajados(r, m):
    return {a.fecha for a in r.asignaciones if a.medico_id == m}


def test_todos_trabajan_cada_dia():
    p = problema([medico(i) for i in range(1, 5)])
    r = generar(p)
    assert r.valido, r.avisos
    for m in range(1, 5):
        assert dias_trabajados(r, m) == set(DIAS)


def test_sin_la_opcion_no_todos_trabajan_cada_dia():
    p = problema([medico(i) for i in range(1, 5)], todos=False)
    r = generar(p)
    assert any(dias_trabajados(r, m) != set(DIAS) for m in range(1, 5))


def test_ausencias_y_dias_sin_turno_posible_quedan_exentos():
    vacaciones = (Ausencia(DIAS[0], DIAS[1]),)  # lunes y martes
    solo_tarde_libre = (Ausencia(DIAS[2], DIAS[2], M),)  # miércoles por la mañana
    nunca_viernes = {(4, M): Elegibilidad.NO_DISPONIBLE, (4, T): Elegibilidad.NO_DISPONIBLE}
    p = problema([
        medico(1, ausencias=vacaciones + solo_tarde_libre),
        medico(2, elegibilidad=nunca_viernes),
        medico(3),
    ])
    r = generar(p)
    assert r.valido, r.avisos
    assert dias_trabajados(r, 1) == set(DIAS) - {DIAS[0], DIAS[1]}
    assert {a.mitad.turno for a in r.asignaciones if a.medico_id == 1 and a.fecha == DIAS[2]} == {T}
    assert dias_trabajados(r, 2) == {d for d in DIAS if d.weekday() != 4}


def test_avisa_si_choca_con_la_cobertura_maxima_y_la_carga():
    # 4 médicos todos los días, pero la cobertura máxima es de 1 + 1.
    p = problema(
        [medico(1), medico(2), medico(3), ReglasMedico(id=4, nombre="Médico 4", carga=RangoCarga(0, 10))],
        manana=(1, 1), tarde=(1, 1),
    )
    r = generar(p)
    causas = [a.mensaje for a in r.avisos if a.tipo is TipoAviso.CAUSA]
    assert any("el lunes 2/11 trabajan 4 médicos y la cobertura máxima de mañana y tarde suma 2" in c for c in causas)
    assert any("Médico 4 trabajará 10 días este mes y su carga máxima es de 5 turnos" in c for c in causas)
    # La regla va por delante del máximo: todos trabajan, y sobra gente.
    assert all(dias_trabajados(r, m) == set(DIAS) for m in range(1, 5))
    assert "El lunes 2/11 por la mañana sobra 1 médico." in [a.mensaje for a in r.avisos]


def test_validacion_avisa_de_un_medico_sin_turno():
    p = problema([medico(i) for i in range(1, 4)])
    r = generar(p)
    sin_lunes = {a for a in r.asignaciones if not (a.medico_id == 2 and a.fecha == LUNES)}
    mensajes = [a.mensaje for a in validar(p, sin_lunes)]
    assert "Médico 2 no tiene turno el lunes 2/11." in mensajes
