"""Comprobaciones previas de viabilidad (diseño, 6.6, primera capa).

Detectan, antes de resolver, situaciones en las que es imposible un
calendario válido, y explican la causa en términos concretos.
"""

from collections import Counter, defaultdict

from turnos.dominio.modelos import Mitad, Turno, formatear_medios
from turnos.motor.entrada import Preparado, Problema, dias_obligatorios
from turnos.motor.resultado import Aviso, TipoAviso, agrupar_mitades, fmt_fecha, medicos_txt


def comprobar(problema: Problema, prep: Preparado) -> list[Aviso]:
    return _cobertura(problema, prep) + _carga(problema, prep) + _todos_trabajan(problema, prep)


def _todos_trabajan(problema: Problema, prep: Preparado) -> list[Aviso]:
    """Con «todos trabajan cada día»: choques con la cobertura máxima y la carga máxima."""
    obligatorios = dias_obligatorios(problema, prep)
    if not obligatorios:
        return []
    avisos = []
    for dia in problema.dias:
        trabajan = sum(1 for dias in obligatorios.values() if dia in dias)
        # Cada médico hace como mínimo un turno completo (dos mitades) ese día.
        maximo = sum(problema.cob(dia, h).maximo for h in Mitad) // 2
        if trabajan > maximo:
            avisos.append(Aviso(
                TipoAviso.CAUSA,
                f"Todos trabajan cada día: el {fmt_fecha(dia)} trabajan {trabajan} médicos y la cobertura "
                f"máxima de mañana y tarde suma {maximo}. Sube los máximos en Cobertura o desactiva la "
                "opción en Configuración.",
                fecha=dia,
            ))
    for med in problema.medicos:
        dias = len(obligatorios.get(med.id, ()))
        if dias * 2 > med.carga.maximo:
            avisos.append(Aviso(
                TipoAviso.CAUSA,
                f"Todos trabajan cada día: {med.nombre} trabajará {dias} días este mes y su carga máxima es de "
                f"{formatear_medios(med.carga.maximo)} turnos.",
                medico_id=med.id,
            ))
    return avisos


def _cobertura(problema: Problema, prep: Preparado) -> list[Aviso]:
    fijados = Counter((a.fecha, a.mitad) for a in prep.fijadas)
    candidatos = Counter((dia, t) for _, dia, t in prep.candidatos)
    avisos = []
    for dia in problema.dias:
        pocos, demasiados = {}, {}
        for h in Mitad:
            cob = problema.cob(dia, h)
            posibles = fijados[dia, h] + candidatos[dia, h.turno]
            if posibles < cob.minimo:
                pocos[h] = (cob.minimo, posibles)
            if fijados[dia, h] > cob.maximo:
                demasiados[h] = (cob.maximo, fijados[dia, h])
        for lugar, (minimo, posibles) in agrupar_mitades(pocos):
            avisos.append(Aviso(
                TipoAviso.CAUSA,
                f"El {fmt_fecha(dia)} {lugar} se {'necesita' if minimo == 1 else 'necesitan'} "
                f"{medicos_txt(minimo)} "
                f"pero {_disponibles(posibles)}.",
                fecha=dia,
            ))
        for lugar, (maximo, fijos) in agrupar_mitades(demasiados):
            avisos.append(Aviso(
                TipoAviso.CAUSA,
                f"El {fmt_fecha(dia)} {lugar} hay {medicos_txt(fijos)} fijados de antemano "
                f"y el máximo es {maximo}.",
                fecha=dia,
            ))
    return avisos


def _carga(problema: Problema, prep: Preparado) -> list[Aviso]:
    # Medios turnos fijados por médico, total y por turno.
    fijados: dict[int, Counter] = defaultdict(Counter)
    for a in prep.fijadas:
        fijados[a.medico_id][a.mitad.turno] += 1
    # Días en los que cada médico podría hacer un turno, total y por turno.
    dias_posibles: dict[int, set] = defaultdict(set)
    dias_posibles_turno: dict[tuple[int, Turno], set] = defaultdict(set)
    for m_id, dia, t in prep.candidatos:
        dias_posibles[m_id].add(dia)
        dias_posibles_turno[m_id, t].add(dia)

    avisos = []
    capacidad = 0
    for m in problema.medicos:
        fijo = sum(fijados[m.id].values())
        alcanzable = fijo + 2 * len(dias_posibles[m.id])
        capacidad += min(alcanzable, m.carga.maximo)
        avisos += _rango(m.id, f"{m.nombre}", "turnos", m.carga, fijo, alcanzable)
        for t, rango in m.carga_por_turno.items():
            fijo_t = fijados[m.id][t]
            alcanzable_t = fijo_t + 2 * len(dias_posibles_turno[m.id, t])
            nombre_t = "mañanas" if t is Turno.MANANA else "tardes"
            avisos += _rango(m.id, m.nombre, nombre_t, rango, fijo_t, alcanzable_t)

    demanda = sum(problema.cob(dia, h).minimo for dia in problema.dias for h in Mitad)
    if capacidad < demanda:
        avisos.append(Aviso(
            TipoAviso.CAUSA,
            f"El equipo puede cubrir como máximo {formatear_medios(capacidad)} turnos "
            f"este mes y se necesitan {formatear_medios(demanda)}.",
        ))
    return avisos


def _rango(m_id, nombre, unidad, rango, fijo, alcanzable) -> list[Aviso]:
    avisos = []
    if alcanzable < rango.minimo:
        avisos.append(Aviso(
            TipoAviso.CAUSA,
            f"{nombre} necesita al menos {formatear_medios(rango.minimo)} {unidad} este mes "
            f"pero solo puede hacer {formatear_medios(alcanzable)}.",
            medico_id=m_id,
        ))
    if fijo > rango.maximo:
        avisos.append(Aviso(
            TipoAviso.CAUSA,
            f"{nombre}: lo fijado este mes suma {formatear_medios(fijo)} {unidad} "
            f"y su máximo es {formatear_medios(rango.maximo)}.",
            medico_id=m_id,
        ))
    return avisos


def _disponibles(n: int) -> str:
    if n == 0:
        return "no hay ninguno disponible"
    return f"solo hay {n} disponible" if n == 1 else f"solo hay {n} disponibles"
