"""Varios clientes a la vez: versión del mes, cerrojo, registro de cambios y eventos
(diseño del modo servidor, 6.2, 8 y 9)."""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from turnos.arranque.servidor import preparar
from turnos.datos.bd import inicializar
from turnos.servicios.periodos import GENERANDO

URL = "/api/periodos/2026/11"


def test_la_version_del_mes_sube_con_cada_cambio(cliente, equipo):
    assert cliente.get(URL).json()["version"] == 0
    cal = cliente.post(f"{URL}/generar", json={}).json()
    assert cal["version"] == 1
    a = cal["asignaciones"][0]
    cal = cliente.post(f"{URL}/cambios", json=[{"medico_id": a["medico_id"], "fecha": a["fecha"], "bloqueada": True}]).json()
    assert cal["version"] == 2
    assert cliente.post(f"{URL}/publicar").json()["version"] == 3
    assert cliente.get(URL).json()["version"] == 3


def test_una_version_antigua_se_rechaza_sin_cambiar_nada(cliente, equipo):
    cal = cliente.post(f"{URL}/generar", json={}).json()
    a = cal["asignaciones"][0]
    cambio = [{"medico_id": a["medico_id"], "fecha": a["fecha"], "mitades": []}]
    r = cliente.post(f"{URL}/cambios", json=cambio, headers={"X-Version-Mes": "0"})  # la de antes de generar
    assert r.status_code == 409
    assert "Otro usuario ha cambiado el calendario" in r.json()["detail"]
    assert r.headers["X-Version-Mes"] == "1"
    assert cliente.get(URL).json()["asignaciones"] == cal["asignaciones"]
    # Con la versión correcta, sí.
    r = cliente.post(f"{URL}/cambios", json=cambio, headers={"X-Version-Mes": "1"})
    assert r.status_code == 200 and r.json()["version"] == 2


def test_sin_version_funciona_como_antes(cliente, equipo):
    assert cliente.post(f"{URL}/generar", json={}).status_code == 200
    assert cliente.post(f"{URL}/generar", json={"alternativa": True}).status_code == 200


def test_mientras_se_genera_otro_recibe_un_aviso(cliente, equipo):
    GENERANDO.add((2026, 11))
    try:
        r = cliente.post(f"{URL}/generar", json={})
        assert r.status_code == 409 and "Se está generando" in r.json()["detail"]
        assert cliente.post("/api/periodos/2026/12/generar", json={}).status_code == 200  # otro mes, sí
    finally:
        GENERANDO.discard((2026, 11))


def test_registro_de_cambios(cliente, equipo):
    cliente.post(f"{URL}/generar", json={})
    cliente.post(f"{URL}/publicar")
    cliente.post(f"{URL}/generar", json={})  # publicado: 409, no se registra
    cliente.put("/api/ajustes", json={"todos_trabajan": True, "roles_segun_presencia": True, "mostrar_cobertura": False,
                                      "municipio": "28079"})
    registro = cliente.get("/api/registro").json()
    assert [r["accion"] for r in registro[:3]] == ["Ajustes generales", "Publicar", "Generar el calendario"]
    assert registro[1]["ruta"] == "POST /api/periodos/2026/11/publicar"
    assert (registro[1]["anio"], registro[1]["mes"]) == (2026, 11)
    acciones = [r["accion"] for r in registro]
    assert "Alta de un médico" in acciones and "Reglas de un médico" in acciones and "Cobertura" in acciones


def test_wal_solo_si_se_pide(tmp_path):
    for wal, esperado in ((False, "delete"), (True, "wal")):
        motor = inicializar(tmp_path / f"{esperado}.sqlite", wal=wal)
        with motor.connect() as conexion:
            assert conexion.exec_driver_sql("PRAGMA journal_mode").scalar() == esperado
        motor.dispose()


# --- Con un servidor de verdad ---------------------------------------------------------


@pytest.fixture
def servidor(tmp_path):
    srv = preparar(ruta=tmp_path / "turnos.sqlite", con_token=False)
    srv.iniciar_en_hilo()
    yield srv
    srv.detener()


