"""Apoyo de las pruebas del modo servidor (los fixtures están en conftest.py)."""

from fastapi.testclient import TestClient

URL = "/api/periodos/2026/11"


def entrar(app, nombre, contrasena) -> TestClient:
    cliente = TestClient(app, headers={"X-Cliente": "pruebas"})
    r = cliente.post("/api/sesion", json={"usuario": nombre, "contrasena": contrasena})
    assert r.status_code == 200, r.text
    return cliente


def cuenta_medico(servidor, admin, medico_id, nombre="ana") -> TestClient:
    """Crea la cuenta (contraseña temporal), entra y elige la suya."""
    r = admin.post("/api/usuarios", json={"nombre": nombre, "nombre_visible": "Ana", "rol": "MEDICO",
                                          "medico_id": medico_id})
    assert r.status_code == 201, r.text
    cliente = entrar(servidor, nombre, r.json()["contrasena_temporal"])
    temporal = r.json()["contrasena_temporal"]
    assert cliente.post("/api/yo/contrasena", json={"actual": temporal, "nueva": "contrasena-ana"}).status_code == 204
    return cliente
