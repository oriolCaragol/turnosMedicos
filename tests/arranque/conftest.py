import pytest
from fastapi.testclient import TestClient

from turnos.api.app import crear_app
from turnos.datos.bd import inicializar


@pytest.fixture
def motor(tmp_path):
    return inicializar(tmp_path / "turnos.sqlite")


@pytest.fixture
def cliente(motor):
    return TestClient(crear_app(motor, interfaz=None))
