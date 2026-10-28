"""Calendario del mes: generar, cambios manuales, deshacer y publicar (especificaciones, 7)."""

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from turnos.api import esquemas as e
from turnos.api.dependencias import SesionBD, VersionMes
from turnos.datos.tablas import HorarioTurno, Periodo
from turnos.dominio.modelos import Rol, Turno
from turnos.motor.entrada import tardes_disponibles
from turnos.exportar.xlsx import exportar_roles_xlsx, exportar_xlsx
from turnos.motor.modelo_cpsat import SinAlternativa
from turnos.servicios import periodos as s

router = APIRouter(prefix="/api/periodos/{anio}/{mes}", tags=["calendario"])
router_meses = APIRouter(prefix="/api/periodos", tags=["calendario"])


@router_meses.get("/publicados", response_model=list[e.MesPublicado])
def publicados(sesion: SesionBD):
    """Meses publicados, del más reciente al más antiguo (los que pueden ver los médicos)."""
    meses = sesion.scalars(
        select(Periodo).where(Periodo.publicado_en.is_not(None)).order_by(Periodo.anio.desc(), Periodo.mes.desc())
    )
    return [{"anio": p.anio, "mes": p.mes, "publicado_en": p.publicado_en} for p in meses]


def _calendario(sesion, anio: int, mes: int) -> e.Calendario:
    try:
        cal = s.leer_calendario(sesion, anio, mes)
    except s.CambioNoValido as error:
        raise HTTPException(422, str(error))
    datos, periodo = cal.datos, cal.datos.periodo
    estado = "SIN_GENERAR" if periodo is None or not (cal.asignaciones or cal.vetos) else "BORRADOR"
    if periodo is not None and periodo.publicado:
        estado = "PUBLICADO"
    medicos = []
    for mm in datos.medicos:
        asignado = cal.carga.get(mm.medico.id)
        medicos.append(e.MedicoCalendario(
            id=mm.medico.id,
            nombre=mm.medico.nombre,
            codigo=mm.medico.codigo,
            activo=mm.medico.activo,
            color=mm.medico.color,
            con_carga=mm.rango is not None,
            minimo=mm.rango.final.minimo if mm.rango else None,
            maximo=mm.rango.final.maximo if mm.rango else None,
            minimo_calculado=mm.rango.calculado.minimo if mm.rango else None,
            maximo_calculado=mm.rango.calculado.maximo if mm.rango else None,
            carga_manual=mm.rango.manual if mm.rango else False,
            asignado=sum(asignado.values()) if asignado else 0,
            asignado_manana=asignado[Turno.MANANA] if asignado else 0,
            asignado_tarde=asignado[Turno.TARDE] if asignado else 0,
            urgencias=cal.veces_rol.get(mm.medico.id, {}).get(Rol.URGENCIAS, 0),
            domicilios=cal.veces_rol.get(mm.medico.id, {}).get(Rol.DOMICILIOS, 0),
            tardes_disponibles=tardes_disponibles(mm.reglas, datos.problema.dias) if mm.reglas else 0,
            habituales=[
                e.HuecoMes(fecha=f, turno=t) for f, t in sorted(mm.habituales, key=lambda i: (i[0], i[1].value))
            ],
            no_elegibles=[
                e.NoElegible(fecha=f, turno=t, motivo=motivo)
                for (f, t), motivo in sorted(mm.no_elegibles.items(), key=lambda i: (i[0][0], i[0][1].value))
            ],
        ))
    return e.Calendario(
        anio=anio,
        mes=mes,
        estado=estado,
        publicado_en=periodo.publicado_en if periodo else None,
        version=periodo.version if periodo else 0,
        carga_por_rangos=not datos.por_presencia,
        dias=[e.Dia(fecha=d, festivo=datos.festivos.get(d)) for d in datos.dias_semana],
        cobertura=[
            e.CoberturaDia(fecha=d, mitad=h, minimo=c.minimo, maximo=c.maximo)
            for (d, h), c in sorted(datos.problema.cobertura.items(), key=lambda i: (i[0][0], i[0][1].value))
        ],
        medicos=medicos,
        asignaciones=cal.asignaciones,
        vetos=cal.vetos,
        roles=cal.roles,
        avisos=[e.AvisoCalendario(**a.__dict__) for a in cal.avisos],
    )


def _ejecutar(sesion, anio: int, mes: int, version: int | None, accion):
    """Ejecuta un cambio del mes: comprueba que nadie lo ha cambiado desde la versión
    que conoce el cliente (si la envía) y sube la versión."""
    periodo = s.obtener_periodo(sesion, anio, mes)
    actual = periodo.version if periodo else 0
    if version is not None and version != actual:
        raise HTTPException(
            409, "Otro usuario ha cambiado el calendario de este mes; se muestra la versión actual.",
            headers={"X-Version-Mes": str(actual)},
        )
    try:
        accion()
    except s.PeriodoPublicado as error:
        raise HTTPException(409, str(error))
    except SinAlternativa as error:
        raise HTTPException(409, str(error))
    except s.CambioNoValido as error:
        raise HTTPException(422, str(error))
    periodo = s.obtener_periodo(sesion, anio, mes, crear=True)
    periodo.version = actual + 1
    sesion.flush()


