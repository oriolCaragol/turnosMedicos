"""Modelos de entrada y salida de la API.

Las cargas viajan en medios turnos (enteros); la interfaz las muestra en turnos.
"""

from datetime import date, datetime, time

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from turnos.dominio.calendario import AmbitoFestivo
from turnos.dominio.modelos import (
    Elegibilidad,
    Mitad,
    OrigenAsignacion,
    Preferencia,
    Rol,
    TipoJornada,
    Turno,
)
from turnos.motor.resultado import TipoAviso
from turnos.recursos import MUNICIPIO_POR_DEFECTO

DiaSemana = Field(ge=0, le=4, description="0 = lunes … 4 = viernes")


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Médicos -----------------------------------------------------------------------


class MedicoEntrada(_Base):
    nombre: str = Field(min_length=1, max_length=80)
    codigo: str = Field(min_length=1, max_length=6, description="Iniciales para el calendario")
    activo: bool = True
    color: str | None = Field(
        default=None, pattern=r"^#[0-9a-fA-F]{6}$", description="Color en el calendario, #rrggbb"
    )


class Medico(MedicoEntrada):
    id: int


class CeldaElegibilidad(_Base):
    dia_semana: int = DiaSemana
    turno: Turno
    valor: Elegibilidad


class JornadaDia(_Base):
    dia_semana: int = DiaSemana
    tipo: TipoJornada


class PreferenciaHueco(_Base):
    dia_semana: int = DiaSemana
    turno: Turno
    valor: Preferencia


class RangoCarga(_Base):
    minimo: int = Field(ge=0)
    maximo: int = Field(ge=0)

    @model_validator(mode="after")
    def _orden(self):
        if self.maximo < self.minimo:
            raise ValueError("El máximo no puede ser menor que el mínimo")
        return self


class RangoCargaTurno(_Base):
    """Límite de carga de un tipo de turno; `maximo` None = sin límite."""

    turno: Turno
    minimo: int = Field(ge=0)
    maximo: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _orden(self):
        if self.maximo is not None and self.maximo < self.minimo:
            raise ValueError("El máximo no puede ser menor que el mínimo")
        return self


class Reglas(_Base):
    elegibilidad: list[CeldaElegibilidad]
    jornadas: list[JornadaDia] = []
    carga: RangoCarga | None
    carga_por_turno: list[RangoCargaTurno] = []
    preferencias: list[PreferenciaHueco] = []


class ReglasLeidas(Reglas):
    vigente_desde: date | None = Field(description="Versión aplicada; None si nunca se guardaron")


class ReglasGuardar(Reglas):
    """Sin `carga`, se guarda el resto y la carga queda como estaba (o sin definir)."""

    vigente_desde: date
    carga: RangoCarga | None = None


# --- Ausencias ---------------------------------------------------------------------


class AusenciaEntrada(_Base):
    medico_id: int
    desde: date
    hasta: date
    turno: Turno | None = Field(default=None, description="None = día completo")

    @model_validator(mode="after")
    def _orden(self):
        if self.hasta < self.desde:
            raise ValueError("La fecha final no puede ser anterior a la inicial")
        return self


class Ausencia(AusenciaEntrada):
    id: int


# --- Festivos ----------------------------------------------------------------------


class FestivoEntrada(_Base):
    fecha: date
    descripcion: str = Field(min_length=1, max_length=100)
    ambito: AmbitoFestivo = AmbitoFestivo.OTRO


class Festivo(FestivoEntrada):
    id: int


class Municipio(_Base):
    ine: str
    nombre: str
    provincia: str
    ccaa: str
    ccaa_nombre: str


class FestivoOficial(_Base):
    fecha: date
    descripcion: str
    ambito: AmbitoFestivo
    fuente: str = Field(description="Referencia oficial (BOE, boletín autonómico, datos abiertos…)")
    url: str | None = None
    estado: str = Field(description="NUEVO (falta en tus datos), IGUAL o DISTINTO (misma fecha, otro nombre o ámbito)")


class BusquedaFestivos(_Base):
    anio: int
    municipio: Municipio
    festivos: list[FestivoOficial]
    solo_en_tus_datos: list[Festivo] = Field(description="Festivos del año que no aparecen en las fuentes")
    fuentes: list[str]
    avisos: list[str]
    completo: bool = Field(description="Incluye los dos festivos locales")


