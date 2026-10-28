"""Tablas de la base de datos (diseño, sección 4).

Las cargas se guardan en medios turnos (enteros). Los días de la semana van de
0 (lunes) a 4 (viernes). Los enumerados se guardan como texto.
"""

from datetime import date, datetime, time

from sqlalchemy import CheckConstraint, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

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


def _enum(tipo):
    return Enum(tipo, native_enum=False, length=20, validate_strings=True)


class Base(DeclarativeBase):
    pass


def _dia_semana_valido(nombre: str = "dia_semana") -> CheckConstraint:
    return CheckConstraint(f"{nombre} BETWEEN 0 AND 4", name=f"ck_{nombre}")


# --- Configuración -------------------------------------------------------------


class HorarioTurno(Base):
    __tablename__ = "horario_turno"

    turno: Mapped[Turno] = mapped_column(_enum(Turno), primary_key=True)
    inicio: Mapped[time]
    corte: Mapped[time]  # separa las dos mitades
    fin: Mapped[time]

    __table_args__ = (CheckConstraint("inicio < corte AND corte < fin", name="ck_horas"),)


class Ajuste(Base):
    """Ajustes generales de la aplicación (clave → valor en JSON). Ver `servicios/ajustes.py`."""

    __tablename__ = "ajuste"

    clave: Mapped[str] = mapped_column(primary_key=True)
    valor: Mapped[str]


class Festivo(Base):
    __tablename__ = "festivo"

    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[date] = mapped_column(unique=True)
    descripcion: Mapped[str]
    ambito: Mapped[AmbitoFestivo] = mapped_column(_enum(AmbitoFestivo))


class CargaFestivos(Base):
    """Años cuyo calendario de festivos precargado ya se volcó en `festivo`.

    Evita volver a cargarlo (y deshacer cambios del planificador) en cada arranque.
    """

    __tablename__ = "carga_festivos"

    anio: Mapped[int] = mapped_column(primary_key=True)
    calendario: Mapped[str]  # el precargado ("madrid") u "oficial:<INE>" (buscado en línea)
    completo: Mapped[bool]  # False si faltaban festivos por publicar al cargarlo
    cargado_en: Mapped[datetime]


class CoberturaSemanal(Base):
    __tablename__ = "cobertura_semanal"

    dia_semana: Mapped[int] = mapped_column(primary_key=True)
    mitad: Mapped[Mitad] = mapped_column(_enum(Mitad), primary_key=True)
    minimo: Mapped[int]
    maximo: Mapped[int]

    __table_args__ = (
        _dia_semana_valido(),
        CheckConstraint("0 <= minimo AND minimo <= maximo", name="ck_cobertura"),
    )


class CoberturaFecha(Base):
    __tablename__ = "cobertura_fecha"

    fecha: Mapped[date] = mapped_column(primary_key=True)
    mitad: Mapped[Mitad] = mapped_column(_enum(Mitad), primary_key=True)
    minimo: Mapped[int]
    maximo: Mapped[int]

    __table_args__ = (CheckConstraint("0 <= minimo AND minimo <= maximo", name="ck_cobertura"),)


# --- Médicos y reglas ------------------------------------------------------------


class Medico(Base):
    __tablename__ = "medico"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str]
    codigo: Mapped[str] = mapped_column(unique=True)
    activo: Mapped[bool] = mapped_column(default=True)
    color: Mapped[str | None] = mapped_column(String(7))  # "#rrggbb" para el calendario

    elegibilidad: Mapped[list["ReglaElegibilidad"]] = relationship(cascade="all, delete-orphan")
    jornadas: Mapped[list["JornadaSemanal"]] = relationship(cascade="all, delete-orphan")
    cargas: Mapped[list["Carga"]] = relationship(cascade="all, delete-orphan")
    preferencias: Mapped[list["ReglaPreferencia"]] = relationship(cascade="all, delete-orphan")
    ausencias: Mapped[list["AusenciaMedico"]] = relationship(cascade="all, delete-orphan")


