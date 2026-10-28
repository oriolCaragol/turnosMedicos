import time
from datetime import date, timedelta

import pytest

from turnos.dominio.modelos import (
    Asignacion,
    Ausencia,
    Elegibilidad,
    Mitad,
    OrigenAsignacion,
    Preferencia,
    RangoCarga,
    TipoJornada,
    Turno,
)
from turnos.motor.entrada import Cobertura, Problema, ReglasMedico
from turnos.motor.modelo_cpsat import Parametros, SinAlternativa, generar, objetivos_equidad
from turnos.motor.resultado import TipoAviso

M, T = Turno.MANANA, Turno.TARDE
F, N = Elegibilidad.FIJO, Elegibilidad.NO_DISPONIBLE
LUNES = date(2026, 11, 2)


def laborables(semanas: int = 1) -> tuple[date, ...]:
    return tuple(
        LUNES + timedelta(days=7 * s + d) for s in range(semanas) for d in range(5)
    )


def cobertura(dias, manana=(1, 1), tarde=(1, 1)) -> dict:
    return {
        (dia, h): Cobertura(*(manana if h.turno is M else tarde)) for dia in dias for h in Mitad
    }


def medico(id_: int, minimo: int = 0, maximo: int = 100, **kw) -> ReglasMedico:
    return ReglasMedico(id=id_, nombre=f"Médico {id_}", carga=RangoCarga(minimo, maximo), **kw)


def problema(medicos, semanas=1, **kw) -> Problema:
    dias = laborables(semanas)
    kw.setdefault("cobertura", cobertura(dias))
    return Problema(dias=dias, medicos=tuple(medicos), **kw)


def en(resultado, dia: date, mitad: Mitad) -> set[int]:
    return {a.medico_id for a in resultado.asignaciones if a.fecha == dia and a.mitad is mitad}


def turnos_de(resultado, medico_id: int) -> set[tuple[date, Turno]]:
    return {(a.fecha, a.mitad.turno) for a in resultado.asignaciones if a.medico_id == medico_id}


def textos(resultado, tipo: TipoAviso) -> list[str]:
    return [a.mensaje for a in resultado.avisos if a.tipo is tipo]


# --- Restricciones estrictas --------------------------------------------------


def test_calendario_valido_cubre_cada_mitad():
    p = problema([medico(i) for i in range(1, 4)])
    r = generar(p)
    assert r.valido and r.optimo and r.avisos == ()
    for dia in p.dias:
        for h in Mitad:
            assert len(en(r, dia, h)) == 1


def test_el_generador_asigna_turnos_completos_y_uno_al_dia():
    p = problema([medico(i) for i in range(1, 4)])
    r = generar(p)
    for dia in p.dias:
        for m in p.medicos:
            mitades = {a.mitad for a in r.asignaciones if a.fecha == dia and a.medico_id == m.id}
            assert mitades in (set(), set(M.mitades), set(T.mitades))


def test_huecos_fijos_y_no_disponibles():
    eleg = {(0, M): F, (1, M): F, (2, M): N, (2, T): N}
    p = problema([medico(1, elegibilidad=eleg), medico(2), medico(3)])
    r = generar(p)
    assert r.valido
    assert {(LUNES, M), (LUNES + timedelta(1), M)} <= turnos_de(r, 1)
    assert not {d for d, _ in turnos_de(r, 1)} & {LUNES + timedelta(2)}
    assert r.asignaciones[Asignacion(1, LUNES, Mitad.M1)] is OrigenAsignacion.FIJO


def test_ausencias():
    ausencias = (Ausencia(LUNES, LUNES + timedelta(1)), Ausencia(LUNES, LUNES + timedelta(4), T))
    p = problema([medico(1, ausencias=ausencias), medico(2), medico(3)])
    r = generar(p)
    assert r.valido
    for dia, turno in turnos_de(r, 1):
        assert turno is M and dia >= LUNES + timedelta(2)


def test_fijo_con_ausencia_no_se_asigna():
    p = problema([
        medico(1, elegibilidad={(0, M): F}, ausencias=(Ausencia(LUNES, LUNES),)),
        medico(2),
        medico(3),
    ])
    assert (LUNES, M) not in turnos_de(generar(p), 1)


def test_jornada_de_manana_mas_media_tarde_cuenta_en_la_cobertura():
    # El lunes el médico 1 hace mañana + primera mitad de la tarde.
    # La primera mitad de la tarde admite 2 médicos para que alguien cubra la tarde completa.
    dias = laborables()
    cob = cobertura(dias)
    cob[LUNES, Mitad.T1] = Cobertura(1, 2)
    p = problema(
        [medico(1, jornadas={0: TipoJornada.MANANA_MAS_MEDIA}), medico(2), medico(3)],
        cobertura=cob,
    )
    r = generar(p)
    assert r.valido
    assert {a.mitad for a in r.asignaciones if a.medico_id == 1 and a.fecha == LUNES} == {
        Mitad.M1, Mitad.M2, Mitad.T1
    }
    assert len(en(r, LUNES, Mitad.T1)) == 2 and len(en(r, LUNES, Mitad.T2)) == 1