class ResultadoImportar(_Base):
    medicos: int
    meses: int
    copia_anterior: str = Field(description="Fichero con la copia de los datos que había antes de importar")


class AnioFestivos(_Base):
    anio: int
    calendario: str
    completo: bool
    precargado: bool = Field(default=False, description="Sus festivos vienen con la aplicación (se pueden restaurar)")


# --- Cobertura ---------------------------------------------------------------------


class CoberturaMitad(_Base):
    mitad: Mitad
    minimo: int = Field(ge=0)
    maximo: int = Field(ge=0)

    @model_validator(mode="after")
    def _orden(self):
        if self.maximo < self.minimo:
            raise ValueError("El máximo no puede ser menor que el mínimo")
        return self


class CoberturaSemanal(CoberturaMitad):
    dia_semana: int = DiaSemana


class CoberturaFecha(CoberturaMitad):
    fecha: date


# --- Configuración y estado -------------------------------------------------------


class HorarioTurno(_Base):
    turno: Turno
    inicio: time
    corte: time
    fin: time

    @model_validator(mode="after")
    def _orden(self):
        if not self.inicio < self.corte < self.fin:
            raise ValueError("Debe cumplirse inicio < corte < fin")
        return self


class HuecoSemanal(_Base):
    dia_semana: int = DiaSemana
    turno: Turno


class RotacionEntrada(_Base):
    """Turno rotativo: `huecos` de la semana que hacen por semanas alternas los `medicos`
    (en orden: el primero, la semana de `desde`; el siguiente, la semana después…)."""

    nombre: str = Field(min_length=1, max_length=80)
    desde: date
    activa: bool = True
    medicos: list[int] = []
    huecos: list[HuecoSemanal] = []


class Rotacion(RotacionEntrada):
    id: int


class Ajustes(_Base):
    """Ajustes generales de la aplicación."""

    todos_trabajan: bool = Field(
        default=True,
        description="Cada médico tiene algún turno cada día laborable, salvo ausencia o sin turnos posibles",
    )
    modo_carga: Literal["RANGOS", "PRESENCIA"] = Field(
        default="RANGOS",
        description="RANGOS: turnos al mes mínimo y máximo de cada médico. PRESENCIA: todos los días salvo ausencia, sin rangos",
    )
    roles_segun_presencia: bool = Field(
        default=True, description="Urgencias y domicilios en proporción a la presencia de cada médico en el mes"
    )
    prioridad_roles: Literal["URGENCIAS", "DOMICILIOS", "IGUAL"] = Field(
        default="URGENCIAS",
        description="Papel que se reparte por igual antes; si hay que forzar una desigualdad, va al otro",
    )
    mostrar_cobertura: bool = Field(
        default=False, description="Mostrar en cada turno del calendario los médicos asignados frente a los necesarios"
    )
    municipio: str = Field(default=MUNICIPIO_POR_DEFECTO, pattern=r"^\d{5}$", description="Código INE del municipio del centro")


class Estado(_Base):
    """Situaciones que conviene resolver antes de generar un calendario.

    `medicos_sin_carga` se calcula para `mes` (el mes siguiente, que es el que
    normalmente se planifica).
    """

    mes: date = Field(description="Primer día del mes revisado")
    anios_festivos_incompletos: list[int]
    medicos_sin_carga: list[Medico]
    cobertura_definida: bool


# --- Calendario del mes ----------------------------------------------------------


class Dia(_Base):
    fecha: date
    festivo: str | None = Field(description="Descripción si es festivo; None si es laborable")


class CoberturaDia(_Base):
    fecha: date
    mitad: Mitad
    minimo: int
    maximo: int


class NoElegible(_Base):
    fecha: date
    turno: Turno
    motivo: str = Field(description="AUSENTE o NO_DISPONIBLE")


class HuecoMes(_Base):
    fecha: date
    turno: Turno


class MedicoCalendario(_Base):
    id: int
    nombre: str
    codigo: str
    activo: bool
    color: str | None = None
    con_carga: bool = Field(description="False si no tiene carga definida para el mes")
    minimo: int | None = None
    maximo: int | None = None
    minimo_calculado: int | None = None
    maximo_calculado: int | None = None
    carga_manual: bool = False
    asignado: int = Field(description="Medios turnos asignados en el mes")
    asignado_manana: int
    asignado_tarde: int
    urgencias: int = Field(default=0, description="Tardes de urgencias en el mes")
    domicilios: int = Field(default=0, description="Tardes de domicilios en el mes")
    tardes_disponibles: int = Field(default=0, description="Tardes que puede trabajar en el mes")
    no_elegibles: list[NoElegible]
    habituales: list[HuecoMes] = Field(default=[], description="Turnos habituales del mes")


