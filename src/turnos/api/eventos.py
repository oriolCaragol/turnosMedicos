"""Eventos en vivo (Server-Sent Events) y registro de cambios (diseño del modo servidor, 6.2 y 9).

Cada petición que modifica datos con éxito deja una fila en el registro de cambios
(en la misma transacción) y, una vez confirmada, produce un evento breve, por ejemplo
`{"tipo": "calendario", "anio": 2026, "mes": 11, "origen": "…"}`, que reciben todos
los clientes conectados a `GET /api/eventos` para volver a pedir lo que ha cambiado.
`origen` es el identificador del cliente que hizo el cambio (cabecera X-Cliente),
para que cada cliente distinga sus cambios de los de otros. Lo hace la sesión de
base de datos de cada petición (`api/dependencias.py`), que es quien sabe cuándo se
han confirmado los datos."""

import asyncio
import json
import re
from datetime import datetime

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from turnos.datos.tablas import RegistroCambio

router = APIRouter(tags=["eventos"])
LATIDO = 15.0  # segundos: mantiene viva la conexión y detecta clientes que se han ido


class Difusor:
    """Reparte los eventos a todos los clientes conectados."""

    def __init__(self) -> None:
        self._colas: set[asyncio.Queue] = set()
        self._bucle: asyncio.AbstractEventLoop | None = None
        self.cerrado = False

    @property
    def conectados(self) -> int:
        return len(self._colas)

    def suscribir(self) -> asyncio.Queue:
        self._bucle = asyncio.get_running_loop()
        cola: asyncio.Queue = asyncio.Queue()
        self._colas.add(cola)
        return cola

    def baja(self, cola: asyncio.Queue) -> None:
        self._colas.discard(cola)

    def publicar(self, evento: dict | None) -> None:
        """Se puede llamar desde cualquier hilo (las rutas síncronas van en hilos)."""
        if self._bucle is None or self._bucle.is_closed():
            return  # nadie se ha conectado todavía
        for cola in list(self._colas):
            self._bucle.call_soon_threadsafe(cola.put_nowait, evento)

    def cerrar(self) -> None:
        """Termina todas las conexiones (al parar el servidor, para no esperarlas)."""
        self.cerrado = True
        self.publicar(None)


@router.get("/api/eventos")
async def eventos(request: Request):
    difusor: Difusor = request.app.state.difusor
    cola = difusor.suscribir()

    async def flujo():
        try:
            yield "retry: 3000\n\n"
            while not difusor.cerrado:
                try:
                    evento = await asyncio.wait_for(cola.get(), timeout=LATIDO)
                except TimeoutError:
                    yield ": latido\n\n"
                    continue
                if evento is None:
                    break
                yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"
        finally:
            difusor.baja(cola)

    return StreamingResponse(
        flujo(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


# --- Qué ha cambiado ---------------------------------------------------------------

_MES = re.compile(r"^/api/periodos/(\d{4})/(\d{1,2})(?:/([a-z-]+))?")
_ACCIONES_MES = {
    "generar": "Generar el calendario", "cambios": "Cambio manual", "liberar": "Volver a automático",
    "manual": "Deshacer o rehacer", "carga": "Rango del mes de un médico", "publicar": "Publicar", "reabrir": "Reabrir",
}
_RECURSOS = [  # (prefijo, tipo del evento, acción para el registro)
    ("/api/medicos", "medicos", None),
    ("/api/ausencias", "ausencias", "Ausencia"),
    ("/api/festivos", "festivos", "Festivos"),
    ("/api/cobertura", "cobertura", "Cobertura"),
    ("/api/ajustes", "configuracion", "Ajustes generales"),
    ("/api/horarios", "configuracion", "Horario de los turnos"),
    ("/api/rotaciones", "rotaciones", "Turnos rotativos"),
    ("/api/importar", "todo", "Importar una copia de los datos"),
    ("/api/solicitudes", "solicitudes", None),
]
_ACCIONES_SOLICITUD = {
    "": "Solicitud nueva", "retirar": "Retirar una solicitud", "aceptar": "Respuesta a un intercambio",
    "aprobar": "Aprobar una solicitud", "rechazar": "Rechazar una solicitud",
}


def clasificar(metodo: str, ruta: str) -> tuple[dict, str] | None:
    """(evento, acción para el registro) de una petición que modifica datos."""
    if (m := _MES.match(ruta)) is not None:
        anio, mes, accion = int(m.group(1)), int(m.group(2)), m.group(3) or ""
        return {"tipo": "calendario", "anio": anio, "mes": mes}, _ACCIONES_MES.get(accion, "Calendario")
    for prefijo, tipo, accion in _RECURSOS:
        if ruta.startswith(prefijo):
            if tipo == "solicitudes":
                accion = _ACCIONES_SOLICITUD.get(ruta.rstrip("/").split("/")[-1] if ruta.count("/") > 3 else "",
                                                 "Solicitud")
            if tipo == "medicos":
                accion = ("Reglas de un médico" if ruta.endswith("/reglas")
                          else {"POST": "Alta de un médico", "DELETE": "Baja de un médico"}.get(metodo, "Datos de un médico"))
            return {"tipo": tipo}, accion
    return None


def instalar(app: FastAPI) -> None:
    """Difusor y ruta de los eventos."""
    app.state.difusor = Difusor()
    app.include_router(router)


def usuario_de(request: Request) -> str | None:
    """Nombre del usuario de la petición (en el modo personal no hay: None)."""
    datos = getattr(request.state, "usuario", None)
    return datos["nombre"] if datos else None


def registrar(sesion: Session, request: Request) -> dict | None:
    """Anota el cambio en el registro (dentro de la transacción de la petición) y
    devuelve el evento que hay que publicar cuando se confirme."""
    clase = clasificar(request.method, request.url.path)
    if clase is None:
        return None
    evento, accion = clase
    evento["origen"] = request.headers.get("x-cliente")
    sesion.add(RegistroCambio(
        momento=datetime.now(), usuario=usuario_de(request), accion=accion, ruta=f"{request.method} {request.url.path}",
        anio=evento.get("anio"), mes=evento.get("mes"),
    ))
    return evento
