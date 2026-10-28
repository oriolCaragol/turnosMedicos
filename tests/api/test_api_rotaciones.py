"""API de turnos rotativos y su efecto en el calendario."""


def rotacion(equipo, **extra):
    return {
        "nombre": "Martes mañana",
        "desde": "2026-11-02",
        "medicos": [equipo[0], equipo[1]],
        "huecos": [{"dia_semana": 1, "turno": "MANANA"}],
        **extra,
    }


def test_alta_listado_modificacion_y_baja(cliente, equipo):
    creada = cliente.post("/api/rotaciones", json=rotacion(equipo)).json()
    assert creada["medicos"] == [equipo[0], equipo[1]] and creada["activa"] is True
    assert [r["id"] for r in cliente.get("/api/rotaciones").json()] == [creada["id"]]
    cambiada = cliente.put(f"/api/rotaciones/{creada['id']}", json=rotacion(
        equipo, medicos=[equipo[2], equipo[0], equipo[1]], huecos=[{"dia_semana": 3, "turno": "TARDE"}],
    )).json()
    assert cambiada["medicos"] == [equipo[2], equipo[0], equipo[1]]
    assert cambiada["huecos"] == [{"dia_semana": 3, "turno": "TARDE"}]
    assert cliente.delete(f"/api/rotaciones/{creada['id']}").status_code == 204
    assert cliente.get("/api/rotaciones").json() == []


def test_datos_no_validos(cliente, equipo):
    assert cliente.post("/api/rotaciones", json=rotacion(equipo, medicos=[equipo[0], equipo[0]])).status_code == 422
    assert cliente.post("/api/rotaciones", json=rotacion(equipo, medicos=[999, equipo[0]])).status_code == 422
    assert cliente.post("/api/rotaciones", json=rotacion(equipo, nombre="")).status_code == 422
    assert cliente.put("/api/rotaciones/999", json=rotacion(equipo)).status_code == 404


def test_el_calendario_alterna_las_semanas(cliente, equipo):
    cliente.post("/api/rotaciones", json=rotacion(equipo))
    cal = cliente.post("/api/periodos/2026/11/generar", json={}).json()
    manana = lambda fecha: {  # noqa: E731
        a["medico_id"] for a in cal["asignaciones"] if a["fecha"] == fecha and a["mitad"] == "M1"
    }
    # Semana del 2/11 → primero; del 9 → segundo; del 16 → primero; del 23 → segundo.
    assert manana("2026-11-03") == {equipo[0]}
    assert manana("2026-11-10") == {equipo[1]}
    assert manana("2026-11-17") == {equipo[0]}
    assert manana("2026-11-24") == {equipo[1]}
    fijas = [a for a in cal["asignaciones"] if a["fecha"] == "2026-11-17" and a["mitad"] == "M1"]
    assert fijas[0]["origen"] == "FIJO"


def test_la_rotacion_manda_sobre_el_fijo_de_la_tarjeta(cliente, equipo):
    # Ana (equipo[0]) tiene los lunes por la mañana como Fijo en su tarjeta.
    cliente.post("/api/rotaciones", json=rotacion(
        equipo, medicos=[equipo[1], equipo[0]], huecos=[{"dia_semana": 0, "turno": "MANANA"}],
    ))
    cal = cliente.post("/api/periodos/2026/11/generar", json={}).json()
    lunes = lambda fecha: {  # noqa: E731
        a["medico_id"] for a in cal["asignaciones"] if a["fecha"] == fecha and a["mitad"] == "M1"
    }
    assert lunes("2026-11-09") == {equipo[0]}  # semana 2: le toca a Ana
    assert lunes("2026-11-16") == {equipo[1]}  # semana 3: a Bea, y Ana no coincide


def test_rotacion_inactiva_o_incompleta_no_cuenta(cliente, equipo):
    cliente.post("/api/rotaciones", json=rotacion(equipo, activa=False))
    cliente.post("/api/rotaciones", json=rotacion(equipo, medicos=[equipo[2]]))
    cal = cliente.post("/api/periodos/2026/11/generar", json={}).json()
    martes = [a for a in cal["asignaciones"] if a["fecha"] == "2026-11-10" and a["mitad"] == "M1"]
    assert not any(a["origen"] == "FIJO" for a in martes)
