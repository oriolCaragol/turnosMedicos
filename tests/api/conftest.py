import pytest
from apoyo_servidor import URL, entrar
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from turnos.api import acceso
from turnos.api.app import crear_app
from turnos.api.rutas.servidor import EstadoServidor
from turnos.datos.bd import inicializar
from turnos.red.configuracion import ConfigServidor
from turnos.servicios import usuarios


@pytest.fixture
def motor(tmp_path):
    return inicializar(tmp_path / "turnos.sqlite")


@pytest.fixture
def cliente(motor):
    return TestClient(crear_app(motor, interfaz=None))


@pytest.fixture
def medico(cliente):
    respuesta = cliente.post("/api/medicos", json={"nombre": "Dra. García", "codigo": "GAR"})
    assert respuesta.status_code == 201
    return respuesta.json()


def sin_festivo_local_de_noviembre(cliente) -> None:
    """Las pruebas de calendario usan noviembre de 2026 con un solo festivo entre semana
    (el lunes 2): sin el festivo local de Madrid del lunes 9 (la Almudena), que traen los
    precargados. Sus festivos se comprueban en tests/recursos/test_festivos.py."""
    for f in cliente.get("/api/festivos", params={"anio": 2026}).json():
        if f["fecha"] == "2026-11-09":
            assert cliente.delete(f"/api/festivos/{f['id']}").status_code == 204


@pytest.fixture
def equipo(cliente):
    """4 médicos con reglas desde noviembre y cobertura de 1 médico por turno.

    Sin la opción «todos trabajan cada día» (con 4 médicos y 1 por turno chocaría
    con la cobertura máxima); las pruebas de esa opción la activan."""
    sin_festivo_local_de_noviembre(cliente)
    cliente.put("/api/ajustes", json={"todos_trabajan": False})
    ids = []
    for nombre, codigo in [("Ana", "ANA"), ("Bea", "BEA"), ("Carlos", "CAR"), ("Dani", "DAN")]:
        m = cliente.post("/api/medicos", json={"nombre": nombre, "codigo": codigo}).json()
        ids.append(m["id"])
        eleg = [{"dia_semana": 0, "turno": "MANANA", "valor": "FIJO"}] if codigo == "ANA" else []
        cliente.put(f"/api/medicos/{m['id']}/reglas", json={
            "vigente_desde": "2026-11-01", "elegibilidad": eleg, "carga": {"minimo": 0, "maximo": 40},
        })
    cobertura = [
        {"dia_semana": d, "mitad": h, "minimo": 1, "maximo": 1}
        for d in range(5) for h in ("M1", "M2", "T1", "T2")
    ]
    cliente.put("/api/cobertura/semanal", json=cobertura)
    return ids


# --- Modo servidor (test_acceso.py, test_solicitudes.py) --------------------------------


@pytest.fixture(autouse=True)
def _sin_limites():
    """Cada prueba empieza sin intentos fallidos de inicio de sesión anotados."""
    acceso.limite_usuario._fallos.clear()
    acceso.limite_direccion._fallos.clear()


@pytest.fixture
def servidor(tmp_path):
    """La aplicación en el modo servidor (sin HTTPS), con un administrador y un planificador."""
    motor = inicializar(tmp_path / "turnos.sqlite", wal=True)
    config = ConfigServidor(datos=tmp_path / "turnos.sqlite", https=False)
    app = crear_app(motor, interfaz=None, servidor=EstadoServidor(config, None, ["http://turnos.local:8443/"]))
    with Session(motor) as sesion, sesion.begin():
        usuarios.crear_usuario(sesion, "admin", "Administración", "ADMINISTRADOR", "contrasena-admin")
        usuarios.crear_usuario(sesion, "plani", "Planificación", "PLANIFICADOR", "contrasena-plani")
    return app


@pytest.fixture
def admin(servidor):
    return entrar(servidor, "admin", "contrasena-admin")


@pytest.fixture
def plani(servidor):
    return entrar(servidor, "plani", "contrasena-plani")


@pytest.fixture
def equipo_servidor(admin):
    """Equipo de 4 médicos con noviembre generado (sin publicar)."""
    sin_festivo_local_de_noviembre(admin)
    admin.put("/api/ajustes", json={"todos_trabajan": False})
    ids = []
    for nombre, codigo in [("Ana", "ANA"), ("Bea", "BEA"), ("Carlos", "CAR"), ("Dani", "DAN")]:
        m = admin.post("/api/medicos", json={"nombre": nombre, "codigo": codigo}).json()
        ids.append(m["id"])
        admin.put(f"/api/medicos/{m['id']}/reglas", json={
            "vigente_desde": "2026-11-01", "elegibilidad": [], "carga": {"minimo": 0, "maximo": 40}})
    admin.put("/api/cobertura/semanal", json=[
        {"dia_semana": d, "mitad": h, "minimo": 1, "maximo": 1} for d in range(5) for h in ("M1", "M2", "T1", "T2")])
    assert admin.post(f"{URL}/generar", json={}).status_code == 200
    return ids
