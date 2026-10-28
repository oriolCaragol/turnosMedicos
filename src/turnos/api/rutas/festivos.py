"""Calendario de festivos (especificaciones, 4.2)."""

from dataclasses import asdict
from datetime import date, datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from turnos.api import esquemas as e
from turnos.api.dependencias import SesionBD, obtener_o_404
from turnos.datos.tablas import CargaFestivos, Festivo
from turnos.recursos import CALENDARIO_PRECARGADO, Municipio, buscar_municipios, calendarios_festivos, municipios
from turnos.servicios import festivos_oficiales
from turnos.servicios.ajustes import leer_ajustes

router = APIRouter(prefix="/api/festivos", tags=["festivos"])


@router.get("", response_model=list[e.Festivo])
def listar(anio: int, sesion: SesionBD):
    return sesion.scalars(
        select(Festivo)
        .where(Festivo.fecha.between(date(anio, 1, 1), date(anio, 12, 31)))
        .order_by(Festivo.fecha)
    ).all()


@router.get("/anios", response_model=list[e.AnioFestivos])
def anios(sesion: SesionBD):
    """Años con festivos cargados (precargados o buscados en línea) y si están completos."""
    return [
        {"anio": c.anio, "calendario": c.calendario, "completo": c.completo,
         "precargado": c.calendario == CALENDARIO_PRECARGADO}
        for c in sesion.scalars(select(CargaFestivos).order_by(CargaFestivos.anio))
    ]


@router.post("", response_model=e.Festivo, status_code=201)
def crear(datos: e.FestivoEntrada, sesion: SesionBD):
    if sesion.scalar(select(Festivo).where(Festivo.fecha == datos.fecha)):
        raise HTTPException(409, "Ya hay un festivo en esa fecha")
    festivo = Festivo(**datos.model_dump())
    sesion.add(festivo)
    sesion.flush()
    return festivo


@router.delete("/{festivo_id}", status_code=204)
def borrar(festivo_id: int, sesion: SesionBD):
    sesion.delete(obtener_o_404(sesion, Festivo, festivo_id, "Festivo"))


@router.post("/restaurar/{anio}", response_model=list[e.Festivo])
def restaurar(anio: int, sesion: SesionBD, calendario: str = CALENDARIO_PRECARGADO):
    """Vuelve a añadir los festivos precargados del año que falten. Devuelve los añadidos."""
    cal = next((c for c in calendarios_festivos(calendario) if c.anio == anio), None)
    if cal is None:
        raise HTTPException(404, f"No hay calendario precargado de {calendario} para {anio}")
    existentes = set(sesion.scalars(select(Festivo.fecha)))
    nuevos = [
        Festivo(fecha=f.fecha, descripcion=f.descripcion, ambito=f.ambito)
        for f in cal.festivos if f.fecha not in existentes
    ]
    sesion.add_all(nuevos)
    sesion.flush()
    return nuevos


# --- Municipio y festivos oficiales (Configuración) ------------------------------------


def _municipio(ine: str) -> Municipio:
    municipio = municipios().get(ine)
    if municipio is None:
        raise HTTPException(404, f"No hay ningún municipio con el código INE {ine}")
    return municipio


@router.get("/municipios", response_model=list[e.Municipio])
def buscar_municipio(q: str = ""):
    return buscar_municipios(q)


@router.get("/municipios/{ine}", response_model=e.Municipio)
def municipio(ine: str):
    return _municipio(ine)


def _buscar(anio: int, sesion) -> tuple[e.BusquedaFestivos, Municipio]:
    municipio = _municipio(leer_ajustes(sesion).municipio)
    try:
        busqueda = festivos_oficiales.buscar(anio, municipio)
    except festivos_oficiales.SinConexion as error:
        raise HTTPException(502, str(error)) from error
    existentes = {f.fecha: f for f in listar(anio, sesion)}
    oficiales = []
    for f in busqueda.festivos:
        previo = existentes.get(f.fecha)
        estado = "NUEVO" if previo is None else (
            "IGUAL" if (previo.descripcion, previo.ambito) == (f.descripcion, f.ambito) else "DISTINTO"
        )
        oficiales.append(e.FestivoOficial(**asdict(f), estado=estado))
    fechas = {f.fecha for f in busqueda.festivos}
    return e.BusquedaFestivos(
        anio=anio,
        municipio=municipio,
        festivos=oficiales,
        solo_en_tus_datos=[f for f in existentes.values() if f.fecha not in fechas] if busqueda.festivos else [],
        fuentes=busqueda.fuentes,
        avisos=busqueda.avisos,
        completo=busqueda.locales >= 2,
    ), municipio


@router.get("/oficiales/{anio}", response_model=e.BusquedaFestivos)
def buscar_oficiales(anio: int, sesion: SesionBD):
    """Festivos oficiales del municipio del centro, comparados con los guardados."""
    return _buscar(anio, sesion)[0]


@router.post("/oficiales/{anio}", response_model=list[e.Festivo])
def cargar_oficiales(anio: int, sesion: SesionBD):
    """Añade los festivos oficiales que faltan (no borra ni cambia los que hay).
    Devuelve los añadidos."""
    busqueda, municipio = _buscar(anio, sesion)
    nuevos = [
        Festivo(fecha=f.fecha, descripcion=f.descripcion, ambito=f.ambito)
        for f in busqueda.festivos if f.estado == "NUEVO"
    ]
    sesion.add_all(nuevos)
    carga = sesion.get(CargaFestivos, anio) or CargaFestivos(anio=anio)
    if busqueda.festivos:
        carga.calendario = f"oficial:{municipio.ine}"
        carga.completo = busqueda.completo
        carga.cargado_en = datetime.now()
        sesion.add(carga)
    sesion.flush()
    return nuevos
