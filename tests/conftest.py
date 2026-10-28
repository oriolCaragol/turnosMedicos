"""Preparaciones comunes a varias carpetas de pruebas."""

import json
import socket
import ssl
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass
class ServidorRed:
    """Un `turnos servidor` real (HTTPS) para probar los clientes contra él."""

    base: str  # https://localhost:<puerto>
    datos: Path
    autoridad: Path
    proceso: subprocess.Popen
    _token: str | None = None

    def contexto(self) -> ssl.SSLContext:
        return ssl.create_default_context(cafile=str(self.autoridad))

    def pedir(self, metodo: str, ruta: str, cuerpo=None, usuario=("admin", "contrasena-admin")):
        """Petición a la API como `usuario` (por defecto, el administrador)."""
        if self._token is None or usuario != ("admin", "contrasena-admin"):
            token = self._entrar(*usuario)
            if usuario == ("admin", "contrasena-admin"):
                self._token = token
        else:
            token = self._token
        peticion = urllib.request.Request(
            f"{self.base}/api{ruta}", method=metodo, data=None if cuerpo is None else json.dumps(cuerpo).encode(),
            headers={"Authorization": f"Bearer {token}", "X-Cliente": "pruebas", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(peticion, context=self.contexto(), timeout=60) as r:
            contenido = r.read()
        return json.loads(contenido) if contenido else None

    def _entrar(self, usuario: str, contrasena: str) -> str:
        peticion = urllib.request.Request(
            f"{self.base}/api/sesion", method="POST",
            data=json.dumps({"usuario": usuario, "contrasena": contrasena, "aplicacion": True}).encode(),
            headers={"Content-Type": "application/json", "X-Cliente": "pruebas"},
        )
        with urllib.request.urlopen(peticion, context=self.contexto(), timeout=30) as r:
            return json.load(r)["token"]


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def servidor_red(tmp_path):
    """Servidor con un administrador, un planificador («plani») y un equipo de 4 médicos
    (Ana tiene cuenta de médico, «ana»), con reglas desde noviembre de 2026."""
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from turnos.api.app import crear_app
    from turnos.api.rutas.servidor import EstadoServidor
    from turnos.datos.bd import inicializar
    from turnos.red.configuracion import ConfigServidor
    from turnos.servicios import usuarios

    datos = tmp_path / "servidor" / "turnos.sqlite"
    datos.parent.mkdir()
    motor = inicializar(datos, wal=True)
    with Session(motor) as sesion, sesion.begin():
        usuarios.crear_usuario(sesion, "admin", "Administración", "ADMINISTRADOR", "contrasena-admin")
        usuarios.crear_usuario(sesion, "plani", "Pablo Planificador", "PLANIFICADOR", "contrasena-plani")
    app = crear_app(motor, interfaz=None, servidor=EstadoServidor(ConfigServidor(datos=datos, https=False), None))
    api = TestClient(app, headers={"X-Cliente": "pruebas"})
    api.post("/api/sesion", json={"usuario": "admin", "contrasena": "contrasena-admin"})
    api.put("/api/ajustes", json={"todos_trabajan": False})
    ids = []
    for nombre, codigo in [("Ana Ruiz", "ANA"), ("Bea Gil", "BEA"), ("Carlos Paz", "CAR"), ("Dani Sanz", "DAN")]:
        m = api.post("/api/medicos", json={"nombre": nombre, "codigo": codigo}).json()
        ids.append(m["id"])
        api.put(f"/api/medicos/{m['id']}/reglas", json={
            "vigente_desde": "2026-11-01", "elegibilidad": [], "carga": {"minimo": 0, "maximo": 40}})
    api.put("/api/cobertura/semanal", json=[
        {"dia_semana": d, "mitad": h, "minimo": 1, "maximo": 1} for d in range(5) for h in ("M1", "M2", "T1", "T2")])
    with Session(motor) as sesion, sesion.begin():
        usuarios.crear_usuario(sesion, "ana", "Ana Ruiz", "MEDICO", "contrasena-ana", medico_id=ids[0])
    motor.dispose()

    puerto = _puerto_libre()
    proceso = subprocess.Popen(
        [sys.executable, "-m", "turnos", "servidor", "--datos", str(datos), "--puerto", str(puerto), "--sin-anuncio"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    autoridad = datos.parent / "certificados" / "autoridad.crt"
    servidor = ServidorRed(f"https://localhost:{puerto}", datos, autoridad, proceso)
    for _ in range(150):
        try:
            with urllib.request.urlopen(f"{servidor.base}/api/servidor/publico", context=servidor.contexto(), timeout=2):
                break
        except (OSError, ssl.SSLError):
            time.sleep(0.1)
    else:
        proceso.kill()
        pytest.fail("El servidor no arrancó: " + proceso.stdout.read())
    yield servidor
    proceso.terminate()
    try:
        proceso.wait(10)
    except subprocess.TimeoutExpired:
        proceso.kill()