class AsignacionCalendario(_Base):
    medico_id: int
    fecha: date
    mitad: Mitad
    origen: OrigenAsignacion
    bloqueada: bool


class RolCalendario(_Base):
    fecha: date
    rol: Rol
    medico_id: int
    manual: bool = False


class VetoCalendario(_Base):
    medico_id: int
    fecha: date
    turno: Turno


class AvisoCalendario(_Base):
    tipo: TipoAviso
    mensaje: str
    fecha: date | None = None
    medico_id: int | None = None


class Calendario(_Base):
    anio: int
    mes: int
    estado: str = Field(description="SIN_GENERAR, BORRADOR o PUBLICADO")
    version: int = Field(default=0, description="Sube con cada cambio del mes (se envía en X-Version-Mes)")
    carga_por_rangos: bool = Field(
        default=True, description="False con el modo «según la presencia»: no hay rangos de carga que mostrar")
    publicado_en: datetime | None
    dias: list[Dia]
    cobertura: list[CoberturaDia]
    medicos: list[MedicoCalendario]
    asignaciones: list[AsignacionCalendario]
    vetos: list[VetoCalendario]
    roles: list[RolCalendario] = []
    avisos: list[AvisoCalendario]


class MesPublicado(BaseModel):
    anio: int
    mes: int
    publicado_en: datetime


class CambioRegistrado(_Base):
    momento: datetime
    usuario: str | None
    accion: str
    ruta: str
    anio: int | None
    mes: int | None


class Generar(_Base):
    alternativa: bool = False


class Cambio(_Base):
    """Un cambio manual; se indica exactamente uno de:
    - `mitades`: deja al médico ese día exactamente en esas mitades;
    - `bloqueada`: bloquea o desbloquea sus asignaciones de ese día;
    - `rol`: le pone de urgencias o domicilios esa tarde."""

    medico_id: int
    fecha: date
    mitades: list[Mitad] | None = None
    bloqueada: bool | None = None
    rol: Rol | None = None

    @model_validator(mode="after")
    def _uno(self):
        if sum(v is not None for v in (self.mitades, self.bloqueada, self.rol)) != 1:
            raise ValueError("Indica solo uno de 'mitades', 'bloqueada' o 'rol'")
        return self


class Liberar(_Base):
    """Sin fecha: todo el mes. Con fecha y sin turno: todo el día."""

    fecha: date | None = None
    turno: Turno | None = None


class EstadoManual(_Base):
    asignaciones: list[AsignacionCalendario]
    vetos: list[VetoCalendario]
    roles: list[RolCalendario] = []


class CargaManual(_Base):
    """Rango del mes en medios turnos; None = usar el calculado."""

    minimo: int | None = Field(default=None, ge=0)
    maximo: int | None = Field(default=None, ge=0)


# --- Modo servidor: usuarios y sesiones (diseño del modo servidor, 6) -------------------

RolUsuario = Literal["ADMINISTRADOR", "PLANIFICADOR", "MEDICO"]


class Yo(BaseModel):
    """Quién usa la aplicación. En el modo personal, siempre un administrador sin cuenta."""

    modo: Literal["personal", "servidor"]
    id: int | None = None
    nombre: str | None = None
    nombre_visible: str | None = None
    rol: RolUsuario
    medico_id: int | None = None
    debe_cambiar: bool = False


class InicioSesion(BaseModel):
    usuario: str = Field(max_length=80)
    contrasena: str = Field(max_length=200)
    dispositivo: str | None = Field(default=None, max_length=200)
    # Las aplicaciones de escritorio guardan el token y lo envían en una cabecera.
    aplicacion: bool = False


class SesionIniciada(Yo):
    token: str | None = None


class CambioContrasena(BaseModel):
    actual: str = Field(max_length=200)
    nueva: str = Field(max_length=200)


class UsuarioEntrada(BaseModel):
    nombre_visible: str = Field(min_length=1, max_length=80)
    rol: RolUsuario
    medico_id: int | None = None
    activo: bool = True


