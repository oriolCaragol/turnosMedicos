"""Urgencias y domicilios en las tardes (un médico distinto para cada papel)."""

from collections import Counter
from datetime import date, timedelta

from turnos.dominio.modelos import (
    Asignacion,
    Ausencia,
    Elegibilidad,
    Mitad,
    RangoCarga,
    Rol,
    TipoJornada,
    Turno,
)
from turnos.motor.entrada import Cobertura, Problema, ReglasMedico
from turnos.motor.modelo_cpsat import generar
from turnos.motor.validacion import validar

M, T = Turno.MANANA, Turno.TARDE
U, D = Rol.URGENCIAS, Rol.DOMICILIOS
LUNES = date(2026, 11, 2)


def dias(semanas=1):
    return tuple(LUNES + timedelta(days=7 * s + d) for s in range(semanas) for d in range(5))


def problema(medicos, semanas=1, manana=(1, 1), tarde=(2, 2), **kw):
    ds = dias(semanas)
    cob = {(d, h): Cobertura(*(manana if h.turno is M else tarde)) for d in ds for h in Mitad}
    return Problema(dias=ds, cobertura=cob, medicos=tuple(medicos), **kw)


def medico(id_, **kw):
    return ReglasMedico(id=id_, nombre=f"Médico {id_}", carga=RangoCarga(0, 100), **kw)


def tarde_completa(r, medico_id, dia):
    return {a.mitad for a in r.asignaciones if a.medico_id == medico_id and a.fecha == dia} >= set(T.mitades)


def test_cada_tarde_un_medico_distinto_para_cada_papel():
    p = problema([medico(i) for i in range(1, 6)])
    r = generar(p)
    assert r.valido
    for dia in p.dias:
        urg, dom = r.roles[dia, U], r.roles[dia, D]
        assert urg != dom
        assert tarde_completa(r, urg, dia) and tarde_completa(r, dom, dia)


def test_reparto_uniforme_entre_los_que_pueden_hacer_tardes():
    # 4 médicos, 10 tardes: 2 o 3 urgencias y 2 o 3 domicilios cada uno.
    p = problema([medico(i) for i in range(1, 5)], semanas=2)
    r = generar(p)
    for rol in Rol:
        veces = Counter(m for (_, rr), m in r.roles.items() if rr is rol)
        assert set(veces) == {1, 2, 3, 4}
        assert all(2 <= n <= 3 for n in veces.values()), veces


def test_quien_no_puede_hacer_tardes_no_recibe_papeles_y_las_ausencias_no_desequilibran():
    solo_mananas = {(d, T): Elegibilidad.NO_DISPONIBLE for d in range(5)}
    ausente = (Ausencia(LUNES, LUNES + timedelta(days=4)),)  # falta la primera semana
    p = problema(
        [medico(1, elegibilidad=solo_mananas), medico(2, ausencias=ausente), medico(3), medico(4), medico(5)],
        semanas=2,
    )
    r = generar(p)
    assert r.valido
    veces = Counter(r.roles.values())
    assert veces[1] == 0
    # El médico 2 solo está 5 de las 10 tardes, pero le bastan para tener las mismas
    # veces que los demás (20 papeles entre 4: 5 cada uno).
    assert [veces[m] for m in (2, 3, 4, 5)] == [5, 5, 5, 5]


# El médico 1 solo puede hacer la tarde de los lunes (2 en dos semanas): no puede tener
# su parte de los dos papeles (2,5 de cada uno) a la vez. Alguno tiene que quedar desigual.
SOLO_LUNES = {(d, T): Elegibilidad.NO_DISPONIBLE for d in range(1, 5)}


def test_si_es_inevitable_la_desigualdad_va_a_los_domicilios():
    """Por defecto, las urgencias se reparten por igual y la diferencia va a domicilios."""
    p = problema([medico(1, elegibilidad=SOLO_LUNES), medico(2), medico(3), medico(4)], semanas=2)
    r = generar(p)
    assert r.valido
    urgencias, domicilios = _veces(r, U), _veces(r, D)
    assert max(urgencias[m] for m in range(1, 5)) - min(urgencias[m] for m in range(1, 5)) <= 1
    assert urgencias[1] == 2 and domicilios[1] == 0  # sus dos tardes, de urgencias
    resto = [domicilios[m] for m in (2, 3, 4)]
    assert max(resto) - min(resto) <= 1


