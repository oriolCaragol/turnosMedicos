"""Calendario de un mes: generación, cambios manuales y publicación.

Une la base de datos con el motor (diseño, 6) y la validación de cambios
manuales (especificaciones, 7).
"""

import calendar
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from turnos.datos.tablas import (
    AsignacionPeriodo,
    AusenciaMedico,
    AvisoPeriodo,
    CargaAjustada,
    CoberturaFecha,
    CoberturaSemanal,
    Festivo,
    Medico,
    Periodo,
    RolTarde,
    Veto,
)
from turnos.dominio.calendario import dias_laborables
from turnos.dominio.carga import ajustar_rango
from turnos.dominio.modelos import (
    Asignacion,
    Ausencia,
    Elegibilidad,
    Mitad,
    OrigenAsignacion,
    RangoCarga,
    Rol,
    Turno,
)
from turnos.motor.entrada import Cobertura, Problema, ReglasMedico
from turnos.motor.modelo_cpsat import Parametros, generar, objetivos_equidad
from turnos.motor.resultado import Aviso, TipoAviso
from turnos.motor.validacion import validar
from turnos.servicios.ajustes import leer_ajustes
from turnos.servicios.reglas import leer_reglas
from turnos.servicios.rotaciones import para_el_motor


class PeriodoPublicado(Exception):
    """El mes está publicado: hay que reabrirlo para cambiarlo."""


class CambioNoValido(ValueError):
    pass


# --- Datos del mes ------------------------------------------------------------------


@dataclass
class RangoMes:
    """Rango de carga de un médico en el mes, en medios turnos."""

    calculado: RangoCarga  # tras el ajuste proporcional por ausencias
    final: RangoCarga  # con la sobrescritura manual, si la hay
    manual: bool


@dataclass
class MedicoMes:
    medico: Medico
    reglas: ReglasMedico | None  # None si no tiene carga definida para el mes
    rango: RangoMes | None
    no_elegibles: dict[tuple[date, Turno], str] = field(default_factory=dict)  # motivo
    habituales: set[tuple[date, Turno]] = field(default_factory=set)  # turno habitual (5.1)


@dataclass
class DatosMes:
    anio: int
    mes: int
    periodo: Periodo | None
    dias_semana: list[date]  # todos los días de lunes a viernes del mes
    festivos: dict[date, str]
    problema: Problema
    medicos: list[MedicoMes]
    por_presencia: bool = False  # modo de carga «según la presencia»: sin rangos que mostrar


def limites_mes(anio: int, mes: int) -> tuple[date, date]:
    if not 1 <= mes <= 12 or not 2000 <= anio <= 2100:
        raise CambioNoValido("Mes no válido")
    return date(anio, mes, 1), date(anio, mes, calendar.monthrange(anio, mes)[1])


def obtener_periodo(sesion: Session, anio: int, mes: int, crear: bool = False) -> Periodo | None:
    limites_mes(anio, mes)  # valida el mes
    periodo = sesion.scalar(select(Periodo).where(Periodo.anio == anio, Periodo.mes == mes))
    if periodo is None and crear:
        periodo = Periodo(anio=anio, mes=mes)
        sesion.add(periodo)
        sesion.flush()
    return periodo


def _cobertura(sesion: Session, dias: list[date]) -> dict[tuple[date, Mitad], Cobertura]:
    semanal = {(c.dia_semana, c.mitad): c for c in sesion.scalars(select(CoberturaSemanal))}
    por_fecha = {
        (c.fecha, c.mitad): c
        for c in sesion.scalars(select(CoberturaFecha).where(CoberturaFecha.fecha.in_(dias)))
    }
    cobertura = {}
    for dia in dias:
        for h in Mitad:
            fila = por_fecha.get((dia, h)) or semanal.get((dia.weekday(), h))
            cobertura[dia, h] = Cobertura(fila.minimo, fila.maximo) if fila else Cobertura(0, 0)
    return cobertura


def _saldo(sesion: Session, medico_id: int, anio: int, mes: int) -> int:
    """Carga real − objetivo acumulada en los meses publicados anteriores (medios turnos)."""
    saldo = 0
    filas = sesion.execute(
        select(Periodo.id, CargaAjustada.objetivo)
        .join(CargaAjustada, CargaAjustada.periodo_id == Periodo.id)
        .where(
            Periodo.publicado_en.is_not(None),
            (Periodo.anio * 12 + Periodo.mes) < anio * 12 + mes,
            CargaAjustada.medico_id == medico_id,
            CargaAjustada.turno.is_(None),
            CargaAjustada.objetivo.is_not(None),
        )
    )
    for periodo_id, objetivo in filas:
        real = len(sesion.scalars(select(AsignacionPeriodo.id).where(
            AsignacionPeriodo.periodo_id == periodo_id, AsignacionPeriodo.medico_id == medico_id
        )).all())
        saldo += real - objetivo
    return saldo


