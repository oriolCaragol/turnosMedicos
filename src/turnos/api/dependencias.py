"""Dependencias comunes de las rutas."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from turnos.api import eventos

METODOS_DE_LECTURA = {"GET", "HEAD", "OPTIONS"}


def _sesion(request: Request) -> Iterator[Session]:
    """Una sesión por petición, en una transacción que se confirma al terminar.

    Las peticiones que escriben se hacen de una en una (cerrojo de la aplicación):
    con varios clientes a la vez, dos escrituras no pueden leer el mismo estado y
    pisarse, y SQLite no tiene que reintentar. Las lecturas no esperan."""
    escribe = request.method not in METODOS_DE_LECTURA
    cerrojo = request.app.state.cerrojo_escritura
    if escribe:
        cerrojo.acquire()
    try:
        evento = None
        with Session(request.app.state.motor) as sesion:
            with sesion.begin():
                yield sesion
                # Solo si la ruta ha terminado bien (si no, la excepción llega aquí y se deshace todo).
                if escribe:
                    evento = eventos.registrar(sesion, request)
            if evento is not None:  # ya confirmado: los demás clientes pueden volver a pedir los datos
                request.app.state.difusor.publicar(evento)
                # Otros datos que ha cambiado la ruta (p. ej. aprobar una solicitud cambia el
                # calendario): para todos, también para quien la hizo (sin origen).
                for extra in getattr(request.state, "eventos", []):
                    request.app.state.difusor.publicar({**extra, "origen": None})
    finally:
        if escribe:
            cerrojo.release()


SesionBD = Annotated[Session, Depends(_sesion)]

# Versión del mes que conoce el cliente: si otro usuario lo ha cambiado desde entonces,
# la operación se rechaza con 409 (diseño del modo servidor, 8). Opcional.
VersionMes = Annotated[int | None, Header(alias="X-Version-Mes")]


def obtener_o_404[T](sesion: Session, tabla: type[T], id_: object, nombre: str) -> T:
    fila = sesion.get(tabla, id_)
    if fila is None:
        raise HTTPException(404, f"{nombre} no encontrado")
    return fila
