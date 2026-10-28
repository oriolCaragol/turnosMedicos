"""Solicitudes de los médicos (diseño del modo servidor, 6.4).

Los médicos no cambian nada: **proponen**, y el planificador o el administrador
deciden. Tres tipos, cada uno con su `propuesta` (JSON):

- DISPONIBILIDAD: `{"desde": "2026-12-01", "elegibilidad": [{dia_semana, turno, valor}…]}`.
  Al aprobarla se guarda una versión nueva de sus reglas desde ese mes; la carga y
  las jornadas siguen siendo las que decidió el planificador (D-S11).
- AUSENCIA: `{"accion": "CREAR"|"MODIFICAR"|"ANULAR", "ausencia_id", "desde", "hasta", "turno"}`.
- CALENDARIO, sobre un turno suyo de un mes **publicado**: `{"cambio": "NO_PUEDO"|
  "OTRA_MITAD"|"INTERCAMBIO", "fecha", "turno", "fecha_companero", "turno_companero"}`.
  Se aplica como cambio manual (bloqueado) sin reabrir el mes (D-S9). En un
  intercambio, el otro médico acepta antes de que llegue al planificador (D-S8).

Para ver qué pasaría al aprobar (`efectos`), se aplica dentro de un punto de
guardado, se leen los avisos de los meses afectados y se deshace.
"""

import json
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from turnos.datos.tablas import AsignacionPeriodo, AusenciaMedico, Medico, Periodo, Solicitud, Usuario
from turnos.dominio.modelos import Elegibilidad, Mitad, Turno
from turnos.exportar.xlsx import nombre_mes
from turnos.servicios import periodos as p
from turnos.servicios.reglas import guardar_reglas, leer_reglas

TIPOS = ("DISPONIBILIDAD", "AUSENCIA", "CALENDARIO")
ABIERTAS = ("ESPERA_COMPANERO", "PENDIENTE")
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes")
DIAS_CORTOS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
TURNO = {Turno.MANANA: "mañana", Turno.TARDE: "tarde"}
ELEGIBILIDAD = {
    Elegibilidad.DISPONIBLE: "Disponible", Elegibilidad.HABITUAL: "Habitual",
    Elegibilidad.FIJO: "Fijo", Elegibilidad.NO_DISPONIBLE: "No disponible",
}


class SolicitudNoValida(ValueError):
    """El mensaje es para mostrarlo tal cual."""


def _fecha(texto) -> date:
    return texto if isinstance(texto, date) else date.fromisoformat(texto)


def _corta(fecha: date) -> str:
    return f"{DIAS_CORTOS[fecha.weekday()]} {fecha.day}/{fecha.month}"


def _mitades(sesion: Session, medico_id: int, fecha: date) -> set[Mitad]:
    periodo = p.obtener_periodo(sesion, fecha.year, fecha.month)
    if periodo is None:
        return set()
    return set(sesion.scalars(select(AsignacionPeriodo.mitad).where(
        AsignacionPeriodo.periodo_id == periodo.id, AsignacionPeriodo.medico_id == medico_id,
        AsignacionPeriodo.fecha == fecha,
    )))


def _publicado(sesion: Session, fecha: date) -> bool:
    periodo = p.obtener_periodo(sesion, fecha.year, fecha.month)
    return periodo is not None and periodo.publicado


# --- Crear --------------------------------------------------------------------------