def _pedir(srv, metodo, ruta, cuerpo=None, cabeceras=None):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    peticion = urllib.request.Request(f"http://127.0.0.1:{srv.puerto}{ruta}", data=datos, method=metodo,
                                      headers={"Content-Type": "application/json", **(cabeceras or {})})
    try:
        with urllib.request.urlopen(peticion, timeout=30) as r:
            return r.status, json.loads(r.read() or "null")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or "null")


def _equipo(srv):
    for i, nombre in enumerate(["Ana", "Bea", "Carlos", "Dani"]):
        _, m = _pedir(srv, "POST", "/api/medicos", {"nombre": nombre, "codigo": f"M{i}"})
        _pedir(srv, "PUT", f"/api/medicos/{m['id']}/reglas",
               {"vigente_desde": "2026-11-01", "elegibilidad": [], "carga": {"minimo": 0, "maximo": 40}})
    _pedir(srv, "PUT", "/api/cobertura/semanal",
           [{"dia_semana": d, "mitad": h, "minimo": 1, "maximo": 2} for d in range(5) for h in ("M1", "M2", "T1", "T2")])


def test_dos_clientes_a_la_vez_con_la_misma_version_solo_gana_uno(servidor):
    _equipo(servidor)
    _, cal = _pedir(servidor, "POST", f"{URL}/generar", {})
    a, b = cal["asignaciones"][0], cal["asignaciones"][-1]
    resultados = []
    salida = threading.Barrier(2)

    def cambiar(asig):
        salida.wait()
        resultados.append(_pedir(servidor, "POST", f"{URL}/cambios",
                                 [{"medico_id": asig["medico_id"], "fecha": asig["fecha"], "mitades": []}],
                                 {"X-Version-Mes": str(cal["version"])})[0])

    hilos = [threading.Thread(target=cambiar, args=(x,)) for x in (a, b)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert sorted(resultados) == [200, 409]
    assert _pedir(servidor, "GET", URL)[1]["version"] == cal["version"] + 1


def _leer_eventos(srv, cuantos, al_conectar):
    """Abre /api/eventos, ejecuta `al_conectar` y devuelve los `cuantos` primeros eventos."""
    respuesta = urllib.request.urlopen(f"http://127.0.0.1:{srv.puerto}/api/eventos", timeout=10)
    assert respuesta.readline().startswith(b"retry:")
    respuesta.readline()
    al_conectar()
    eventos = []
    while len(eventos) < cuantos:
        linea = respuesta.readline().decode().strip()
        if linea.startswith("data: "):
            eventos.append(json.loads(linea[6:]))
    respuesta.close()
    return eventos


def test_los_cambios_llegan_como_eventos_con_su_origen(servidor):
    _equipo(servidor)

    def cambios():
        _pedir(servidor, "POST", f"{URL}/generar", {}, {"X-Cliente": "pestaña-1"})
        _pedir(servidor, "PUT", "/api/ajustes", {"todos_trabajan": False, "roles_segun_presencia": True,
                                                 "mostrar_cobertura": False, "municipio": "28079"})
        _pedir(servidor, "POST", "/api/periodos/2026/11/publicar", None, {"X-Version-Mes": "99"})  # 409: sin evento
        _pedir(servidor, "POST", "/api/medicos", {"nombre": "Eva", "codigo": "EVA"})

    eventos = _leer_eventos(servidor, 3, cambios)
    assert eventos == [
        {"tipo": "calendario", "anio": 2026, "mes": 11, "origen": "pestaña-1"},
        {"tipo": "configuracion", "origen": None},
        {"tipo": "medicos", "origen": None},
    ]


def test_detener_no_espera_a_los_clientes_conectados(tmp_path):
    srv = preparar(ruta=tmp_path / "t.sqlite", con_token=False)
    srv.iniciar_en_hilo()
    conexion = urllib.request.urlopen(f"http://127.0.0.1:{srv.puerto}/api/eventos", timeout=10)
    conexion.readline()
    inicio = time.monotonic()
    srv.detener()
    assert time.monotonic() - inicio < 3
    conexion.close()