class ReglaElegibilidad(Base):
    """Celda de la cuadrícula de elegibilidad, válida desde una fecha (diseño, 4.2)."""

    __tablename__ = "elegibilidad"

    id: Mapped[int] = mapped_column(primary_key=True)
    medico_id: Mapped[int] = mapped_column(ForeignKey("medico.id", ondelete="CASCADE"))
    vigente_desde: Mapped[date]
    dia_semana: Mapped[int]
    turno: Mapped[Turno] = mapped_column(_enum(Turno))
    valor: Mapped[Elegibilidad] = mapped_column(_enum(Elegibilidad))

    __table_args__ = (
        _dia_semana_valido(),
        UniqueConstraint("medico_id", "vigente_desde", "dia_semana", "turno"),
    )


class JornadaSemanal(Base):
    """Jornada de 1,5 o 2 turnos fijada por el planificador (especificaciones, 5.3).

    `tipo` NULL a partir de `vigente_desde` anula una jornada anterior.
    """

    __tablename__ = "jornada_semanal"

    id: Mapped[int] = mapped_column(primary_key=True)
    medico_id: Mapped[int] = mapped_column(ForeignKey("medico.id", ondelete="CASCADE"))
    vigente_desde: Mapped[date]
    dia_semana: Mapped[int]
    tipo: Mapped[TipoJornada | None] = mapped_column(_enum(TipoJornada))

    __table_args__ = (
        _dia_semana_valido(),
        UniqueConstraint("medico_id", "vigente_desde", "dia_semana"),
    )


class Carga(Base):
    """Rango de carga mensual en medios turnos (especificaciones, 5.2).

    `turno` NULL = carga total (siempre con máximo). En las filas por turno,
    `maximo` NULL = sin límite; una fila 0–NULL anula un límite anterior.
    """

    __tablename__ = "carga"

    id: Mapped[int] = mapped_column(primary_key=True)
    medico_id: Mapped[int] = mapped_column(ForeignKey("medico.id", ondelete="CASCADE"))
    vigente_desde: Mapped[date]
    turno: Mapped[Turno | None] = mapped_column(_enum(Turno))
    minimo: Mapped[int]
    maximo: Mapped[int | None]

    __table_args__ = (
        CheckConstraint("0 <= minimo AND (maximo IS NULL OR minimo <= maximo)", name="ck_carga"),
        CheckConstraint("turno IS NOT NULL OR maximo IS NOT NULL", name="ck_carga_total"),
        UniqueConstraint("medico_id", "vigente_desde", "turno"),
    )


class ReglaPreferencia(Base):
    __tablename__ = "preferencia"

    id: Mapped[int] = mapped_column(primary_key=True)
    medico_id: Mapped[int] = mapped_column(ForeignKey("medico.id", ondelete="CASCADE"))
    dia_semana: Mapped[int]
    turno: Mapped[Turno] = mapped_column(_enum(Turno))
    valor: Mapped[Preferencia] = mapped_column(_enum(Preferencia))

    __table_args__ = (
        _dia_semana_valido(),
        UniqueConstraint("medico_id", "dia_semana", "turno"),
    )


class AusenciaMedico(Base):
    """Ausencia sin motivo, solo fechas (especificaciones, 8). `turno` NULL = día completo."""

    __tablename__ = "ausencia"

    id: Mapped[int] = mapped_column(primary_key=True)
    medico_id: Mapped[int] = mapped_column(ForeignKey("medico.id", ondelete="CASCADE"))
    desde: Mapped[date]
    hasta: Mapped[date]
    turno: Mapped[Turno | None] = mapped_column(_enum(Turno))

    __table_args__ = (CheckConstraint("desde <= hasta", name="ck_fechas"),)


class RotacionTabla(Base):
    """Turno rotativo (especificaciones, 5.8): turnos de la semana que un grupo de
    médicos hace por semanas alternas, empezando por el primero en la semana de `desde`."""

    __tablename__ = "rotacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str]
    desde: Mapped[date]
    activa: Mapped[bool] = mapped_column(default=True)

    miembros: Mapped[list["RotacionMedico"]] = relationship(
        cascade="all, delete-orphan", order_by="RotacionMedico.orden"
    )
    huecos: Mapped[list["RotacionHueco"]] = relationship(cascade="all, delete-orphan")


