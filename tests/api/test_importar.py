"""Importar una copia de los datos (sustituye todos los datos)."""

import sqlite3

from fastapi.testclient import TestClient

from turnos.api.app import crear_app
from turnos.datos.bd import inicializar


def _copia(tmp_path, nombre, medicos):
    """Base de datos de otra instalación, con esos médicos."""
    ruta = tmp_path / nombre
    otro = TestClient(crear_app(inicializar(ruta), interfaz=None))
    for i, m in enumerate(medicos):
        otro.post("/api/medicos", json={"nombre": m, "codigo": f"M{i}"})
    return otro.get("/api/copia-de-seguridad").content


def test_importar_sustituye_los_datos_y_guarda_los_anteriores(cliente, medico, motor, tmp_path):
    copia = _copia(tmp_path, "otra.sqlite", ["Dra. Ruiz", "Dr. Sanz"])
    r = cliente.post("/api/importar", content=copia, headers={"content-type": "application/vnd.sqlite3"})
    assert r.status_code == 200, r.text
    assert r.json()["medicos"] == 2 and r.json()["meses"] == 0
    assert [m["nombre"] for m in cliente.get("/api/medicos").json()] == ["Dr. Sanz", "Dra. Ruiz"]
    anterior = r.json()["copia_anterior"]
    assert "antes-de-importar" in anterior
    with sqlite3.connect(anterior) as c:
        assert c.execute("SELECT nombre FROM medico").fetchall() == [("Dra. García",)]
    # La aplicación sigue funcionando con los datos nuevos.
    assert cliente.post("/api/medicos", json={"nombre": "Dr. Nuevo", "codigo": "NUE"}).status_code == 201


def test_importar_rechaza_ficheros_que_no_son_copias(cliente, medico, tmp_path):
    r = cliente.post("/api/importar", content=b"hola")
    assert r.status_code == 422 and "no es una base de datos" in r.json()["detail"]

    otra = tmp_path / "otra.sqlite"
    with sqlite3.connect(otra) as c:
        c.execute("CREATE TABLE cosa (x)")
    r = cliente.post("/api/importar", content=otra.read_bytes())
    assert r.status_code == 422 and "no una copia de turnosMedicos" in r.json()["detail"]

    assert [m["nombre"] for m in cliente.get("/api/medicos").json()] == ["Dra. García"]


def test_importar_una_copia_de_una_version_mas_nueva(cliente, medico, tmp_path):
    ruta = tmp_path / "nueva.sqlite"
    inicializar(ruta).dispose()
    with sqlite3.connect(ruta) as c:
        c.execute("UPDATE alembic_version SET version_num = '9999_futura'")
    r = cliente.post("/api/importar", content=ruta.read_bytes())
    assert r.status_code == 422 and "más reciente" in r.json()["detail"]
    assert [m["nombre"] for m in cliente.get("/api/medicos").json()] == ["Dra. García"]