def test_el_generador_nunca_crea_jornadas_largas():
    # Un solo médico y cobertura de mañana y tarde: no puede hacer ambas.
    p = problema([medico(1)])
    r = generar(p)
    assert not r.valido
    for dia in p.dias:
        assert len({a.mitad.turno for a in r.asignaciones if a.fecha == dia}) == 1


def test_asignaciones_bloqueadas_se_respetan_aunque_incumplan_reglas():
    bloqueadas = frozenset(Asignacion(1, LUNES, h) for h in T.mitades)
    p = problema(
        [medico(1, elegibilidad={(0, T): N}), medico(2), medico(3)], bloqueadas=bloqueadas
    )
    r = generar(p)
    assert (LUNES, T) in turnos_de(r, 1)
    assert r.asignaciones[Asignacion(1, LUNES, Mitad.T1)] is OrigenAsignacion.MANUAL
    assert (LUNES, M) not in turnos_de(r, 1)  # ese día ya tiene algo fijado


def test_vetadas_no_se_asignan():
    vetadas = frozenset({(1, dia, t) for dia in laborables() for t in Turno})
    p = problema(
        [medico(1, elegibilidad={(0, M): F}), medico(2), medico(3)], vetadas=vetadas
    )
    assert turnos_de(generar(p), 1) == set()


def test_carga_mensual_dentro_del_rango():
    # Demanda 10 turnos; el médico 1 debe hacer exactamente 2 turnos (4 medios).
    p = problema([medico(1, 4, 4), medico(2), medico(3)])
    r = generar(p)
    assert r.valido and r.carga[1] == 4


def test_carga_por_tipo_de_turno():
    p = problema([
        medico(1, carga_por_turno={T: RangoCarga(6, 6)}),
        medico(2),
        medico(3),
    ])
    r = generar(p)
    assert r.valido
    assert sum(1 for _, t in turnos_de(r, 1) if t is T) == 3


# --- Inviabilidad y avisos -----------------------------------------------------


def test_falta_personal_genera_avisos_y_calendario_de_mejor_esfuerzo():
    dias = laborables()
    p = problema(
        [medico(1), medico(2)],
        cobertura=cobertura(dias, manana=(3, 3), tarde=(0, 0)),
    )
    r = generar(p)
    assert not r.valido
    assert "El lunes 2/11 por la mañana se necesitan 3 médicos pero solo hay 2 disponibles." in (
        textos(r, TipoAviso.CAUSA)
    )
    assert "El lunes 2/11 por la mañana falta 1 médico." in textos(r, TipoAviso.INCUMPLIMIENTO)
    assert len(en(r, LUNES, Mitad.M1)) == 2  # se cubre todo lo posible


def test_carga_minima_inalcanzable():
    ausencia = Ausencia(LUNES, LUNES + timedelta(2))
    p = problema([medico(1, 8, 10, ausencias=(ausencia,)), medico(2), medico(3)])
    r = generar(p)
    assert not r.valido
    assert "Médico 1 necesita al menos 4 turnos este mes pero solo puede hacer 2." in (
        textos(r, TipoAviso.CAUSA)
    )
    assert "Médico 1 tiene 2 turnos, por debajo de su mínimo de 4." in (
        textos(r, TipoAviso.INCUMPLIMIENTO)
    )


def test_aviso_en_una_sola_mitad_y_prioridad_de_cubrir():
    # La primera mitad de la tarde no admite al médico de media tarde + uno de tarde:
    # se prefiere un médico de más ahí que dejar sin cubrir la segunda mitad.
    dias = laborables()
    cob = cobertura(dias)
    cob[LUNES, Mitad.T1] = Cobertura(1, 1)
    p = problema(
        [medico(1, jornadas={0: TipoJornada.MANANA_MAS_MEDIA}), medico(2), medico(3)],
        cobertura=cob,
    )
    r = generar(p)
    assert not r.valido
    assert textos(r, TipoAviso.INCUMPLIMIENTO) == [
        "El lunes 2/11 en la primera mitad de la tarde sobra 1 médico."
    ]


def test_capacidad_total_insuficiente():
    p = problema([medico(1, 0, 2), medico(2, 0, 2)])
    r = generar(p)
    assert "El equipo puede cubrir como máximo 2 turnos este mes y se necesitan 10." in (
        textos(r, TipoAviso.CAUSA)
    )


# --- Objetivos -------------------------------------------------------------------