def _roles(sesion: Session, periodo: Periodo | None) -> list[RolTarde]:
    if periodo is None:
        return []
    return list(sesion.scalars(
        select(RolTarde).where(RolTarde.periodo_id == periodo.id).order_by(RolTarde.fecha, RolTarde.rol)
    ))


def _tarde_completa(sesion: Session, periodo: Periodo, medico_id: int, fecha: date) -> bool:
    mitades = set(sesion.scalars(select(AsignacionPeriodo.mitad).where(
        AsignacionPeriodo.periodo_id == periodo.id,
        AsignacionPeriodo.medico_id == medico_id,
        AsignacionPeriodo.fecha == fecha,
    )))
    return set(Turno.TARDE.mitades) <= mitades


def construir(sesion: Session, anio: int, mes: int) -> DatosMes:
    primero, ultimo = limites_mes(anio, mes)
    periodo = obtener_periodo(sesion, anio, mes)
    festivos = {
        f.fecha: f.descripcion
        for f in sesion.scalars(select(Festivo).where(Festivo.fecha.between(primero, ultimo)))
    }
    dias = dias_laborables(anio, mes, festivos)
    dias_semana = dias_laborables(anio, mes, ())
    cota = 4 * len(dias)

    asignaciones = (
        list(sesion.scalars(select(AsignacionPeriodo).where(AsignacionPeriodo.periodo_id == periodo.id)))
        if periodo else []
    )
    vetos = list(sesion.scalars(select(Veto).where(Veto.periodo_id == periodo.id))) if periodo else []
    roles = _roles(sesion, periodo)
    manuales = (
        {(c.medico_id, c.turno): c for c in sesion.scalars(
            select(CargaAjustada).where(CargaAjustada.periodo_id == periodo.id)
        )}
        if periodo else {}
    )

    con_turnos = {a.medico_id for a in asignaciones}
    medicos_bd = sesion.scalars(
        select(Medico).where(Medico.activo | Medico.id.in_(con_turnos)).order_by(Medico.nombre)
    ).all()

    ajustes = leer_ajustes(sesion)
    # Según la presencia: sin rangos de la ficha; cada médico, como mucho los turnos de
    # los días que está (reducido por sus ausencias). El reparto del resto lo hace la
    # equidad, en proporción a ese máximo, y «todos trabajan» asegura un turno al día.
    por_presencia = ajustes.modo_carga == "PRESENCIA"
    medicos: list[MedicoMes] = []
    reglas_motor: list[ReglasMedico] = []
    for med in medicos_bd:
        reglas = leer_reglas(sesion, med.id, primero)
        ausencias = tuple(
            Ausencia(a.desde, a.hasta, a.turno)
            for a in sesion.scalars(select(AusenciaMedico).where(
                AusenciaMedico.medico_id == med.id,
                AusenciaMedico.hasta >= primero,
                AusenciaMedico.desde <= ultimo,
            ))
        )
        no_elegibles = {}
        habituales = set()
        for dia in dias:
            for t in Turno:
                if any(a.cubre(dia, t) for a in ausencias):
                    no_elegibles[dia, t] = "AUSENTE"
                elif reglas.elegibilidad[dia.weekday(), t] is Elegibilidad.NO_DISPONIBLE:
                    no_elegibles[dia, t] = "NO_DISPONIBLE"
                elif reglas.elegibilidad[dia.weekday(), t] is Elegibilidad.HABITUAL:
                    habituales.add((dia, t))

        if not med.activo or (reglas.carga is None and not por_presencia):
            medicos.append(MedicoMes(med, None, None, no_elegibles, habituales))
            continue

        calculado = ajustar_rango(RangoCarga(0, cota) if por_presencia else reglas.carga, dias, ausencias)
        if por_presencia:
            manuales.pop((med.id, None), None)  # los rangos ajustados a mano no cuentan
        fila = manuales.get((med.id, None))
        final = RangoCarga(
            fila.minimo_manual if fila and fila.minimo_manual is not None else calculado.minimo,
            fila.maximo_manual if fila and fila.maximo_manual is not None else calculado.maximo,
        ) if fila else calculado
        if final.maximo < final.minimo:
            final = RangoCarga(final.minimo, final.minimo)
        manual = bool(fila and (fila.minimo_manual is not None or fila.maximo_manual is not None))

        por_turno = {}
        for t, (minimo, maximo) in ({} if por_presencia else reglas.carga_por_turno).items():
            ajustado = ajustar_rango(RangoCarga(minimo, maximo if maximo is not None else minimo), dias, ausencias)
            por_turno[t] = RangoCarga(ajustado.minimo, ajustado.maximo if maximo is not None else cota)

        rm = ReglasMedico(
            id=med.id,
            nombre=med.nombre,
            carga=final,
            elegibilidad=reglas.elegibilidad,
            jornadas=reglas.jornadas,
            carga_por_turno=por_turno,
            ausencias=ausencias,
            preferencias=reglas.preferencias,
            saldo=_saldo(sesion, med.id, anio, mes),
        )
        reglas_motor.append(rm)
        medicos.append(MedicoMes(med, rm, RangoMes(calculado, final, manual), no_elegibles, habituales))

    problema = Problema(
        dias=tuple(dias),
        cobertura=_cobertura(sesion, dias),
        medicos=tuple(reglas_motor),
        bloqueadas=frozenset(
            Asignacion(a.medico_id, a.fecha, a.mitad) for a in asignaciones if a.bloqueada
        ),
        vetadas=frozenset((v.medico_id, v.fecha, v.turno) for v in vetos),
        anterior=frozenset(Asignacion(a.medico_id, a.fecha, a.mitad) for a in asignaciones),
        roles_fijados={(r.fecha, r.rol): r.medico_id for r in roles if r.manual},
        roles_anteriores={(r.fecha, r.rol): r.medico_id for r in roles},
        todos_trabajan=ajustes.todos_trabajan or por_presencia,
        roles_segun_presencia=ajustes.roles_segun_presencia,
        prioridad_roles=None if ajustes.prioridad_roles == "IGUAL" else Rol(ajustes.prioridad_roles),
        rotaciones=para_el_motor(sesion),
    )
    return DatosMes(anio, mes, periodo, dias_semana, festivos, problema, medicos, por_presencia)