class RotacionMedico(Base):
    __tablename__ = "rotacion_medico"

    rotacion_id: Mapped[int] = mapped_column(ForeignKey("rotacion.id", ondelete="CASCADE"), primary_key=True)
    medico_id: Mapped[int] = mapped_column(ForeignKey("medico.id", ondelete="CASCADE"), primary_key=True)
    orden: Mapped[int]


class RotacionHueco(Base):
    __tablename__ = "rotacion_hueco"

    rotacion_id: Mapped[int] = mapped_column(ForeignKey("rotacion.id", ondelete="CASCADE"), primary_key=True)
    dia_semana: Mapped[int] = mapped_column(primary_key=True)
    turno: Mapped[Turno] = mapped_column(_enum(Turno), primary_key=True)

    __table_args__ = (_dia_semana_valido(),)


# --- Periodos y asignaciones -----------------------------------------------------


class Periodo(Base):
    __tablename__ = "periodo"

    id: Mapped[int] = mapped_column(primary_key=True)
    anio: Mapped[int]
    mes: Mapped[int]
    publicado_en: Mapped[datetime | None]  # NULL = borrador
    # Sube con cada cambio del mes: los clientes la envían para detectar que otro
    # usuario lo ha cambiado mientras tanto (diseño del modo servidor, 8).
    version: Mapped[int] = mapped_column(default=0, server_default="0")

    __table_args__ = (
        UniqueConstraint("anio", "mes"),
        CheckConstraint("mes BETWEEN 1 AND 12", name="ck_mes"),
    )

    @property
    def publicado(self) -> bool:
        return self.publicado_en is not None


class CargaAjustada(Base):
    """Rango del mes tras el ajuste por ausencias, con sobrescritura manual.

    `objetivo` (solo en la fila total) es la carga objetivo usada al generar;
    sirve para calcular el saldo de equidad de los meses siguientes.
    """

    __tablename__ = "carga_ajustada"

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("periodo.id", ondelete="CASCADE"))
    medico_id: Mapped[int] = mapped_column(ForeignKey("medico.id", ondelete="CASCADE"))
    turno: Mapped[Turno | None] = mapped_column(_enum(Turno))
    minimo_calc: Mapped[int]
    maximo_calc: Mapped[int]
    minimo_manual: Mapped[int | None]
    maximo_manual: Mapped[int | None]
    objetivo: Mapped[int | None]

    __table_args__ = (UniqueConstraint("periodo_id", "medico_id", "turno"),)


class AsignacionPeriodo(Base):
    """Un médico en una mitad de turno. Un turno completo son dos filas."""

    __tablename__ = "asignacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("periodo.id", ondelete="CASCADE"))
    medico_id: Mapped[int] = mapped_column(ForeignKey("medico.id", ondelete="CASCADE"))
    fecha: Mapped[date]
    mitad: Mapped[Mitad] = mapped_column(_enum(Mitad))
    origen: Mapped[OrigenAsignacion] = mapped_column(_enum(OrigenAsignacion))
    bloqueada: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (UniqueConstraint("periodo_id", "medico_id", "fecha", "mitad"),)


class RolTarde(Base):
    """Médico que hace urgencias o domicilios una tarde (especificaciones, 5.6).

    `manual`: elegido a mano; el generador lo respeta al regenerar."""

    __tablename__ = "rol_tarde"

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("periodo.id", ondelete="CASCADE"))
    fecha: Mapped[date]
    rol: Mapped[Rol] = mapped_column(_enum(Rol))
    medico_id: Mapped[int] = mapped_column(ForeignKey("medico.id", ondelete="CASCADE"))
    manual: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (UniqueConstraint("periodo_id", "fecha", "rol"),)


class Veto(Base):
    """Turno que el planificador ha quitado a mano y el motor no debe volver a asignar."""

    __tablename__ = "veto"

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("periodo.id", ondelete="CASCADE"))
    medico_id: Mapped[int] = mapped_column(ForeignKey("medico.id", ondelete="CASCADE"))
    fecha: Mapped[date]
    turno: Mapped[Turno] = mapped_column(_enum(Turno))

    __table_args__ = (UniqueConstraint("periodo_id", "medico_id", "fecha", "turno"),)