def crear(sesion: Session, usuario: Usuario, tipo: str, propuesta: dict, comentario: str = "") -> Solicitud:
    """Valida la propuesta y la guarda (en espera del compañero si es un intercambio)."""
    if usuario.medico_id is None:
        raise SolicitudNoValida("Solo los médicos pueden proponer cambios")
    if tipo not in TIPOS:
        raise SolicitudNoValida(f"Tipo de solicitud desconocido: {tipo}")
    medico_id = usuario.medico_id
    companero_id = None
    propuesta = dict(propuesta)
    if tipo == "DISPONIBILIDAD":
        desde = _fecha(propuesta["desde"])
        hoy = date.today()
        if desde.day != 1 or (desde.year, desde.month) < (hoy.year, hoy.month):
            raise SolicitudNoValida("La disponibilidad se propone desde el primer día de este mes o de uno siguiente")
        if len(propuesta.get("elegibilidad", [])) != 10:
            raise SolicitudNoValida("Falta la cuadrícula completa de la semana")
    elif tipo == "AUSENCIA":
        accion = propuesta.get("accion")
        if accion in ("MODIFICAR", "ANULAR"):
            ausencia = sesion.get(AusenciaMedico, propuesta.get("ausencia_id") or 0)
            if ausencia is None or ausencia.medico_id != medico_id:
                raise SolicitudNoValida("Esa ausencia no es tuya o ya no existe")
        elif accion != "CREAR":
            raise SolicitudNoValida("Acción de ausencia desconocida")
        if accion in ("CREAR", "MODIFICAR"):
            if _fecha(propuesta["hasta"]) < _fecha(propuesta["desde"]):
                raise SolicitudNoValida("La fecha final no puede ser anterior a la inicial")
    else:
        fecha, turno = _fecha(propuesta["fecha"]), Turno(propuesta["turno"])
        if not _publicado(sesion, fecha):
            raise SolicitudNoValida("Solo se pueden proponer cambios en meses publicados")
        if not set(turno.mitades) & _mitades(sesion, medico_id, fecha):
            raise SolicitudNoValida(f"No tienes la {TURNO[turno]} del {_corta(fecha)}")
        if propuesta.get("cambio") == "INTERCAMBIO":
            companero_id = propuesta.get("companero_id")
            otra_fecha, otro_turno = _fecha(propuesta["fecha_companero"]), Turno(propuesta["turno_companero"])
            if companero_id == medico_id or sesion.get(Medico, companero_id or 0) is None:
                raise SolicitudNoValida("Elige con qué compañero quieres intercambiar")
            if (otra_fecha.year, otra_fecha.month) != (fecha.year, fecha.month):
                raise SolicitudNoValida("El intercambio debe ser dentro del mismo mes")
            if not set(otro_turno.mitades) & _mitades(sesion, companero_id, otra_fecha):
                raise SolicitudNoValida("Tu compañero no tiene ese turno")
        elif propuesta.get("cambio") not in ("NO_PUEDO", "OTRA_MITAD"):
            raise SolicitudNoValida("Cambio desconocido")
    solicitud = Solicitud(
        tipo=tipo, estado="ESPERA_COMPANERO" if companero_id else "PENDIENTE", medico_id=medico_id,
        companero_id=companero_id, autor_id=usuario.id, propuesta=json.dumps(propuesta, default=str),
        comentario=comentario.strip(), creada=datetime.now(),
    )
    sesion.add(solicitud)
    sesion.flush()
    return solicitud


# --- Describir ------------------------------------------------------------------------


def propuesta(solicitud: Solicitud) -> dict:
    return json.loads(solicitud.propuesta)


def describir(sesion: Session, solicitud: Solicitud) -> list[str]:
    """Qué cambia, en frases (las muestran la web y la aplicación nativa)."""
    datos = propuesta(solicitud)
    if solicitud.tipo == "DISPONIBILIDAD":
        desde = _fecha(datos["desde"])
        actual = leer_reglas(sesion, solicitud.medico_id, desde).elegibilidad
        lineas = [f"Disponibilidad semanal desde {nombre_mes(desde.year, desde.month)}:"]
        for celda in sorted(datos["elegibilidad"], key=lambda c: (c["dia_semana"], c["turno"] != "MANANA")):
            clave = (celda["dia_semana"], Turno(celda["turno"]))
            nuevo = Elegibilidad(celda["valor"])
            if actual.get(clave) != nuevo:
                lineas.append(f"{DIAS[clave[0]]} por la {TURNO[clave[1]]}: "
                              f"{ELEGIBILIDAD[actual.get(clave, Elegibilidad.DISPONIBLE)]} → {ELEGIBILIDAD[nuevo]}")
        if len(lineas) == 1:
            lineas.append("sin cambios respecto a la actual")
        return lineas
    if solicitud.tipo == "AUSENCIA":
        def periodo(d):
            desde, hasta = _fecha(d["desde"]), _fecha(d["hasta"])
            dias = _corta(desde) if desde == hasta else f"del {_corta(desde)} al {_corta(hasta)}"
            return f"{dias} ({'solo ' + TURNO[Turno(d['turno'])] if d.get('turno') else 'día completo'})"

        if datos["accion"] == "CREAR":
            return [f"Ausencia {periodo(datos)}"]
        ausencia = sesion.get(AusenciaMedico, datos.get("ausencia_id") or 0)
        actual = periodo({"desde": ausencia.desde, "hasta": ausencia.hasta,
                          "turno": ausencia.turno.value if ausencia.turno else None}) if ausencia else "(ya no existe)"
        if datos["accion"] == "ANULAR":
            return [f"Anular la ausencia {actual}"]
        return [f"Cambiar la ausencia {actual}", f"por {periodo(datos)}"]
    fecha, turno = _fecha(datos["fecha"]), Turno(datos["turno"])
    if datos["cambio"] == "NO_PUEDO":
        return [f"No puede hacer la {TURNO[turno]} del {_corta(fecha)}"]
    if datos["cambio"] == "OTRA_MITAD":
        otro = Turno.TARDE if turno is Turno.MANANA else Turno.MANANA
        return [f"Prefiere la {TURNO[otro]} en lugar de la {TURNO[turno]} del {_corta(fecha)}"]
    otra_fecha, otro_turno = _fecha(datos["fecha_companero"]), Turno(datos["turno_companero"])
    companero = solicitud.companero.nombre if solicitud.companero else "?"
    return [f"Intercambio con {companero}: su {TURNO[turno]} del {_corta(fecha)} "
            f"por la {TURNO[otro_turno]} del {_corta(otra_fecha)}"]


