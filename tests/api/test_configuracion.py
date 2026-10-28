from pathlib import Path

from fastapi.testclient import TestClient

from turnos.api.app import crear_app


# --- Ausencias -------------------------------------------------------------------


def test_ausencias(cliente, medico):
    datos = {"medico_id": medico["id"], "desde": "2026-11-10", "hasta": "2026-11-13"}
    creada = cliente.post("/api/ausencias", json=datos).json()
    cliente.post("/api/ausencias", json={**datos, "desde": "2026-12-01", "hasta": "2026-12-02",
                                         "turno": "TARDE"})
    noviembre = cliente.get("/api/ausencias", params={"desde": "2026-11-01", "hasta": "2026-11-30"})
    assert [a["id"] for a in noviembre.json()] == [creada["id"]]
    assert len(cliente.get("/api/ausencias", params={"medico_id": medico["id"]}).json()) == 2
    modificada = cliente.put(f"/api/ausencias/{creada['id']}", json={**datos, "turno": "MANANA"})
    assert modificada.json()["turno"] == "MANANA"
    assert cliente.delete(f"/api/ausencias/{creada['id']}").status_code == 204


def test_ausencia_no_valida(cliente, medico):
    invertida = {"medico_id": medico["id"], "desde": "2026-11-13", "hasta": "2026-11-10"}
    assert cliente.post("/api/ausencias", json=invertida).status_code == 422
    sin_medico = {"medico_id": 999, "desde": "2026-11-10", "hasta": "2026-11-13"}
    assert cliente.post("/api/ausencias", json=sin_medico).status_code == 404


# --- Festivos --------------------------------------------------------------------


def test_festivos_precargados(cliente):
    assert len(cliente.get("/api/festivos", params={"anio": 2026}).json()) == 14
    anios = {a["anio"]: a["completo"] for a in cliente.get("/api/festivos/anios").json()}
    assert anios[2026] is True and anios[2027] is False


def test_alta_baja_y_restaurar_festivos(cliente):
    nuevo = cliente.post("/api/festivos", json={"fecha": "2026-12-24", "descripcion": "Nochebuena"})
    assert nuevo.status_code == 201
    duplicado = cliente.post("/api/festivos", json={"fecha": "2026-12-24", "descripcion": "Otra"})
    assert duplicado.status_code == 409

    festivos = cliente.get("/api/festivos", params={"anio": 2026}).json()
    local = next(f for f in festivos if f["fecha"] == "2026-05-15")
    assert cliente.delete(f"/api/festivos/{local['id']}").status_code == 204
    restaurados = cliente.post("/api/festivos/restaurar/2026").json()
    assert [f["fecha"] for f in restaurados] == ["2026-05-15"]
    assert cliente.post("/api/festivos/restaurar/2030").status_code == 404


# --- Cobertura -------------------------------------------------------------------


def test_cobertura_semanal(cliente):
    inicial = cliente.get("/api/cobertura/semanal").json()
    assert len(inicial) == 20 and all(c["minimo"] == 0 for c in inicial)
    datos = [{**c, "minimo": 3, "maximo": 4} for c in inicial]
    guardada = cliente.put("/api/cobertura/semanal", json=datos).json()
    assert all((c["minimo"], c["maximo"]) == (3, 4) for c in guardada)
    malo = [{**datos[0], "minimo": 5, "maximo": 4}]
    assert cliente.put("/api/cobertura/semanal", json=malo).status_code == 422


def test_cobertura_por_fecha(cliente):
    mitades = [{"mitad": m, "minimo": 1, "maximo": 1} for m in ("M1", "M2", "T1", "T2")]
    r = cliente.put("/api/cobertura/fechas/2026-12-24", json=mitades)
    assert len(r.json()) == 4
    assert cliente.put("/api/cobertura/fechas/2026-12-24", json=mitades[:2]).status_code == 422
    assert len(cliente.get("/api/cobertura/fechas", params={"desde": "2026-12-01"}).json()) == 4
    cliente.delete("/api/cobertura/fechas/2026-12-24")
    assert cliente.get("/api/cobertura/fechas").json() == []


# --- Horarios y estado -----------------------------------------------------------


def test_horarios(cliente):
    horarios = cliente.get("/api/horarios").json()
    assert [h["turno"] for h in horarios] == ["MANANA", "TARDE"]
    horarios[0]["corte"] = "11:00:00"
    assert cliente.put("/api/horarios", json=horarios).json()[0]["corte"] == "11:00:00"
    horarios[0]["corte"] = "16:00:00"
    assert cliente.put("/api/horarios", json=horarios).status_code == 422