# --- Generación ---------------------------------------------------------------------


def _comprobar_editable(periodo: Periodo) -> None:
    if periodo.publicado:
        raise PeriodoPublicado("El mes está publicado; reábrelo para hacer cambios")


# Meses que se están generando ahora mismo (para avisar a otro usuario que lo intente).
GENERANDO: set[tuple[int, int]] = set()


def generar_mes(sesion: Session, anio: int, mes: int, alternativa: bool = False) -> None:
    """Genera (o regenera) el calendario. Respeta lo bloqueado y lo vetado; al
    regenerar cambia lo mínimo, salvo que se pida una alternativa."""
    GENERANDO.add((anio, mes))
    try:
        _generar_mes(sesion, anio, mes, alternativa)
    finally:
        GENERANDO.discard((anio, mes))


def _generar_mes(sesion: Session, anio: int, mes: int, alternativa: bool) -> None:
    periodo = obtener_periodo(sesion, anio, mes, crear=True)
    _comprobar_editable(periodo)
    datos = construir(sesion, anio, mes)
    problema = datos.problema
    parametros = Parametros()
    if alternativa:
        generadas = len(problema.anterior - problema.bloqueadas) // 2
        parametros = Parametros(
            alternativa_de=problema.anterior, cambios_minimos=max(2, generadas // 20)
        )
    resultado = generar(problema, parametros)

    sesion.execute(delete(AsignacionPeriodo).where(AsignacionPeriodo.periodo_id == periodo.id))
    for a, origen in resultado.asignaciones.items():
        sesion.add(AsignacionPeriodo(
            periodo_id=periodo.id, medico_id=a.medico_id, fecha=a.fecha, mitad=a.mitad,
            origen=origen, bloqueada=origen is OrigenAsignacion.MANUAL,
        ))

    sesion.execute(delete(RolTarde).where(RolTarde.periodo_id == periodo.id))
    for (fecha, rol), medico_id in resultado.roles.items():
        sesion.add(RolTarde(
            periodo_id=periodo.id, fecha=fecha, rol=rol, medico_id=medico_id,
            manual=problema.roles_fijados.get((fecha, rol)) == medico_id,
        ))

    # Solo se guardan las causas; los incumplimientos se calculan siempre al vuelo.
    sesion.execute(delete(AvisoPeriodo).where(AvisoPeriodo.periodo_id == periodo.id))
    for aviso in resultado.avisos:
        if aviso.tipo is TipoAviso.CAUSA:
            sesion.add(AvisoPeriodo(
                periodo_id=periodo.id, tipo=aviso.tipo, mensaje=aviso.mensaje,
                fecha=aviso.fecha, medico_id=aviso.medico_id,
            ))

    objetivos = objetivos_equidad(problema, parametros.limite_saldo)
    for mm in datos.medicos:
        if mm.rango is None:
            continue
        fila = sesion.scalar(select(CargaAjustada).where(
            CargaAjustada.periodo_id == periodo.id,
            CargaAjustada.medico_id == mm.medico.id,
            CargaAjustada.turno.is_(None),
        )) or CargaAjustada(periodo_id=periodo.id, medico_id=mm.medico.id, turno=None)
        fila.minimo_calc, fila.maximo_calc = mm.rango.calculado.minimo, mm.rango.calculado.maximo
        fila.objetivo = objetivos[mm.medico.id]
        sesion.add(fila)
    sesion.flush()


# --- Cambios manuales ---------------------------------------------------------------


@dataclass(frozen=True)
class FijarDia:
    """Deja a un médico, en una fecha, exactamente en estas mitades (vacío = nada).

    Todo lo que queda asignado se bloquea; los turnos que pierde se vetan para
    que el generador no los vuelva a poner."""

    medico_id: int
    fecha: date
    mitades: frozenset[Mitad]


@dataclass(frozen=True)
class Bloquear:
    medico_id: int
    fecha: date
    bloqueada: bool


@dataclass(frozen=True)
class AsignarRol:
    """Pone a un médico (que hace la tarde completa) de urgencias o de domicilios.

    Si ya tenía el otro papel ese día, los dos médicos se lo intercambian."""

    medico_id: int
    fecha: date
    rol: Rol


def _asignar_rol(sesion: Session, periodo: Periodo, cambio: AsignarRol) -> None:
    if not _tarde_completa(sesion, periodo, cambio.medico_id, cambio.fecha):
        raise CambioNoValido("Para hacer urgencias o domicilios hay que tener la tarde completa ese día")
    del_dia = {
        r.rol: r for r in sesion.scalars(select(RolTarde).where(
            RolTarde.periodo_id == periodo.id, RolTarde.fecha == cambio.fecha
        ))
    }
    otro = Rol.DOMICILIOS if cambio.rol is Rol.URGENCIAS else Rol.URGENCIAS
    anterior = del_dia.get(cambio.rol)
    if del_dia.get(otro) is not None and del_dia[otro].medico_id == cambio.medico_id:
        # Intercambio: quien tenía este papel pasa al otro (o el otro queda libre).
        if anterior is not None and anterior.medico_id != cambio.medico_id:
            del_dia[otro].medico_id, del_dia[otro].manual = anterior.medico_id, True
        else:
            sesion.delete(del_dia[otro])
    fila = anterior or RolTarde(periodo_id=periodo.id, fecha=cambio.fecha, rol=cambio.rol)
    fila.medico_id, fila.manual = cambio.medico_id, True
    sesion.add(fila)
    # Como todo cambio a mano, su tarde queda bloqueada.
    for a in sesion.scalars(select(AsignacionPeriodo).where(
        AsignacionPeriodo.periodo_id == periodo.id,
        AsignacionPeriodo.medico_id == cambio.medico_id,
        AsignacionPeriodo.fecha == cambio.fecha,
    )):
        if a.mitad.turno is Turno.TARDE:
            a.bloqueada = True
    sesion.flush()


def aplicar_cambios(
    sesion: Session, anio: int, mes: int, cambios: list[FijarDia | Bloquear | AsignarRol],
    *, en_publicado: bool = False,
) -> None:
    """`en_publicado`: también en un mes publicado, sin reabrirlo (solicitudes aprobadas, D-S9)."""
    periodo = obtener_periodo(sesion, anio, mes, crear=True)
    if not en_publicado:
        _comprobar_editable(periodo)
    primero, ultimo = limites_mes(anio, mes)
    for cambio in cambios:
        if not primero <= cambio.fecha <= ultimo:
            raise CambioNoValido(f"La fecha {cambio.fecha} no es de este mes")
        if sesion.get(Medico, cambio.medico_id) is None:
            raise CambioNoValido("Médico no encontrado")
        filas = list(sesion.scalars(select(AsignacionPeriodo).where(
            AsignacionPeriodo.periodo_id == periodo.id,
            AsignacionPeriodo.medico_id == cambio.medico_id,
            AsignacionPeriodo.fecha == cambio.fecha,
        )))
        if isinstance(cambio, AsignarRol):
            _asignar_rol(sesion, periodo, cambio)
            continue
        if isinstance(cambio, Bloquear):
            for fila in filas:
                fila.bloqueada = cambio.bloqueada
                if cambio.bloqueada:
                    fila.origen = OrigenAsignacion.MANUAL
            continue

        antes = {f.mitad.turno for f in filas}
        for fila in filas:
            sesion.delete(fila)
        sesion.flush()
        for h in sorted(cambio.mitades, key=lambda h: h.value):
            sesion.add(AsignacionPeriodo(
                periodo_id=periodo.id, medico_id=cambio.medico_id, fecha=cambio.fecha, mitad=h,
                origen=OrigenAsignacion.MANUAL, bloqueada=True,
            ))
        despues = {h.turno for h in cambio.mitades}
        for t in Turno:
            veto = sesion.scalar(select(Veto).where(
                Veto.periodo_id == periodo.id, Veto.medico_id == cambio.medico_id,
                Veto.fecha == cambio.fecha, Veto.turno == t,
            ))
            if t in antes and t not in despues and veto is None:
                sesion.add(Veto(periodo_id=periodo.id, medico_id=cambio.medico_id, fecha=cambio.fecha, turno=t))
            elif t in despues and veto is not None:
                sesion.delete(veto)
        # Sin la tarde completa no puede seguir con urgencias ni domicilios.
        if not set(Turno.TARDE.mitades) <= set(cambio.mitades):
            sesion.execute(delete(RolTarde).where(
                RolTarde.periodo_id == periodo.id,
                RolTarde.fecha == cambio.fecha,
                RolTarde.medico_id == cambio.medico_id,
            ))
        sesion.flush()


def liberar(sesion: Session, anio: int, mes: int, fecha: date | None = None, turno: Turno | None = None) -> None:
    """Devuelve al generador un turno (o un día, o todo el mes): desbloquea sus
    asignaciones y retira los vetos, de modo que al regenerar se decide de nuevo."""
    periodo = obtener_periodo(sesion, anio, mes, crear=True)
    _comprobar_editable(periodo)
    primero, ultimo = limites_mes(anio, mes)
    if fecha is not None and not primero <= fecha <= ultimo:
        raise CambioNoValido(f"La fecha {fecha} no es de este mes")
    filas = sesion.scalars(select(AsignacionPeriodo).where(AsignacionPeriodo.periodo_id == periodo.id))
    for fila in filas:
        if (fecha is None or fila.fecha == fecha) and (turno is None or fila.mitad.turno is turno):
            fila.bloqueada = False
    vetos = delete(Veto).where(Veto.periodo_id == periodo.id)
    if fecha is not None:
        vetos = vetos.where(Veto.fecha == fecha)
    if turno is not None:
        vetos = vetos.where(Veto.turno == turno)
    sesion.execute(vetos)
    if turno in (None, Turno.TARDE):
        for r in _roles(sesion, periodo):
            if fecha is None or r.fecha == fecha:
                r.manual = False
    sesion.flush()


@dataclass(frozen=True)
class EstadoManual:
    """Foto de las asignaciones y vetos de un mes (para deshacer / rehacer)."""

    asignaciones: list[tuple[int, date, Mitad, OrigenAsignacion, bool]]
    vetos: list[tuple[int, date, Turno]]
    roles: list[tuple[date, Rol, int, bool]] = field(default_factory=list)  # fecha, rol, médico, manual


def restaurar(sesion: Session, anio: int, mes: int, estado: EstadoManual) -> None:
    periodo = obtener_periodo(sesion, anio, mes, crear=True)
    _comprobar_editable(periodo)
    primero, ultimo = limites_mes(anio, mes)
    if any(not primero <= a[1] <= ultimo for a in estado.asignaciones) or any(
        not primero <= v[1] <= ultimo for v in estado.vetos
    ):
        raise CambioNoValido("Hay fechas que no son de este mes")
    sesion.execute(delete(AsignacionPeriodo).where(AsignacionPeriodo.periodo_id == periodo.id))
    sesion.execute(delete(Veto).where(Veto.periodo_id == periodo.id))
    sesion.flush()
    for medico_id, fecha, mitad, origen, bloqueada in set(estado.asignaciones):
        sesion.add(AsignacionPeriodo(
            periodo_id=periodo.id, medico_id=medico_id, fecha=fecha, mitad=mitad,
            origen=origen, bloqueada=bloqueada,
        ))
    for medico_id, fecha, turno in set(estado.vetos):
        sesion.add(Veto(periodo_id=periodo.id, medico_id=medico_id, fecha=fecha, turno=turno))
    sesion.execute(delete(RolTarde).where(RolTarde.periodo_id == periodo.id))
    for fecha, rol, medico_id, manual in {(f, r): (f, r, m, man) for f, r, m, man in estado.roles}.values():
        if primero <= fecha <= ultimo:
            sesion.add(RolTarde(periodo_id=periodo.id, fecha=fecha, rol=rol, medico_id=medico_id, manual=manual))
    sesion.flush()


def fijar_carga_manual(
    sesion: Session, anio: int, mes: int, medico_id: int, minimo: int | None, maximo: int | None
) -> None:
    """Sobrescribe (o, con None, vuelve al calculado) el rango del médico en el mes."""
    periodo = obtener_periodo(sesion, anio, mes, crear=True)
    _comprobar_editable(periodo)
    if minimo is not None and maximo is not None and maximo < minimo:
        raise CambioNoValido("El máximo no puede ser menor que el mínimo")
    datos = construir(sesion, anio, mes)
    mm = next((m for m in datos.medicos if m.medico.id == medico_id and m.rango), None)
    if mm is None:
        raise CambioNoValido("El médico no tiene carga definida para este mes")
    fila = sesion.scalar(select(CargaAjustada).where(
        CargaAjustada.periodo_id == periodo.id,
        CargaAjustada.medico_id == medico_id,
        CargaAjustada.turno.is_(None),
    )) or CargaAjustada(periodo_id=periodo.id, medico_id=medico_id, turno=None)
    fila.minimo_calc, fila.maximo_calc = mm.rango.calculado.minimo, mm.rango.calculado.maximo
    fila.minimo_manual, fila.maximo_manual = minimo, maximo
    sesion.add(fila)
    sesion.flush()


def publicar(sesion: Session, anio: int, mes: int, publicado: bool) -> None:
    periodo = obtener_periodo(sesion, anio, mes, crear=True)
    periodo.publicado_en = datetime.now() if publicado else None
    sesion.flush()


# --- Lectura ------------------------------------------------------------------------


@dataclass
class Calendario:
    datos: DatosMes
    asignaciones: list[AsignacionPeriodo]
    vetos: list[Veto]
    avisos: list[Aviso]
    carga: dict[int, Counter]  # medios turnos asignados por médico y turno
    roles: list[RolTarde] = field(default_factory=list)
    veces_rol: dict[int, Counter] = field(default_factory=dict)  # urgencias/domicilios por médico


def leer_calendario(sesion: Session, anio: int, mes: int) -> Calendario:
    datos = construir(sesion, anio, mes)
    periodo = datos.periodo
    asignaciones = (
        list(sesion.scalars(
            select(AsignacionPeriodo)
            .where(AsignacionPeriodo.periodo_id == periodo.id)
            .order_by(AsignacionPeriodo.fecha, AsignacionPeriodo.mitad, AsignacionPeriodo.medico_id)
        ))
        if periodo else []
    )
    vetos = list(sesion.scalars(select(Veto).where(Veto.periodo_id == periodo.id))) if periodo else []
    causas = (
        [Aviso(a.tipo, a.mensaje, a.fecha, a.medico_id) for a in sesion.scalars(
            select(AvisoPeriodo).where(AvisoPeriodo.periodo_id == periodo.id).order_by(AvisoPeriodo.id)
        )]
        if periodo else []
    )
    roles = _roles(sesion, periodo)
    incumplimientos = (
        validar(
            datos.problema,
            [Asignacion(a.medico_id, a.fecha, a.mitad) for a in asignaciones],
            {(r.fecha, r.rol): r.medico_id for r in roles},
        )
        if asignaciones else []
    )
    carga: dict[int, Counter] = defaultdict(Counter)
    for a in asignaciones:
        carga[a.medico_id][a.mitad.turno] += 1
    veces_rol: dict[int, Counter] = defaultdict(Counter)
    for r in roles:
        veces_rol[r.medico_id][r.rol] += 1
    return Calendario(datos, asignaciones, vetos, causas + incumplimientos, carga, roles, veces_rol)