# --- Aplicar --------------------------------------------------------------------------


def _cambios_calendario(sesion: Session, solicitud: Solicitud) -> list[p.FijarDia]:
    """Los días que quedan, por médico y fecha, con sus mitades finales."""
    datos = propuesta(solicitud)
    fecha, turno = _fecha(datos["fecha"]), Turno(datos["turno"])
    finales: dict[tuple[int, date], set[Mitad]] = {}

    def quitar(medico: int, dia: date, t: Turno):
        finales.setdefault((medico, dia), _mitades(sesion, medico, dia))
        finales[medico, dia] -= set(t.mitades)

    def poner(medico: int, dia: date, t: Turno):
        finales.setdefault((medico, dia), _mitades(sesion, medico, dia))
        finales[medico, dia] |= set(t.mitades)

    quitar(solicitud.medico_id, fecha, turno)
    if datos["cambio"] == "OTRA_MITAD":
        poner(solicitud.medico_id, fecha, Turno.TARDE if turno is Turno.MANANA else Turno.MANANA)
    elif datos["cambio"] == "INTERCAMBIO":
        otra_fecha, otro_turno = _fecha(datos["fecha_companero"]), Turno(datos["turno_companero"])
        quitar(solicitud.companero_id, otra_fecha, otro_turno)
        poner(solicitud.medico_id, otra_fecha, otro_turno)
        poner(solicitud.companero_id, fecha, turno)
    return [p.FijarDia(m, d, frozenset(h)) for (m, d), h in finales.items()]


def _aplicar(sesion: Session, solicitud: Solicitud) -> list[tuple[int, int]]:
    """Aplica el cambio pedido y devuelve los meses (año, mes) del calendario que toca."""
    datos = propuesta(solicitud)
    if solicitud.tipo == "DISPONIBILIDAD":
        desde = _fecha(datos["desde"])
        reglas = leer_reglas(sesion, solicitud.medico_id, desde)
        for celda in datos["elegibilidad"]:
            reglas.elegibilidad[celda["dia_semana"], Turno(celda["turno"])] = Elegibilidad(celda["valor"])
        guardar_reglas(sesion, solicitud.medico_id, desde, reglas)
        return []
    if solicitud.tipo == "AUSENCIA":
        accion = datos["accion"]
        if accion == "CREAR":
            sesion.add(AusenciaMedico(medico_id=solicitud.medico_id, desde=_fecha(datos["desde"]),
                                      hasta=_fecha(datos["hasta"]),
                                      turno=Turno(datos["turno"]) if datos.get("turno") else None))
        else:
            ausencia = sesion.get(AusenciaMedico, datos.get("ausencia_id") or 0)
            if ausencia is None:
                raise SolicitudNoValida("La ausencia ya no existe")
            if accion == "ANULAR":
                sesion.delete(ausencia)
            else:
                ausencia.desde, ausencia.hasta = _fecha(datos["desde"]), _fecha(datos["hasta"])
                ausencia.turno = Turno(datos["turno"]) if datos.get("turno") else None
        sesion.flush()
        return []
    fecha = _fecha(datos["fecha"])
    try:
        p.aplicar_cambios(sesion, fecha.year, fecha.month, _cambios_calendario(sesion, solicitud), en_publicado=True)
    except p.CambioNoValido as error:
        raise SolicitudNoValida(str(error)) from error
    periodo = p.obtener_periodo(sesion, fecha.year, fecha.month)
    periodo.version += 1  # los clientes con el mes abierto lo notan (diseño, 8)
    sesion.flush()
    return [(fecha.year, fecha.month)]


