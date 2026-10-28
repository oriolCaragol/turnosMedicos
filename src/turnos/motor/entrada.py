"""Entrada del motor y preprocesado (diseño, 6.1 y 6.2).

El preprocesado separa lo que ya está decidido (asignaciones fijadas) de lo
que debe decidir el motor (candidatos: turnos completos que puede asignar).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta

from turnos.dominio.modelos import (
    Asignacion,
    Ausencia,
    Elegibilidad,
    Mitad,
    OrigenAsignacion,
    Preferencia,
    RangoCarga,
    Rol,
    TipoJornada,
    Turno,
)

# Hueco semanal: (día de la semana 0 = lunes … 4 = viernes, turno).
HuecoSemanal = tuple[int, Turno]


@dataclass(frozen=True)
class Cobertura:
    """Médicos necesarios en una mitad de turno (especificaciones, 4.4)."""

    minimo: int
    maximo: int

    def __post_init__(self) -> None:
        if self.minimo < 0 or self.maximo < self.minimo:
            raise ValueError(f"Cobertura no válida: {self.minimo}–{self.maximo}")


@dataclass(frozen=True)
class ReglasMedico:
    """Reglas de un médico ya resueltas para el mes que se planifica.

    `carga` y `carga_por_turno` son los rangos ya ajustados por ausencias.
    `saldo` es lo que el médico acumula de más (+) o de menos (−) respecto a
    su objetivo en los meses publicados, en medios turnos.
    Los huecos que no aparecen en `elegibilidad` se consideran Disponibles.
    """

    id: int
    nombre: str
    carga: RangoCarga
    elegibilidad: Mapping[HuecoSemanal, Elegibilidad] = field(default_factory=dict)
    jornadas: Mapping[int, TipoJornada] = field(default_factory=dict)
    carga_por_turno: Mapping[Turno, RangoCarga] = field(default_factory=dict)
    ausencias: tuple[Ausencia, ...] = ()
    preferencias: Mapping[HuecoSemanal, Preferencia] = field(default_factory=dict)
    saldo: int = 0

    def eleg(self, fecha: date, turno: Turno) -> Elegibilidad:
        return self.elegibilidad.get((fecha.weekday(), turno), Elegibilidad.DISPONIBLE)

    def ausente(self, fecha: date, turno: Turno) -> bool:
        return any(a.cubre(fecha, turno) for a in self.ausencias)


@dataclass(frozen=True)
class Rotacion:
    """Turno rotativo (especificaciones, 5.8): unos turnos de la semana que un grupo
    de médicos hace por turnos, una semana cada uno, sin coincidir.

    La semana de `desde` le toca al primero de `medicos`, la siguiente al segundo, y
    así sucesivamente; la cuenta sigue de un mes a otro."""

    medicos: tuple[int, ...]
    huecos: frozenset[HuecoSemanal]
    desde: date
    nombre: str = ""

    @property
    def lunes(self) -> date:
        return self.desde - timedelta(days=self.desde.weekday())

    def titular(self, fecha: date, turno: Turno) -> int | None:
        """Médico al que le toca ese turno esa semana (None si no es de la rotación)."""
        if (fecha.weekday(), turno) not in self.huecos or len(self.medicos) < 2 or fecha < self.lunes:
            return None
        return self.medicos[((fecha - self.lunes).days // 7) % len(self.medicos)]


@dataclass(frozen=True)
class Problema:
    """Todo lo que necesita el motor para generar un mes.

    - `dias`: días laborables del periodo (sin festivos).
    - `cobertura`: para cada día y mitad; si falta, se entiende 0–0.
    - `bloqueadas`: asignaciones puestas a mano que deben mantenerse.
    - `vetadas`: (médico, fecha, turno) que el planificador ha quitado a mano
      y no deben volver a asignarse.
    - `anterior`: calendario previo del periodo, para cambiar lo mínimo al
      regenerar.
    - `roles_fijados`: urgencias/domicilios elegidos a mano (fecha, rol) → médico.
    - `roles_anteriores`: los del calendario previo, para cambiar lo mínimo.
    - `todos_trabajan`: cada médico trabaja todos los días laborables en que
      puede (no está ausente y tiene algún turno posible).
    - `rotaciones`: turnos rotativos entre grupos de médicos.
    - `roles_segun_presencia`: urgencias y domicilios en proporción a las tardes
      del mes en que cada médico no está ausente (si no, por igual).
    - `prioridad_roles`: el papel cuyo reparto se iguala primero. Si no se puede
      repartir todo por igual, la desigualdad va al otro (por defecto, las urgencias
      iguales y la diferencia en domicilios). None: los dos a la vez.
    """

    dias: tuple[date, ...]
    cobertura: Mapping[tuple[date, Mitad], Cobertura]
    medicos: tuple[ReglasMedico, ...]
    bloqueadas: frozenset[Asignacion] = frozenset()
    vetadas: frozenset[tuple[int, date, Turno]] = frozenset()
    anterior: frozenset[Asignacion] = frozenset()
    roles_fijados: Mapping[tuple[date, Rol], int] = field(default_factory=dict)
    roles_anteriores: Mapping[tuple[date, Rol], int] = field(default_factory=dict)
    todos_trabajan: bool = False
    rotaciones: tuple[Rotacion, ...] = ()
    roles_segun_presencia: bool = False
    prioridad_roles: Rol | None = Rol.URGENCIAS

    def cob(self, fecha: date, mitad: Mitad) -> Cobertura:
        return self.cobertura.get((fecha, mitad), Cobertura(0, 0))

    def requiere_roles(self, fecha: date) -> bool:
        """Urgencias y domicilios hacen falta las tardes que necesitan al menos dos médicos
        (uno para cada papel); con menos, el reparto no es posible."""
        return all(self.cob(fecha, h).minimo >= 2 for h in Turno.TARDE.mitades)

    def dias_con_roles(self) -> list[date]:
        return [d for d in self.dias if self.requiere_roles(d)]


def dias_obligatorios(problema: "Problema", prep: "Preparado") -> dict[int, set[date]]:
    """Con `todos_trabajan`: días en que cada médico ha de tener algún turno.

    Son los días laborables en que ya tiene algo fijado o tiene algún turno posible
    (no ausente, no marcado «—» y no quitado a mano); los demás quedan exentos."""
    if not problema.todos_trabajan:
        return {}
    con_algo = {(a.medico_id, a.fecha) for a in prep.fijadas} | {(m, d) for m, d, _ in prep.candidatos}
    return {
        med.id: {d for d in problema.dias if (med.id, d) in con_algo}
        for med in problema.medicos
    }


def tardes_disponibles(medico: ReglasMedico, dias) -> int:
    """Tardes del mes en que el médico podría trabajar (marcadas en su tarjeta y sin ausencia).

    El reparto de urgencias y domicilios es proporcional a este número."""
    return sum(
        1 for d in dias
        if medico.eleg(d, Turno.TARDE) is not Elegibilidad.NO_DISPONIBLE and not medico.ausente(d, Turno.TARDE)
    )


def presencia(medico: ReglasMedico, dias) -> int:
    """Tardes del mes en que el médico no está ausente, tenga o no turno ese día:
    mide su presencia en el mes (sus reglas no cuentan, solo las ausencias)."""
    return sum(1 for d in dias if not medico.ausente(d, Turno.TARDE))


@dataclass(frozen=True)
class Preparado:
    """Resultado del preprocesado.

    - `fijadas`: asignaciones ya decididas, con su origen.
    - `candidatos`: (médico, fecha, turno) que el motor puede asignar como
      turno completo.
    """

    fijadas: Mapping[Asignacion, OrigenAsignacion]
    candidatos: frozenset[tuple[int, date, Turno]]


def preparar(problema: Problema) -> Preparado:
    medicos = {m.id: m for m in problema.medicos}
    fijadas: dict[Asignacion, OrigenAsignacion] = {}

    # Asignaciones bloqueadas: se respetan siempre, aunque incumplan reglas.
    for a in problema.bloqueadas:
        fijadas[a] = OrigenAsignacion.MANUAL
    dias_bloqueados = {(a.medico_id, a.fecha) for a in problema.bloqueadas}

    # Reglas del médico: jornada especial o huecos Fijo, salvo ausencia o veto.
    for m in problema.medicos:
        for dia in problema.dias:
            if (m.id, dia) in dias_bloqueados:
                continue
            jornada = m.jornadas.get(dia.weekday())
            if jornada is not None:
                mitades = jornada.mitades
            else:
                mitades = frozenset(
                    h for t in Turno if m.eleg(dia, t) is Elegibilidad.FIJO for h in t.mitades
                )
            for h in mitades:
                if not m.ausente(dia, h.turno) and (m.id, dia, h.turno) not in problema.vetadas:
                    fijadas[Asignacion(m.id, dia, h)] = OrigenAsignacion.FIJO

    # Turnos rotativos: a quien le toca esa semana lo tiene fijo, y los demás del grupo
    # no pueden coincidir con él. Si quien le toca no puede (ausencia, veto…), el turno
    # queda libre para el resto, incluidos los demás del grupo.
    excluidos: set[tuple[int, date, Turno]] = set()
    for rot in problema.rotaciones:
        for dia in problema.dias:
            for t in Turno:
                titular = rot.titular(dia, t)
                m = medicos.get(titular) if titular is not None else None
                if m is None or (m.id, dia) in dias_bloqueados or m.ausente(dia, t):
                    continue
                if (m.id, dia, t) in problema.vetadas:
                    continue
                for h in t.mitades:
                    fijadas[Asignacion(m.id, dia, h)] = OrigenAsignacion.FIJO
                for otro in rot.medicos:
                    if otro == m.id:
                        continue
                    excluidos.add((otro, dia, t))
                    # La rotación manda sobre el «Fijo» de la tarjeta de los demás en ese turno.
                    for h in t.mitades:
                        if fijadas.get(Asignacion(otro, dia, h)) is OrigenAsignacion.FIJO:
                            del fijadas[Asignacion(otro, dia, h)]

    # Candidatos: solo días sin nada fijado (el motor solo crea jornadas de 1 turno).
    dias_fijados = {(a.medico_id, a.fecha) for a in fijadas}
    candidatos = frozenset(
        (m.id, dia, t)
        for m in medicos.values()
        for dia in problema.dias
        if (m.id, dia) not in dias_fijados
        for t in Turno
        if m.eleg(dia, t).asignable
        and not m.ausente(dia, t)
        and (m.id, dia, t) not in problema.vetadas
        and (m.id, dia, t) not in excluidos
    )
    return Preparado(fijadas=fijadas, candidatos=candidatos)
