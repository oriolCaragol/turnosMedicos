"""El propio servidor (modo servidor): direcciones y QR, copias y certificado de la
autoridad para instalar en los dispositivos (diseño del modo servidor, 7 y 10.2).

Solo se instala en el modo servidor. `app.state.servidor` lo prepara `turnos.red.orden`.
"""

import io
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from turnos.api import esquemas as e
from turnos.red import certificados, copias
from turnos.red.configuracion import ConfigServidor


@dataclass
class EstadoServidor:
    config: ConfigServidor
    ficheros: certificados.Ficheros | None  # None sin HTTPS
    direcciones: list[str] = field(default_factory=list)  # https://turnos.local:8443/, https://192.168.1.50:8443/…


router = APIRouter(prefix="/api/servidor", tags=["servidor"])


def _estado(request: Request) -> EstadoServidor:
    return request.app.state.servidor


@router.get("/publico", response_model=e.ServidorPublico)
def publico(request: Request):
    estado = _estado(request)
    return {"nombre": "Turnos médicos", "https": estado.config.https, "hay_certificado": estado.ficheros is not None}


@router.get("", response_model=e.InfoServidor)
def informacion(request: Request):
    estado = _estado(request)
    huella = caduca = None
    if estado.ficheros is not None:
        huella = certificados.huella(certificados.leer_certificado(estado.ficheros.autoridad))
        caduca = certificados.leer_certificado(estado.ficheros.servidor).not_valid_after_utc.replace(tzinfo=None)
    return {
        "nombre": "Turnos médicos", "https": estado.config.https, "hay_certificado": estado.ficheros is not None,
        "direcciones": estado.direcciones, "huella_autoridad": huella, "certificado_caduca": caduca,
        "datos": str(estado.config.datos), "conservar_copias": estado.config.conservar_copias,
        "copias": [{"nombre": c.ruta.name, "tamano": c.tamano, "fecha": c.fecha} for c in copias.listar(estado.config.copias)],
    }


@router.get("/qr.svg", response_class=Response)
def qr(request: Request, direccion: str):
    """Código QR de una de las direcciones del servidor (para abrirla desde el móvil)."""
    if direccion not in _estado(request).direcciones:
        raise HTTPException(404, "No es una dirección de este servidor")
    import segno

    salida = io.BytesIO()
    segno.make(direccion, error="m").save(salida, kind="svg", scale=6, border=2, dark="#1c1c1c", light="#ffffff")
    return Response(salida.getvalue(), media_type="image/svg+xml")


@router.post("/copias", response_model=e.CopiaServidor, status_code=201)
async def copiar(request: Request):
    """Copia de seguridad inmediata (además de la diaria)."""
    config = _estado(request).config
    ruta: Path = await run_in_threadpool(copias.copiar_ahora, config.datos, config.copias)
    return {"nombre": ruta.name, "tamano": ruta.stat().st_size,
            "fecha": copias.listar(config.copias)[0].fecha}


def instalar(app: FastAPI, estado: EstadoServidor) -> None:
    app.state.servidor = estado
    app.include_router(router)

    # Fuera de /api: se descargan sin sesión, desde la página de entrada.
    @app.get("/certificado/turnos-autoridad.crt", include_in_schema=False)
    def autoridad_der():
        if estado.ficheros is None:
            raise HTTPException(404, "Este servidor no usa HTTPS")
        return Response(certificados.autoridad_der(estado.ficheros), media_type="application/x-x509-ca-cert",
                        headers={"Content-Disposition": 'attachment; filename="turnos-autoridad.crt"'})

    @app.get("/certificado/turnos-autoridad.pem", include_in_schema=False)
    def autoridad_pem():
        if estado.ficheros is None:
            raise HTTPException(404, "Este servidor no usa HTTPS")
        return Response(estado.ficheros.autoridad.read_bytes(), media_type="application/x-pem-file",
                        headers={"Content-Disposition": 'attachment; filename="turnos-autoridad.pem"'})

    @app.get("/certificado/turnos.mobileconfig", include_in_schema=False)
    def perfil():
        if estado.ficheros is None:
            raise HTTPException(404, "Este servidor no usa HTTPS")
        return Response(certificados.perfil_ios(estado.ficheros), media_type="application/x-apple-aspen-config",
                        headers={"Content-Disposition": 'attachment; filename="turnos.mobileconfig"'})