def test_estado(cliente, medico):
    estado = cliente.get("/api/estado").json()
    assert estado["mes"].endswith("-01")
    assert estado["anios_festivos_incompletos"] == [2027]
    assert [m["codigo"] for m in estado["medicos_sin_carga"]] == ["GAR"]
    assert estado["cobertura_definida"] is False
    # Con reglas desde el mes revisado deja de aparecer.
    cliente.put(f"/api/medicos/{medico['id']}/reglas", json={
        "vigente_desde": estado["mes"], "elegibilidad": [], "carga": {"minimo": 0, "maximo": 10},
    })
    assert cliente.get("/api/estado").json()["medicos_sin_carga"] == []


# --- Interfaz ----------------------------------------------------------------------


def test_sirve_la_interfaz_y_su_navegacion(motor, tmp_path: Path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>turnos</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    cliente = TestClient(crear_app(motor, interfaz=dist))
    assert cliente.get("/").text == "<html>turnos</html>"
    assert cliente.get("/medicos/3").text == "<html>turnos</html>"  # ruta de React
    assert cliente.get("/assets/app.js").text == "console.log(1)"
    assert cliente.get("/api/no-existe").status_code == 404
    assert cliente.get("/../../etc/passwd").text == "<html>turnos</html>"


# --- Ajustes generales -----------------------------------------------------------


def test_ajustes_por_defecto_y_guardado(cliente):
    assert cliente.get("/api/ajustes").json() == {
        "todos_trabajan": True, "modo_carga": "RANGOS", "roles_segun_presencia": True, "prioridad_roles": "URGENCIAS",
        "mostrar_cobertura": False, "municipio": "28079"
    }
    nuevos = {"todos_trabajan": False, "modo_carga": "PRESENCIA", "roles_segun_presencia": False,
              "prioridad_roles": "DOMICILIOS", "mostrar_cobertura": True, "municipio": "46250"}
    assert cliente.put("/api/ajustes", json=nuevos).json() == nuevos
    assert cliente.get("/api/ajustes").json() == nuevos
    assert cliente.put("/api/ajustes", json={"todos_trabajan": False, "municipio": "99999"}).status_code == 422


def test_todos_trabajan_cada_dia_en_el_calendario(cliente, equipo):
    # 4 médicos y hasta 2 por turno: con la opción, los 4 trabajan los 20 días laborables.
    cobertura = [
        {"dia_semana": d, "mitad": h, "minimo": 1, "maximo": 2} for d in range(5) for h in ("M1", "M2", "T1", "T2")
    ]
    cliente.put("/api/cobertura/semanal", json=cobertura)
    cliente.put("/api/ajustes", json={"todos_trabajan": True})
    cal = cliente.post("/api/periodos/2026/11/generar", json={}).json()
    assert cal["avisos"] == []
    for m in equipo:
        assert len({a["fecha"] for a in cal["asignaciones"] if a["medico_id"] == m}) == 20
    # Un médico de vacaciones una semana queda exento esos días.
    cliente.post("/api/ausencias", json={"medico_id": equipo[0], "desde": "2026-11-16", "hasta": "2026-11-20"})
    cal = cliente.post("/api/periodos/2026/11/generar", json={}).json()
    assert len({a["fecha"] for a in cal["asignaciones"] if a["medico_id"] == equipo[0]}) == 15
    # Quitarlo a mano de su turno lo avisa (aún podría hacer el otro turno ese día)…
    turno = next(a["mitad"][0] for a in cal["asignaciones"] if a["medico_id"] == equipo[1] and a["fecha"] == "2026-11-03")
    cal = cliente.post("/api/periodos/2026/11/cambios", json=[
        {"medico_id": equipo[1], "fecha": "2026-11-03", "mitades": []},
    ]).json()
    nombre = next(m["nombre"] for m in cal["medicos"] if m["id"] == equipo[1])
    assert f"{nombre} no tiene turno el martes 3/11." in [a["mensaje"] for a in cal["avisos"]]
    # …y al regenerar se le pone el otro turno, no el que se le quitó.
    cal = cliente.post("/api/periodos/2026/11/generar", json={}).json()
    del_dia = {a["mitad"][0] for a in cal["asignaciones"] if a["medico_id"] == equipo[1] and a["fecha"] == "2026-11-03"}
    assert del_dia and turno not in del_dia


def test_prioridad_de_urgencias_o_domicilios(cliente):
    assert cliente.put("/api/ajustes", json={"prioridad_roles": "IGUAL"}).json()["prioridad_roles"] == "IGUAL"
    assert cliente.put("/api/ajustes", json={"prioridad_roles": "OTRA"}).status_code == 422
