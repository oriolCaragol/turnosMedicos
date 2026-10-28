from datetime import date

from sqlalchemy.orm import Session

from turnos.datos.tablas import AsignacionPeriodo, Periodo
from turnos.dominio.modelos import Mitad, OrigenAsignacion


def reglas(vigente_desde: str, minimo=24, maximo=32, **extra) -> dict:
    return {
        "vigente_desde": vigente_desde,
        "elegibilidad": [{"dia_semana": 0, "turno": "MANANA", "valor": "FIJO"}],
        "carga": {"minimo": minimo, "maximo": maximo},
        **extra,
    }


def test_alta_listado_y_modificacion(cliente, medico):
    assert medico["activo"] is True
    cliente.post("/api/medicos", json={"nombre": "Dr. López", "codigo": "LOP", "activo": False})
    nombres = [m["nombre"] for m in cliente.get("/api/medicos").json()]
    assert nombres == ["Dra. García", "Dr. López"]  # activos primero
    r = cliente.put(f"/api/medicos/{medico['id']}", json={"nombre": "Dra. García Ruiz", "codigo": "GAR"})
    assert r.json()["nombre"] == "Dra. García Ruiz"


def test_color(cliente, medico):
    assert medico["color"] is None
    r = cliente.put(f"/api/medicos/{medico['id']}", json={"nombre": "Dra. García", "codigo": "GAR", "color": "#7fc8a9"})
    assert r.json()["color"] == "#7fc8a9"
    malo = cliente.put(f"/api/medicos/{medico['id']}", json={"nombre": "Dra. García", "codigo": "GAR", "color": "verde"})
    assert malo.status_code == 422
    nuevo = cliente.post("/api/medicos", json={"nombre": "Otro", "codigo": "OTR", "color": "#ffcc00"}).json()
    assert nuevo["color"] == "#ffcc00"
    cal = cliente.get("/api/periodos/2026/11").json()
    assert {m["codigo"]: m["color"] for m in cal["medicos"]} == {"GAR": "#7fc8a9", "OTR": "#ffcc00"}


def test_codigo_duplicado(cliente, medico):
    r = cliente.post("/api/medicos", json={"nombre": "Otro", "codigo": "GAR"})
    assert r.status_code == 409
    assert r.json()["detail"] == "Ya hay un médico con ese código"


def test_medico_inexistente(cliente):
    assert cliente.get("/api/medicos/999").status_code == 404
    assert cliente.get("/api/medicos/999/reglas").status_code == 404


def test_borrar(cliente, medico):
    assert cliente.delete(f"/api/medicos/{medico['id']}").status_code == 204
    assert cliente.get("/api/medicos").json() == []


def test_no_se_borra_un_medico_con_turnos(cliente, medico, motor):
    with Session(motor) as s, s.begin():
        periodo = Periodo(anio=2026, mes=11)
        s.add(periodo)
        s.flush()
        s.add(AsignacionPeriodo(
            periodo_id=periodo.id, medico_id=medico["id"], fecha=date(2026, 11, 3),
            mitad=Mitad.M1, origen=OrigenAsignacion.GENERADOR,
        ))
    assert cliente.delete(f"/api/medicos/{medico['id']}").status_code == 409


def test_reglas_por_defecto(cliente, medico):
    r = cliente.get(f"/api/medicos/{medico['id']}/reglas").json()
    assert r["vigente_desde"] is None and r["carga"] is None
    assert len(r["elegibilidad"]) == 10
    assert {c["valor"] for c in r["elegibilidad"]} == {"DISPONIBLE"}


def test_guardar_y_leer_reglas(cliente, medico):
    url = f"/api/medicos/{medico['id']}/reglas"
    datos = reglas(
        "2026-11-01",
        jornadas=[{"dia_semana": 1, "tipo": "MANANA_MAS_MEDIA"}],
        carga_por_turno=[{"turno": "TARDE", "minimo": 4, "maximo": None}],
        preferencias=[{"dia_semana": 4, "turno": "TARDE", "valor": "EVITA"}],
    )
    assert cliente.put(url, json=datos).status_code == 200
    r = cliente.get(url, params={"fecha": "2026-11-15"}).json()
    assert r["vigente_desde"] == "2026-11-01"
    assert r["carga"] == {"minimo": 24, "maximo": 32}
    assert {"dia_semana": 0, "turno": "MANANA", "valor": "FIJO"} in r["elegibilidad"]
    assert r["jornadas"] == [{"dia_semana": 1, "tipo": "MANANA_MAS_MEDIA"}]
    assert r["carga_por_turno"] == [{"turno": "TARDE", "minimo": 4, "maximo": None}]
    assert r["preferencias"] == [{"dia_semana": 4, "turno": "TARDE", "valor": "EVITA"}]


def test_versiones_de_reglas(cliente, medico):
    url = f"/api/medicos/{medico['id']}/reglas"
    cliente.put(url, json=reglas("2026-11-01", jornadas=[{"dia_semana": 1, "tipo": "DOBLE"}]))
    cliente.put(url, json=reglas("2027-01-01", minimo=10, maximo=20))
    antes = cliente.get(url, params={"fecha": "2026-12-15"}).json()
    despues = cliente.get(url, params={"fecha": "2027-02-01"}).json()
    assert antes["carga"]["minimo"] == 24 and antes["jornadas"] != []
    assert despues["carga"]["minimo"] == 10 and despues["jornadas"] == []  # jornada anulada
    assert cliente.get(url, params={"fecha": "2026-10-01"}).json()["carga"] is None
    # Guardar con la misma fecha sustituye esa versión.
    cliente.put(url, json=reglas("2027-01-01", minimo=12, maximo=20))
    assert cliente.get(url, params={"fecha": "2027-02-01"}).json()["carga"]["minimo"] == 12


def test_reglas_sin_carga_se_guardan(cliente, medico):
    """Un médico nuevo conserva su disponibilidad aunque aún no tenga carga."""
    url = f"/api/medicos/{medico['id']}/reglas"
    sin_carga = reglas("2026-11-01")
    del sin_carga["carga"]
    r = cliente.put(url, json=sin_carga)
    assert r.status_code == 200
    assert r.json()["carga"] is None
    assert {"dia_semana": 0, "turno": "MANANA", "valor": "FIJO"} in r.json()["elegibilidad"]
    # Con carga en una versión anterior, guardar sin carga la conserva.
    cliente.put(url, json=reglas("2026-10-01", minimo=8, maximo=10))
    cliente.put(url, json=sin_carga)
    assert cliente.get(url, params={"fecha": "2026-11-15"}).json()["carga"] == {"minimo": 8, "maximo": 10}


def test_reglas_no_validas(cliente, medico):
    url = f"/api/medicos/{medico['id']}/reglas"
    assert cliente.put(url, json=reglas("2026-11-01", minimo=30, maximo=20)).status_code == 422
    dia_malo = reglas("2026-11-01")
    dia_malo["elegibilidad"] = [{"dia_semana": 5, "turno": "MANANA", "valor": "FIJO"}]
    assert cliente.put(url, json=dia_malo).status_code == 422


def test_turno_habitual_se_guarda(cliente, medico):
    url = f"/api/medicos/{medico['id']}/reglas"
    datos = reglas("2026-11-01")
    datos["elegibilidad"] = [{"dia_semana": 2, "turno": "TARDE", "valor": "HABITUAL"}]
    assert cliente.put(url, json=datos).status_code == 200
    leidas = cliente.get(url, params={"fecha": "2026-11-15"}).json()["elegibilidad"]
    assert {"dia_semana": 2, "turno": "TARDE", "valor": "HABITUAL"} in leidas