def test_con_prioridad_en_domicilios_la_desigualdad_va_a_urgencias():
    p = problema([medico(1, elegibilidad=SOLO_LUNES), medico(2), medico(3), medico(4)], semanas=2,
                 prioridad_roles=D)
    r = generar(p)
    urgencias, domicilios = _veces(r, U), _veces(r, D)
    assert max(domicilios[m] for m in range(1, 5)) - min(domicilios[m] for m in range(1, 5)) <= 1
    assert domicilios[1] == 2 and urgencias[1] == 0


def test_sin_prioridad_la_diferencia_se_reparte_entre_los_dos_papeles():
    p = problema([medico(1, elegibilidad=SOLO_LUNES), medico(2), medico(3), medico(4)], semanas=2,
                 prioridad_roles=None)
    r = generar(p)
    assert r.valido
    for rol in Rol:
        veces = _veces(r, rol)
        assert veces[1] <= 1
        resto = [veces[m] for m in (2, 3, 4)]
        assert max(resto) - min(resto) <= 1, (rol, resto)


def test_media_tarde_no_basta_para_un_papel():
    p = problema([medico(1, jornadas={d: TipoJornada.MANANA_MAS_MEDIA for d in range(5)}),
                  medico(2), medico(3), medico(4)],
                 manana=(1, 2), tarde=(2, 3))
    r = generar(p)
    assert 1 not in r.roles.values()


def test_papel_fijado_a_mano():
    bloqueadas = frozenset(Asignacion(3, LUNES, h) for h in T.mitades)
    p = problema([medico(i) for i in range(1, 5)], bloqueadas=bloqueadas, roles_fijados={(LUNES, D): 3})
    assert generar(p).roles[LUNES, D] == 3


def test_sin_dos_medicos_de_tarde_falta_un_papel():
    p = problema([medico(1), medico(2, elegibilidad={(d, T): Elegibilidad.NO_DISPONIBLE for d in range(5)})],
                 manana=(1, 1), tarde=(2, 2))
    r = generar(p)
    assert not r.valido
    assert any("por la tarde nadie hace" in a.mensaje for a in r.avisos)


def test_con_un_solo_medico_de_tarde_no_hay_papeles():
    # Con cobertura de 1 por la tarde no se exigen urgencias ni domicilios.
    p = problema([medico(i) for i in range(1, 4)], tarde=(1, 1))
    r = generar(p)
    assert r.valido and r.roles == {}


def test_validacion_de_papeles():
    p = problema([medico(i) for i in range(1, 5)])
    r = generar(p)
    roles = dict(r.roles)
    assert validar(p, r.asignaciones, roles) == []
    # Mismo médico para los dos papeles, y alguien sin tarde completa.
    roles[LUNES, D] = roles[LUNES, U]
    sin_tarde = next(m for m in range(1, 5) if not tarde_completa(r, m, LUNES + timedelta(1)))
    roles[LUNES + timedelta(1), U] = sin_tarde
    del roles[LUNES + timedelta(2), D]
    mensajes = [a.mensaje for a in validar(p, r.asignaciones, roles)]
    assert any("urgencias y domicilios a la vez el lunes 2/11" in m for m in mensajes)
    assert any(f"Médico {sin_tarde} hace urgencias el martes 3/11 pero no tiene la tarde completa." == m for m in mensajes)
    assert "El miércoles 4/11 por la tarde nadie hace domicilios." in mensajes


def test_estabilidad_de_los_papeles_al_regenerar():
    p = problema([medico(i) for i in range(1, 6)], semanas=2)
    r1 = generar(p)
    p2 = Problema(dias=p.dias, cobertura=p.cobertura, medicos=p.medicos,
                  anterior=frozenset(r1.asignaciones), roles_anteriores=r1.roles)
    assert generar(p2).roles == r1.roles


def test_reparto_igualado_aunque_unos_tengan_mas_tardes_disponibles():
    # 4 médicos y 6 tardes con papeles; dos de ellos solo pueden 3 tardes de cada semana
    # (lunes a miércoles), pero eso les basta para tener las mismas veces que los demás.
    # Antes, la parte «proporcional a las tardes disponibles» permitía 3 / 2 / 1.
    lunes_a_miercoles = {(d, T): Elegibilidad.NO_DISPONIBLE for d in (3, 4)}
    p = problema(
        [medico(1), medico(2), medico(3, elegibilidad=lunes_a_miercoles), medico(4, elegibilidad=lunes_a_miercoles)],
        semanas=2, manana=(0, 4), tarde=(2, 2),
    )
    r = generar(p)
    assert r.valido
    for rol in Rol:
        veces = Counter(m for (_, rr), m in r.roles.items() if rr is rol)
        cuentas = [veces[m] for m in (1, 2, 3, 4)]
        assert max(cuentas) - min(cuentas) <= 1, (rol, cuentas)
    total = Counter(r.roles.values())
    cuentas = [total[m] for m in (1, 2, 3, 4)]
    assert max(cuentas) - min(cuentas) <= 1, cuentas