class AvisoPeriodo(Base):
    """Avisos de la última generación de un periodo (especificaciones, 6.4)."""

    __tablename__ = "aviso"

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("periodo.id", ondelete="CASCADE"))
    tipo: Mapped[TipoAviso] = mapped_column(_enum(TipoAviso))
    mensaje: Mapped[str]
    fecha: Mapped[date | None]
    medico_id: Mapped[int | None] = mapped_column(ForeignKey("medico.id", ondelete="CASCADE"))


class RegistroCambio(Base):
    """Quién cambió qué y cuándo (diseño del modo servidor, 6.2)."""

    __tablename__ = "registro_cambio"

    id: Mapped[int] = mapped_column(primary_key=True)
    momento: Mapped[datetime]
    usuario: Mapped[str | None]  # en el modo personal, None
    accion: Mapped[str]  # p. ej. «Generar», «Cambio manual», «Reglas de un médico»
    ruta: Mapped[str]  # método y ruta de la API
    anio: Mapped[int | None]
    mes: Mapped[int | None]



# --- Modo servidor: usuarios y sesiones (diseño del modo servidor, 6) -------------------


class Usuario(Base):
    """Cuenta del modo servidor. En el modo personal no hay ninguna."""

    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(40), unique=True)  # para entrar, en minúsculas
    nombre_visible: Mapped[str] = mapped_column(String(80))
    hash_contrasena: Mapped[str]
    rol: Mapped[str] = mapped_column(String(20))  # ADMINISTRADOR, PLANIFICADOR o MEDICO
    medico_id: Mapped[int | None] = mapped_column(ForeignKey("medico.id", ondelete="SET NULL"))
    activo: Mapped[bool] = mapped_column(default=True)
    # Con contraseña temporal (recién creada o restablecida): debe elegir una al entrar.
    debe_cambiar: Mapped[bool] = mapped_column(default=False)
    creado: Mapped[datetime]

    __table_args__ = (CheckConstraint("rol IN ('ADMINISTRADOR', 'PLANIFICADOR', 'MEDICO')", name="ck_rol"),)


class SesionUsuario(Base):
    """Sesión abierta en un dispositivo. Se guarda el resumen del token, no el token."""

    __tablename__ = "sesion"

    id: Mapped[int] = mapped_column(primary_key=True)
    hash_token: Mapped[str] = mapped_column(String(64), unique=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"))
    dispositivo: Mapped[str] = mapped_column(String(200))
    creada: Mapped[datetime]
    ultimo_uso: Mapped[datetime]
    caduca: Mapped[datetime]

    usuario: Mapped[Usuario] = relationship()


class Solicitud(Base):
    """Cambio que propone un médico y decide el planificador (diseño del modo servidor, 6.4).

    `propuesta` es el cambio pedido en JSON (ver `servicios/solicitudes.py`). Estados:
    ESPERA_COMPANERO (intercambio aún sin aceptar por el otro médico), PENDIENTE,
    APROBADA (aplicada), RESUELTA (el planificador lo resolvió de otra forma),
    RECHAZADA y RETIRADA."""

    __tablename__ = "solicitud"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20))  # DISPONIBILIDAD, AUSENCIA o CALENDARIO
    estado: Mapped[str] = mapped_column(String(20))
    medico_id: Mapped[int] = mapped_column(ForeignKey("medico.id", ondelete="CASCADE"))
    companero_id: Mapped[int | None] = mapped_column(ForeignKey("medico.id", ondelete="CASCADE"))
    autor_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"))
    propuesta: Mapped[str]
    comentario: Mapped[str] = mapped_column(default="")
    respuesta_companero: Mapped[str | None]
    creada: Mapped[datetime]
    resuelta_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"))
    resuelta_en: Mapped[datetime | None]
    comentario_resolucion: Mapped[str | None]

    medico: Mapped[Medico] = relationship(foreign_keys=[medico_id])
    companero: Mapped[Medico | None] = relationship(foreign_keys=[companero_id])
    autor: Mapped[Usuario | None] = relationship(foreign_keys=[autor_id])
    resuelta_por: Mapped[Usuario | None] = relationship(foreign_keys=[resuelta_por_id])