def meses_afectados(sesion: Session, solicitud: Solicitud) -> list[Periodo]:
    """Meses ya generados a los que afecta (para avisar y calcular los efectos)."""
    datos = propuesta(solicitud)
    if solicitud.tipo == "CALENDARIO":
        fecha = _fecha(datos["fecha"])
        periodo = p.obtener_periodo(sesion, fecha.year, fecha.month)
        return [periodo] if periodo else []
    if solicitud.tipo == "DISPONIBILIDAD":
        desde, hasta = _fecha(datos["desde"]), date.max
    else:
        fechas = [_fecha(datos[c]) for c in ("desde", "hasta") if datos.get(c)]
        ausencia = sesion.get(AusenciaMedico, datos.get("ausencia_id") or 0)
        if ausencia is not None:
            fechas += [ausencia.desde, ausencia.hasta]
        desde, hasta = min(fechas), max(fechas)
    generados = []
    for periodo in sesion.scalars(select(Periodo).order_by(Periodo.anio, Periodo.mes)):
        primero, ultimo = p.limites_mes(periodo.anio, periodo.mes)
        if ultimo >= desde and primero <= hasta and sesion.scalar(
            select(AsignacionPeriodo.id).where(AsignacionPeriodo.periodo_id == periodo.id).limit(1)
        ):
            generados.append(periodo)
    return generados


@dataclass
class Efectos:
    avisos: list[str]  # avisos nuevos del calendario si se aprueba
    meses: list[str]  # «noviembre de 2026 (publicado)»: meses ya generados que hay que revisar


def efectos(sesion: Session, solicitud: Solicitud) -> Efectos:
    periodos = meses_afectados(sesion, solicitud)
    meses = [f"{nombre_mes(x.anio, x.mes)} ({'publicado' if x.publicado else 'borrador'})" for x in periodos]
    antes = {(x.anio, x.mes): {a.mensaje for a in p.leer_calendario(sesion, x.anio, x.mes).avisos} for x in periodos}
    nuevos: list[str] = []
    punto = sesion.begin_nested()
    try:
        _aplicar(sesion, solicitud)
        for (anio, mes), previos in antes.items():
            nuevos += [a.mensaje for a in p.leer_calendario(sesion, anio, mes).avisos if a.mensaje not in previos]
    except SolicitudNoValida as error:
        nuevos.append(f"No se puede aplicar: {error}")
    finally:
        punto.rollback()
    return Efectos(list(dict.fromkeys(nuevos)), meses if solicitud.tipo != "CALENDARIO" else [])


# --- Circuito ---------------------------------------------------------------------------


def _abierta(solicitud: Solicitud, *estados: str) -> None:
    if solicitud.estado in estados:
        return
    if solicitud.estado == "ESPERA_COMPANERO":
        raise SolicitudNoValida("Aún falta que el compañero acepte el intercambio")
    raise SolicitudNoValida("Esta solicitud ya está resuelta")


def retirar(solicitud: Solicitud, usuario: Usuario) -> None:
    if solicitud.medico_id != usuario.medico_id:
        raise PermissionError
    _abierta(solicitud, *ABIERTAS)
    solicitud.estado = "RETIRADA"
    solicitud.resuelta_en = datetime.now()


def responder_companero(solicitud: Solicitud, usuario: Usuario, acepta: bool, comentario: str) -> None:
    if solicitud.companero_id is None or solicitud.companero_id != usuario.medico_id:
        raise PermissionError
    _abierta(solicitud, "ESPERA_COMPANERO")
    solicitud.respuesta_companero = comentario.strip() or None
    if acepta:
        solicitud.estado = "PENDIENTE"
    else:
        solicitud.estado = "RECHAZADA"
        solicitud.resuelta_en = datetime.now()
        solicitud.comentario_resolucion = f"{solicitud.companero.nombre} no acepta el intercambio"


def aprobar(sesion: Session, solicitud: Solicitud, usuario: Usuario, comentario: str, aplicar: bool = True) -> list[tuple[int, int]]:
    """Aprueba y aplica (o, con `aplicar=False`, la marca como resuelta de otra forma).
    Devuelve los meses del calendario que han cambiado."""
    _abierta(solicitud, "PENDIENTE")
    meses = _aplicar(sesion, solicitud) if aplicar else []
    solicitud.estado = "APROBADA" if aplicar else "RESUELTA"
    solicitud.resuelta_por_id, solicitud.resuelta_en = usuario.id, datetime.now()
    solicitud.comentario_resolucion = comentario.strip() or None
    sesion.flush()
    return meses


def rechazar(solicitud: Solicitud, usuario: Usuario, comentario: str) -> None:
    _abierta(solicitud, *ABIERTAS)
    solicitud.estado = "RECHAZADA"
    solicitud.resuelta_por_id, solicitud.resuelta_en = usuario.id, datetime.now()
    solicitud.comentario_resolucion = comentario.strip() or None
