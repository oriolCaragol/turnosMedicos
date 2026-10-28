"""Sesión con token (diseño del modo escritorio, 7)."""

import pytest
from fastapi.testclient import TestClient

from turnos.api.app import crear_app

TOKEN = "secreto-de-prueba"


@pytest.fixture
def protegido(motor, tmp_path):
    (tmp_path / "interfaz" / "assets").mkdir(parents=True)
    (tmp_path / "interfaz" / "index.html").write_text("<html>turnos</html>")
    app = crear_app(motor, interfaz=tmp_path / "interfaz", token=TOKEN, nombre_cookie="turnos_sesion_1234")
    return TestClient(app)


def test_api_sin_sesion_responde_401(protegido):
    respuesta = protegido.get("/api/medicos")
    assert respuesta.status_code == 401
    assert "Sesión no válida" in respuesta.json()["detail"]


def test_token_en_la_direccion_deja_cookie_y_redirige(protegido):
    respuesta = protegido.get("/calendario?vista=lista&token=" + TOKEN, follow_redirects=False)
    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/calendario?vista=lista"
    cookie = respuesta.headers["set-cookie"]
    assert cookie.startswith("turnos_sesion_1234=" + TOKEN)
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert protegido.get("/api/medicos").status_code == 200


def test_token_incorrecto_no_abre_sesion(protegido):
    respuesta = protegido.get("/?token=otro", follow_redirects=False)
    assert respuesta.status_code == 401
    assert "set-cookie" not in respuesta.headers
    assert protegido.get("/api/medicos").status_code == 401


def test_cabecera_con_el_token(protegido):
    assert protegido.get("/api/medicos", headers={"X-Turnos-Token": TOKEN}).status_code == 200
    assert protegido.get("/api/medicos", headers={"X-Turnos-Token": "no"}).status_code == 401


def test_cookie_de_otro_puerto_no_vale(protegido):
    protegido.cookies.set("turnos_sesion_9999", TOKEN)
    assert protegido.get("/api/medicos").status_code == 401


def test_la_interfaz_se_sirve_sin_sesion(protegido):
    """La página carga (mostraría el aviso de sesión); solo los datos están protegidos."""
    assert protegido.get("/").status_code == 200


def test_sin_token_no_se_protege(cliente):
    assert cliente.get("/api/medicos").status_code == 200