class UsuarioNuevo(UsuarioEntrada):
    nombre: str = Field(min_length=1, max_length=40)


class UsuarioSalida(_Base):
    id: int
    nombre: str
    nombre_visible: str
    rol: RolUsuario
    medico_id: int | None
    activo: bool
    debe_cambiar: bool
    creado: datetime


class ContrasenaTemporal(BaseModel):
    usuario: UsuarioSalida
    contrasena_temporal: str


class SesionAbierta(BaseModel):
    id: int
    usuario: str
    nombre_visible: str
    dispositivo: str
    creada: datetime
    ultimo_uso: datetime
    caduca: datetime
    actual: bool


# --- Modo servidor: el propio servidor (diseño del modo servidor, 10) ------------------


class ServidorPublico(BaseModel):
    """Lo que necesita la página de inicio de sesión."""

    nombre: str
    https: bool
    hay_certificado: bool


class CopiaServidor(BaseModel):
    nombre: str
    tamano: int
    fecha: datetime


class InfoServidor(ServidorPublico):
    direcciones: list[str]
    huella_autoridad: str | None
    certificado_caduca: datetime | None
    datos: str
    copias: list[CopiaServidor]
    conservar_copias: int


# --- Solicitudes de los médicos (diseño del modo servidor, 6.4) --------------------------


class PropuestaDisponibilidad(BaseModel):
    tipo: Literal["DISPONIBILIDAD"]
    desde: date = Field(description="Primer día del mes desde el que vale")
    elegibilidad: list[CeldaElegibilidad] = Field(min_length=10, max_length=10)


class PropuestaAusencia(BaseModel):
    tipo: Literal["AUSENCIA"]
    accion: Literal["CREAR", "MODIFICAR", "ANULAR"]
    ausencia_id: int | None = None
    desde: date | None = None
    hasta: date | None = None
    turno: Turno | None = Field(default=None, description="None = día completo")

    @model_validator(mode="after")
    def _fechas(self):
        if self.accion != "ANULAR" and (self.desde is None or self.hasta is None):
            raise ValueError("Indica las fechas de la ausencia")
        if self.accion != "CREAR" and self.ausencia_id is None:
            raise ValueError("Indica qué ausencia")
        return self


class PropuestaCalendario(BaseModel):
    tipo: Literal["CALENDARIO"]
    cambio: Literal["NO_PUEDO", "OTRA_MITAD", "INTERCAMBIO"]
    fecha: date
    turno: Turno
    companero_id: int | None = None
    fecha_companero: date | None = None
    turno_companero: Turno | None = None

    @model_validator(mode="after")
    def _intercambio(self):
        if self.cambio == "INTERCAMBIO" and None in (self.companero_id, self.fecha_companero, self.turno_companero):
            raise ValueError("Elige el compañero y el turno que te daría a cambio")
        return self


class SolicitudEntrada(BaseModel):
    propuesta: PropuestaDisponibilidad | PropuestaAusencia | PropuestaCalendario = Field(discriminator="tipo")
    comentario: str = Field(default="", max_length=1000)


EstadoSolicitud = Literal["ESPERA_COMPANERO", "PENDIENTE", "APROBADA", "RESUELTA", "RECHAZADA", "RETIRADA"]


class SolicitudSalida(BaseModel):
    id: int
    tipo: Literal["DISPONIBILIDAD", "AUSENCIA", "CALENDARIO"]
    estado: EstadoSolicitud
    medico_id: int
    medico: str
    companero_id: int | None
    companero: str | None
    propuesta: dict
    descripcion: list[str] = Field(description="Qué cambia, en frases")
    comentario: str
    respuesta_companero: str | None
    creada: datetime
    resuelta_por: str | None
    resuelta_en: datetime | None
    comentario_resolucion: str | None
    mia: bool = Field(description="La ha pedido quien consulta")
    me_toca_aceptar: bool = Field(description="Es el compañero de un intercambio en espera")


class Resolucion(BaseModel):
    comentario: str = Field(default="", max_length=1000)
    aplicar: bool = Field(default=True, description="False: resuelta de otra forma, sin aplicar el cambio")


class RespuestaCompanero(BaseModel):
    acepta: bool
    comentario: str = Field(default="", max_length=1000)


class EfectosSolicitud(BaseModel):
    avisos: list[str]
    meses: list[str]
