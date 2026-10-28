"""Horarios de los turnos y estado general de la configuración."""

import sqlite3
import tempfile
from contextlib import closing
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from turnos.api import esquemas as e
from turnos.api.dependencias import SesionBD
from turnos.api.eventos import usuario_de
from turnos.datos.bd import copia_de_seguridad
from turnos.datos.tablas import CargaFestivos, CoberturaSemanal, HorarioTurno, Medico, RegistroCambio
from turnos.dominio.modelos import Turno
from turnos.recursos import municipios
from turnos.servicios import importar as importacion
from turnos.servicios.ajustes import Ajustes, guardar_ajustes, leer_ajustes
from turnos.servicios.reglas import leer_reglas

router = APIRouter(prefix="/api", tags=["configuración"])


@router.get("/horarios", response_model=list[e.HorarioTurno])
def horarios(sesion: SesionBD):
    return sesion.scalars(select(HorarioTurno).order_by(HorarioTurno.inicio)).all()


@router.put("/horarios", response_model=list[e.HorarioTurno])
def guardar_horarios(datos: list[e.HorarioTurno], sesion: SesionBD):
    if sorted(h.turno.value for h in datos) != sorted(t.value for t in Turno):
        raise HTTPException(422, "Hay que indicar el horario de mañana y de tarde")
    for h in datos:
        fila = sesion.get(HorarioTurno, h.turno) or HorarioTurno(turno=h.turno)
        fila.inicio, fila.corte, fila.fin = h.inicio, h.corte, h.fin
        sesion.add(fila)
    sesion.flush()
    return horarios(sesion)


@router.get("/ajustes", response_model=e.Ajustes)
def ajustes(sesion: SesionBD):
    return e.Ajustes(**asdict(leer_ajustes(sesion)))


@router.put("/ajustes", response_model=e.Ajustes)
def guardar(datos: e.Ajustes, sesion: SesionBD):
    if datos.municipio not in municipios():
        raise HTTPException(422, f"No hay ningún municipio con el código INE {datos.municipio}")
    guardar_ajustes(sesion, Ajustes(**datos.model_dump()))
    return ajustes(sesion)


@router.get("/estado", response_model=e.Estado)
def estado(sesion: SesionBD):
    hoy = date.today()
    mes = date(hoy.year + hoy.month // 12, hoy.month % 12 + 1, 1)
    activos = sesion.scalars(select(Medico).where(Medico.activo).order_by(Medico.nombre))
    return e.Estado(
        mes=mes,
        anios_festivos_incompletos=list(sesion.scalars(
            select(CargaFestivos.anio).where(~CargaFestivos.completo).order_by(CargaFestivos.anio)
        )),
        # Según la presencia no hay rangos que definir: nadie se queda sin turnos por eso.
        medicos_sin_carga=[] if leer_ajustes(sesion).modo_carga == "PRESENCIA"
        else [m for m in activos if leer_reglas(sesion, m.id, mes).carga is None],
        cobertura_definida=sesion.scalar(
            select(CoberturaSemanal).where(CoberturaSemanal.minimo > 0).limit(1)
        ) is not None,
    )


@router.get("/copia-de-seguridad", response_class=FileResponse)
def descargar_copia(request: Request, tareas: BackgroundTasks):
    """Copia consistente del fichero de datos (SQLite), para guardarla aparte."""
    ruta = request.app.state.motor.url.database
    if not ruta:
        raise HTTPException(404, "La base de datos no está en un fichero")
    carpeta = Path(tempfile.mkdtemp())
    copia = copia_de_seguridad(Path(ruta), carpeta / "copia.sqlite")
    with closing(sqlite3.connect(copia)) as conexion, conexion:
        conexion.execute("DELETE FROM sesion")  # las sesiones abiertas no viajan en la copia
    tareas.add_task(lambda: (copia.unlink(missing_ok=True), carpeta.rmdir()))
    return FileResponse(
        copia,
        media_type="application/vnd.sqlite3",
        filename=f"turnos-copia-{datetime.now():%Y%m%d-%H%M}.sqlite",
    )


@router.post("/importar", response_model=e.ResultadoImportar)
async def importar(request: Request):
    """Sustituye todos los datos por los de una copia (el cuerpo es el fichero SQLite).

    Antes se guarda una copia de los datos actuales junto al fichero de datos."""
    ruta = request.app.state.motor.url.database
    if not ruta:
        raise HTTPException(404, "La base de datos no está en un fichero")
    contenido = await request.body()
    app = request.app
    modo_servidor = hasattr(request.state, "usuario")

    def sustituir():
        # Nadie escribe mientras se sustituyen los datos (ver api/dependencias.py).
        with app.state.cerrojo_escritura:
            resultado = importacion.importar(app.state.motor, Path(ruta), contenido,
                                             conservar_cuentas=modo_servidor)
            with Session(app.state.motor) as sesion, sesion.begin():
                sesion.add(RegistroCambio(momento=datetime.now(), usuario=usuario_de(request),
                                          accion="Importar una copia de los datos",
                                          ruta="POST /api/importar", anio=None, mes=None))
        return resultado

    try:
        resultado = await run_in_threadpool(sustituir)
    except importacion.CopiaNoValida as error:
        raise HTTPException(422, str(error)) from error
    app.state.difusor.publicar({"tipo": "todo", "origen": request.headers.get("x-cliente")})
    return e.ResultadoImportar(**asdict(resultado))


@router.get("/registro", response_model=list[e.CambioRegistrado])
def registro(sesion: SesionBD, limite: int = 100):
    """Últimos cambios: quién, cuándo y qué (diseño del modo servidor, 6.2)."""
    return sesion.scalars(select(RegistroCambio).order_by(RegistroCambio.id.desc()).limit(min(limite, 1000))).all()