@router.get("", response_model=e.Calendario)
def obtener(anio: int, mes: int, sesion: SesionBD):
    return _calendario(sesion, anio, mes)


@router.post("/generar", response_model=e.Calendario)
def generar(anio: int, mes: int, datos: e.Generar, sesion: SesionBD, version: VersionMes = None):
    _ejecutar(sesion, anio, mes, version, lambda: s.generar_mes(sesion, anio, mes, alternativa=datos.alternativa))
    return _calendario(sesion, anio, mes)


@router.post("/cambios", response_model=e.Calendario)
def cambios(anio: int, mes: int, datos: list[e.Cambio], sesion: SesionBD, version: VersionMes = None):
    lista = [
        s.FijarDia(c.medico_id, c.fecha, frozenset(c.mitades)) if c.mitades is not None
        else s.AsignarRol(c.medico_id, c.fecha, c.rol) if c.rol is not None
        else s.Bloquear(c.medico_id, c.fecha, c.bloqueada)
        for c in datos
    ]
    _ejecutar(sesion, anio, mes, version, lambda: s.aplicar_cambios(sesion, anio, mes, lista))
    return _calendario(sesion, anio, mes)


@router.post("/liberar", response_model=e.Calendario)
def liberar(anio: int, mes: int, datos: e.Liberar, sesion: SesionBD, version: VersionMes = None):
    """«Volver a automático»: desbloquea y retira vetos del turno, el día o el mes."""
    _ejecutar(sesion, anio, mes, version, lambda: s.liberar(sesion, anio, mes, datos.fecha, datos.turno))
    return _calendario(sesion, anio, mes)


@router.put("/manual", response_model=e.Calendario)
def restaurar(anio: int, mes: int, datos: e.EstadoManual, sesion: SesionBD, version: VersionMes = None):
    """Sustituye asignaciones y vetos por los indicados (deshacer / rehacer)."""
    estado = s.EstadoManual(
        asignaciones=[(a.medico_id, a.fecha, a.mitad, a.origen, a.bloqueada) for a in datos.asignaciones],
        vetos=[(v.medico_id, v.fecha, v.turno) for v in datos.vetos],
        roles=[(r.fecha, r.rol, r.medico_id, r.manual) for r in datos.roles],
    )
    _ejecutar(sesion, anio, mes, version, lambda: s.restaurar(sesion, anio, mes, estado))
    return _calendario(sesion, anio, mes)


@router.put("/carga/{medico_id}", response_model=e.Calendario)
def carga_manual(anio: int, mes: int, medico_id: int, datos: e.CargaManual, sesion: SesionBD, version: VersionMes = None):
    _ejecutar(sesion, anio, mes, version, lambda: s.fijar_carga_manual(sesion, anio, mes, medico_id, datos.minimo, datos.maximo))
    return _calendario(sesion, anio, mes)


@router.post("/publicar", response_model=e.Calendario)
def publicar(anio: int, mes: int, sesion: SesionBD, version: VersionMes = None):
    _ejecutar(sesion, anio, mes, version, lambda: s.publicar(sesion, anio, mes, True))
    return _calendario(sesion, anio, mes)


@router.post("/reabrir", response_model=e.Calendario)
def reabrir(anio: int, mes: int, sesion: SesionBD, version: VersionMes = None):
    _ejecutar(sesion, anio, mes, version, lambda: s.publicar(sesion, anio, mes, False))
    return _calendario(sesion, anio, mes)


@router.get(
    "/urgencias-domicilios.xlsx",
    response_class=Response,
    responses={200: {"content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}}},
)
def exportar_roles(anio: int, mes: int, sesion: SesionBD):
    """Urgencias y domicilios del mes en XLSX: quién hace cada papel cada día y cuántas
    veces cada médico."""
    try:
        cal = s.leer_calendario(sesion, anio, mes)
    except s.CambioNoValido as error:
        raise HTTPException(422, str(error))
    return Response(
        exportar_roles_xlsx(cal),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="urgencias-domicilios-{anio}-{mes:02d}.xlsx"'},
    )


@router.get(
    "/exportar.xlsx",
    response_class=Response,
    responses={200: {"content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}}},
)
def exportar(anio: int, mes: int, sesion: SesionBD):
    """Calendario del mes en XLSX (hojas Calendario, Por médico y Resumen)."""
    try:
        cal = s.leer_calendario(sesion, anio, mes)
    except s.CambioNoValido as error:
        raise HTTPException(422, str(error))
    horarios = {
        h.turno: f"{h.inicio:%H:%M}–{h.fin:%H:%M}" for h in sesion.scalars(select(HorarioTurno))
    }
    for turno in Turno:
        horarios.setdefault(turno, "")
    return Response(
        exportar_xlsx(cal, horarios),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="turnos-{anio}-{mes:02d}.xlsx"'},
    )
