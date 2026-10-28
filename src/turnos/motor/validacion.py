"""Validación de un calendario ya hecho, p. ej. tras cambios manuales.

Devuelve los mismos avisos de incumplimiento que el motor, más los de
asignaciones en huecos donde el médico no está disponible o está ausente
(el planificador puede hacerlo, pero se le avisa; especificaciones, 7).
"""

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import date

from turnos.dominio.modelos import Asignacion, Elegibilidad, Mitad, Rol, Turno
from turnos.motor.entrada import Problema
from turnos.motor.resultado import (
    Aviso,
    TipoAviso,
    aviso_rol_sin_cubrir,
    aviso_sin_turno,
    avisos_carga,
    avisos_cobertura,
    fmt_fecha,
    fmt_turno,
)


def validar(
    problema: Problema,
    asignaciones: Iterable[Asignacion],
    roles: Mapping[tuple[date, Rol], int] | None = None,
) -> list[Aviso]:
    """Avisos de incumplimiento del calendario. Con `roles`, comprueba también
    urgencias y domicilios de cada tarde."""
    asignaciones = list(asignaciones)
    dias = set(problema.dias)
    avisos: list[Aviso] = []

    por_mitad = Counter((a.fecha, a.mitad) for a in asignaciones)
    for dia in problema.dias:
        faltas, sobras = {}, {}
        for h in Mitad:
            cob, n = problema.cob(dia, h), por_mitad[dia, h]
            faltas[h], sobras[h] = max(0, cob.minimo - n), max(0, n - cob.maximo)
        avisos += avisos_cobertura(dia, faltas, sobras)

    turnos_por_medico: dict[int, set[tuple[date, Turno]]] = defaultdict(set)
    mitades_por_medico: dict[int, Counter] = defaultdict(Counter)
    for a in asignaciones:
        turnos_por_medico[a.medico_id].add((a.fecha, a.mitad.turno))
        mitades_por_medico[a.medico_id][a.mitad.turno] += 1

    for m in problema.medicos:
        for fecha, turno in sorted(turnos_por_medico[m.id], key=lambda x: (x[0], x[1].value)):
            motivo = None
            if fecha not in dias:
                motivo = "es festivo o fin de semana"
            elif m.ausente(fecha, turno):
                motivo = "está ausente"
            elif (
                m.eleg(fecha, turno) is Elegibilidad.NO_DISPONIBLE
                and not _por_jornada(m, fecha, turno)
                and not any(r.titular(fecha, turno) == m.id for r in problema.rotaciones)
            ):
                motivo = "no está disponible en ese turno"
            if motivo:
                avisos.append(Aviso(
                    TipoAviso.INCUMPLIMIENTO,
                    f"{m.nombre} está asignado el {fmt_fecha(fecha)} {fmt_turno(turno)} pero {motivo}.",
                    fecha=fecha,
                    medico_id=m.id,
                ))
        mitades = mitades_por_medico[m.id]
        avisos += avisos_carga(m.id, m.nombre, "turnos", sum(mitades.values()), m.carga)
        for t, rango in m.carga_por_turno.items():
            unidad = "mañanas" if t is Turno.MANANA else "tardes"
            avisos += avisos_carga(m.id, m.nombre, unidad, mitades[t], rango)
    if roles is not None:
        avisos += _validar_roles(problema, asignaciones, roles)
    if problema.todos_trabajan:
        avisos += _validar_todos_trabajan(problema, asignaciones)
    avisos += _validar_rotaciones(problema, turnos_por_medico)
    return avisos


def _validar_rotaciones(problema: Problema, turnos_por_medico) -> list[Aviso]:
    """Dos médicos del mismo turno rotativo en ese turno a la vez."""
    nombres = {m.id: m.nombre for m in problema.medicos}
    avisos = []
    for rot in problema.rotaciones:
        for dia in problema.dias:
            for t in Turno:
                titular = rot.titular(dia, t)
                if titular is None or (dia, t) not in turnos_por_medico[titular]:
                    continue
                for otro in rot.medicos:
                    if otro != titular and (dia, t) in turnos_por_medico[otro]:
                        avisos.append(Aviso(
                            TipoAviso.INCUMPLIMIENTO,
                            f"{nombres.get(otro, f'Médico {otro}')} coincide con {nombres.get(titular, f'Médico {titular}')} "
                            f"en el turno rotativo «{rot.nombre}» el {fmt_fecha(dia)} {fmt_turno(t)}.",
                            fecha=dia,
                            medico_id=otro,
                        ))
    return avisos


def _validar_todos_trabajan(problema: Problema, asignaciones: list[Asignacion]) -> list[Aviso]:
    """Médicos sin ningún turno un día en que podían trabajar."""
    trabaja = {(a.medico_id, a.fecha) for a in asignaciones}
    avisos = []
    for m in problema.medicos:
        for dia in problema.dias:
            if (m.id, dia) in trabaja:
                continue
            posible = any(
                not m.ausente(dia, t)
                and m.eleg(dia, t) is not Elegibilidad.NO_DISPONIBLE
                and (m.id, dia, t) not in problema.vetadas
                for t in Turno
            )
            if posible:
                avisos.append(aviso_sin_turno(dia, m.id, m.nombre))
    return avisos


def _validar_roles(problema: Problema, asignaciones: list[Asignacion], roles) -> list[Aviso]:
    nombres = {m.id: m.nombre for m in problema.medicos}
    tarde = defaultdict(set)
    for a in asignaciones:
        if a.mitad.turno is Turno.TARDE:
            tarde[a.medico_id, a.fecha].add(a.mitad)
    avisos = []
    for dia in problema.dias_con_roles():
        for rol in Rol:
            m_id = roles.get((dia, rol))
            if m_id is None:
                avisos.append(aviso_rol_sin_cubrir(dia, rol))
            elif tarde[m_id, dia] != set(Turno.TARDE.mitades):
                avisos.append(Aviso(
                    TipoAviso.INCUMPLIMIENTO,
                    f"{nombres.get(m_id, f'Médico {m_id}')} hace {rol.nombre} el {fmt_fecha(dia)} "
                    "pero no tiene la tarde completa.",
                    fecha=dia,
                    medico_id=m_id,
                ))
        urg, dom = roles.get((dia, Rol.URGENCIAS)), roles.get((dia, Rol.DOMICILIOS))
        if urg is not None and urg == dom:
            avisos.append(Aviso(
                TipoAviso.INCUMPLIMIENTO,
                f"{nombres.get(urg, f'Médico {urg}')} hace urgencias y domicilios a la vez el {fmt_fecha(dia)}.",
                fecha=dia,
                medico_id=urg,
            ))
    return avisos


def _por_jornada(medico, fecha: date, turno: Turno) -> bool:
    """El turno forma parte de una jornada especial definida en las reglas del médico."""
    jornada = medico.jornadas.get(fecha.weekday())
    return jornada is not None and any(h.turno is turno for h in jornada.mitades)