def test_equidad_entre_medicos_iguales():
    # 2 semanas × 2 turnos = 20 turnos entre 4 médicos: 5 cada uno.
    p = problema([medico(i) for i in range(1, 5)], semanas=2)
    r = generar(p)
    assert r.valido
    assert set(r.carga.values()) == {10}


def test_equidad_proporcional_al_rango():
    # Pesos 40, 40, 20 → objetivos 16, 16 y 8 medios turnos de una demanda de 40.
    p = problema([medico(1, 0, 40), medico(2, 0, 40), medico(3, 0, 20)], semanas=2)
    r = generar(p)
    assert r.carga == {1: 16, 2: 16, 3: 8}


def test_saldo_de_meses_anteriores_compensa():
    # Objetivos sin saldo: 10 medios turnos cada uno. El médico 1 hizo 2 turnos
    # de más en meses anteriores: su objetivo baja a 6 y acaba con menos carga.
    medicos = [medico(1, saldo=4)] + [medico(i) for i in range(2, 5)]
    p = problema(medicos, semanas=2)
    assert objetivos_equidad(p, limite_saldo=4) == {1: 6, 2: 10, 3: 10, 4: 10}
    assert objetivos_equidad(p, limite_saldo=2)[1] == 8
    r = generar(p, Parametros(limite_saldo=4))
    assert r.carga[1] <= 8 < max(r.carga.values())


def test_preferencias():
    prefs = {(d, T): Preferencia.PREFIERE for d in range(5)}
    evita = {(d, T): Preferencia.EVITA for d in range(5)}
    p = problema([medico(1, preferencias=prefs), medico(2, preferencias=evita)])
    r = generar(p)
    assert r.valido
    assert all(t is T for _, t in turnos_de(r, 1))
    assert all(t is M for _, t in turnos_de(r, 2))


def test_estabilidad_al_regenerar():
    p = problema([medico(i) for i in range(1, 5)], semanas=2)
    r1 = generar(p)
    anterior = frozenset(r1.asignaciones)
    # Se regenera con otra semilla: la estabilidad debe conservar el calendario.
    p2 = Problema(dias=p.dias, cobertura=p.cobertura, medicos=p.medicos, anterior=anterior)
    r2 = generar(p2, Parametros(semilla=7))
    assert set(r2.asignaciones) == anterior


def test_determinismo():
    p = problema([medico(i) for i in range(1, 6)], semanas=4)
    assert generar(p).asignaciones == generar(p).asignaciones


def test_alternativa_distinta():
    p = problema([medico(i) for i in range(1, 5)], semanas=2)
    r1 = generar(p)
    actual = frozenset(r1.asignaciones)
    r2 = generar(p, Parametros(alternativa_de=actual, cambios_minimos=4))
    assert r2.valido
    cambiados = {(a.medico_id, a.fecha, a.mitad.turno) for a in set(r2.asignaciones) - actual}
    assert len(cambiados) >= 4


def test_sin_alternativa_posible():
    p = problema([medico(1, elegibilidad={(d, T): N for d in range(5)}), medico(2,
                  elegibilidad={(d, M): N for d in range(5)})])
    actual = frozenset(generar(p).asignaciones)
    with pytest.raises(SinAlternativa):
        generar(p, Parametros(alternativa_de=actual))


# --- Rendimiento -------------------------------------------------------------------


def test_tamano_real_en_menos_de_10_segundos():
    dias = laborables(semanas=5)  # 25 días laborables
    medicos = [medico(i, 20, 40) for i in range(1, 31)]
    p = problema(medicos, semanas=5, cobertura=cobertura(dias, manana=(10, 12), tarde=(8, 10)))
    inicio = time.perf_counter()
    r = generar(p)
    assert time.perf_counter() - inicio < 10
    assert r.valido


def test_turno_habitual():
    # Dos médicos que pueden hacer todo; cada uno tiene su turno habitual cada día.
    H = Elegibilidad.HABITUAL
    p = problema([
        medico(1, elegibilidad={(d, M): H for d in range(5)}),
        medico(2, elegibilidad={(d, T): H for d in range(5)}),
    ])
    r = generar(p)
    assert r.valido
    assert {t for _, t in turnos_de(r, 1)} == {M}
    assert {t for _, t in turnos_de(r, 2)} == {T}


def test_habitual_no_obliga_a_trabajar_ese_dia():
    # Tres médicos con la mañana habitual todos los días y cobertura de 1:
    # cada mañana la hace uno solo, no los tres (a diferencia de Fijo).
    H = Elegibilidad.HABITUAL
    dias = laborables()
    p = problema(
        [medico(i, elegibilidad={(d, M): H for d in range(5)}) for i in (1, 2, 3)],
        cobertura=cobertura(dias, manana=(1, 1), tarde=(0, 0)),
    )
    r = generar(p)
    assert r.valido
    for dia in dias:
        assert len(en(r, dia, Mitad.M1)) == 1