def test_partes():
    from fractions import Fraction as F

    from turnos.motor.modelo_cpsat import partes

    iguales = {1: 1, 2: 1, 3: 1, 4: 1}
    # 10 entre 4: 2,5 cada uno, sin importar cuántas tardes tenga cada uno.
    assert partes(10, {1: 20, 2: 20, 3: 8, 4: 6}, iguales) == {m: F(5, 2) for m in iguales}
    # Quien solo puede 1 se queda con 1; los otros 9, entre 3.
    assert partes(10, {1: 1, 2: 20, 3: 20, 4: 20}, iguales) == {1: 1, 2: 3, 3: 3, 4: 3}
    # Con pesos (presencia): la mitad de presencia, la mitad de parte.
    assert partes(14, {1: 20, 2: 20, 3: 20, 4: 20}, {1: 5, 2: 10, 3: 10, 4: 10}) == {1: 2, 2: 4, 3: 4, 4: 4}
    # Con pesos y alguien limitado por sus tardes.
    assert partes(12, {1: 1, 2: 20, 3: 20}, {1: 10, 2: 10, 3: 5}) == {1: 1, 2: F(22, 3), 3: F(11, 3)}
    # Sin peso (ausente todo el mes): sin parte.
    assert partes(10, {1: 20, 2: 20}, {1: 0, 2: 10}) == {2: 10}


def _veces(r, rol=None):
    return Counter(m for (_, rr), m in r.roles.items() if rol is None or rr is rol)


def test_segun_presencia_las_ausencias_reducen_la_parte():
    ausente = (Ausencia(LUNES, LUNES + timedelta(days=4)),)  # falta la primera de dos semanas
    medicos = [medico(1, ausencias=ausente), medico(2), medico(3), medico(4)]
    # Por igual: 5 papeles cada uno (le bastan sus 5 tardes).
    r = generar(problema(medicos, semanas=2))
    assert [_veces(r)[m] for m in (1, 2, 3, 4)] == [5, 5, 5, 5]
    # Según presencia: 5 de 10 tardes frente a 10 → la mitad. 10 de cada papel:
    # partes 1,43 / 2,86 / 2,86 / 2,86 → 1 / 3 / 3 / 3.
    r = generar(problema(medicos, semanas=2, roles_segun_presencia=True))
    assert r.valido
    for rol in Rol:
        assert [_veces(r, rol)[m] for m in (1, 2, 3, 4)] == [1, 3, 3, 3], rol
    assert _veces(r)[1] == 2  # juntos, a la fuerza 1 + 1


def test_segun_presencia_sin_diferencias_injustificadas():
    # Como el mes real que dio 3 / 2 / 1: 10 médicos, dos con 3 tardes de ausencia y
    # 20 tardes con papel. Las partes (2,06 y 1,75) se redondean a 2 para todos.
    ausencia = (Ausencia(LUNES, LUNES + timedelta(days=2)),)
    medicos = [medico(i, ausencias=ausencia if i in (1, 2) else ()) for i in range(1, 11)]
    p = problema(medicos, semanas=4, manana=(0, 10), tarde=(2, 10), roles_segun_presencia=True)
    r = generar(p)
    assert r.valido
    for rol in Rol:
        assert set(_veces(r, rol).values()) == {2}, _veces(r, rol)


def test_bandas_por_restos_mayores():
    from fractions import Fraction as F

    from turnos.motor.modelo_cpsat import bandas

    # El mes real: 8 con 2,06 y 2 con 1,75 (total 20) → 2 para todos.
    partes = {**{m: F(400, 194) for m in range(1, 9)}, 9: F(340, 194), 10: F(340, 194)}
    assert set(bandas(partes).values()) == {(2, 2)}
    # Todos iguales (25 entre 30): abierta para todos.
    assert set(bandas({m: F(5, 6) for m in range(30)}).values()) == {(0, 1)}
    # Enteras: fijas.
    assert bandas({1: F(3), 2: F(1)}) == {1: (3, 3), 2: (1, 1)}
    # Un resto mayor y un empate en el siguiente: 1,9 → 2; 1,55 y 1,55 → 1 o 2 (sobra 1).
    assert bandas({1: F(19, 10), 2: F(31, 20), 3: F(31, 20)}) == {1: (2, 2), 2: (1, 2), 3: (1, 2)}
