"""Solicitudes de los médicos (diseño del modo servidor, 6.4): cada tipo, su circuito,
que un médico no vea ni resuelva las de otros, que aprobar aplique el cambio y sus efectos."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from apoyo_servidor import URL, cuenta_medico
from turnos.datos.tablas import RegistroCambio

SEMANA = [{"dia_semana": d, "turno": t, "valor": "DISPONIBLE"} for d in range(5) for t in ("MANANA", "TARDE")]


def _turno_de(cliente, medico, turno="MANANA"):
    """Una fecha en la que el médico tiene ese turno completo (noviembre)."""
    cal = cliente.get(URL).json()
    mitades = {"MANANA": {"M1", "M2"}, "TARDE": {"T1", "T2"}}[turno]
    dias: dict[str, set] = {}
    for a in cal["asignaciones"]:
        if a["medico_id"] == medico:
            dias.setdefault(a["fecha"], set()).add(a["mitad"])
    return next(f for f, m in sorted(dias.items()) if mitades <= m)


def test_ausencia_pedida_aprobada_y_aplicada(servidor, admin, plani, equipo_servidor):
    ana = equipo_servidor[0]
    medico = cuenta_medico(servidor, admin, ana)
    r = medico.post("/api/solicitudes", json={
        "propuesta": {"tipo": "AUSENCIA", "accion": "CREAR", "desde": "2026-12-02", "hasta": "2026-12-04"},
        "comentario": "Congreso"})
    assert r.status_code == 201, r.text
    solicitud = r.json()
    assert solicitud["estado"] == "PENDIENTE" and solicitud["mia"]
    assert solicitud["descripcion"] == ["Ausencia del mié 2/12 al vie 4/12 (día completo)"]
    # El planificador la ve, con sus efectos (diciembre no está generado: ningún mes que revisar).
    assert [x["id"] for x in plani.get("/api/solicitudes").json()] == [solicitud["id"]]
    assert plani.get(f"/api/solicitudes/{solicitud['id']}/efectos").json() == {"avisos": [], "meses": []}
    r = plani.post(f"/api/solicitudes/{solicitud['id']}/aprobar", json={"comentario": "Que vaya bien"})
    assert r.json()["estado"] == "APROBADA" and r.json()["resuelta_por"] == "Planificación"
    assert [(a["desde"], a["hasta"]) for a in plani.get(f"/api/ausencias?medico_id={ana}").json()] == [
        ("2026-12-02", "2026-12-04")]
    # El médico ve el estado y el comentario; no se puede aprobar dos veces.
    vista = medico.get("/api/solicitudes").json()[0]
    assert (vista["estado"], vista["comentario_resolucion"]) == ("APROBADA", "Que vaya bien")
    assert plani.post(f"/api/solicitudes/{solicitud['id']}/aprobar", json={}).status_code == 409
    with Session(servidor.state.motor) as sesion:
        acciones = [(c.usuario, c.accion) for c in sesion.scalars(select(RegistroCambio).order_by(RegistroCambio.id))]
    assert ("ana", "Solicitud nueva") in acciones and ("plani", "Aprobar una solicitud") in acciones


def test_anular_una_ausencia_propia(servidor, admin, plani, equipo_servidor):
    ana, bea = equipo_servidor[:2]
    medico = cuenta_medico(servidor, admin, ana)
    propia = plani.post("/api/ausencias", json={"medico_id": ana, "desde": "2026-12-10", "hasta": "2026-12-10"}).json()
    ajena = plani.post("/api/ausencias", json={"medico_id": bea, "desde": "2026-12-10", "hasta": "2026-12-10"}).json()
    r = medico.post("/api/solicitudes", json={"propuesta": {"tipo": "AUSENCIA", "accion": "ANULAR", "ausencia_id": ajena["id"]}})
    assert r.status_code == 422 and "no es tuya" in r.json()["detail"]
    r = medico.post("/api/solicitudes", json={"propuesta": {"tipo": "AUSENCIA", "accion": "ANULAR", "ausencia_id": propia["id"]}})
    assert r.json()["descripcion"] == ["Anular la ausencia jue 10/12 (día completo)"]
    plani.post(f"/api/solicitudes/{r.json()['id']}/aprobar", json={})
    assert plani.get(f"/api/ausencias?medico_id={ana}").json() == []


def test_disponibilidad_desde_un_mes_conserva_la_carga(servidor, admin, plani, equipo_servidor):
    ana = equipo_servidor[0]
    medico = cuenta_medico(servidor, admin, ana)
    semana = [c | {"valor": "NO_DISPONIBLE"} if (c["dia_semana"], c["turno"]) == (0, "TARDE") else c for c in SEMANA]
    r = medico.post("/api/solicitudes", json={"propuesta": {"tipo": "DISPONIBILIDAD", "desde": "2026-11-01",
                                                            "elegibilidad": semana}})
    assert r.status_code == 201, r.text
    assert r.json()["descripcion"] == ["Disponibilidad semanal desde noviembre de 2026:",
                                       "lunes por la tarde: Disponible → No disponible"]
    efectos = plani.get(f"/api/solicitudes/{r.json()['id']}/efectos").json()
    assert efectos["meses"] == ["noviembre de 2026 (borrador)"]  # ya generado: hay que revisarlo
    plani.post(f"/api/solicitudes/{r.json()['id']}/aprobar", json={})
    reglas = plani.get(f"/api/medicos/{ana}/reglas?fecha=2026-11-15").json()
    assert {"dia_semana": 0, "turno": "TARDE", "valor": "NO_DISPONIBLE"} in reglas["elegibilidad"]
    assert reglas["carga"] == {"minimo": 0, "maximo": 40}  # la carga la decide el planificador
    # Un mes ya pasado no se puede proponer.
    r = medico.post("/api/solicitudes", json={"propuesta": {"tipo": "DISPONIBILIDAD", "desde": "2020-01-01",
                                                            "elegibilidad": SEMANA}})
    assert r.status_code == 422


def test_no_puedo_hacer_un_turno_de_un_mes_publicado(servidor, admin, plani, equipo_servidor):
    ana = equipo_servidor[0]
    medico = cuenta_medico(servidor, admin, ana)
    fecha = _turno_de(plani, ana)
    propuesta = {"tipo": "CALENDARIO", "cambio": "NO_PUEDO", "fecha": fecha, "turno": "MANANA"}
    # En un borrador, no: solo meses publicados.
    r = medico.post("/api/solicitudes", json={"propuesta": propuesta})
    assert r.status_code == 422 and "publicados" in r.json()["detail"]
    plani.post(f"{URL}/publicar")
    version = plani.get(URL).json()["version"]
    r = medico.post("/api/solicitudes", json={"propuesta": propuesta, "comentario": "Médico de cabecera"})
    assert r.status_code == 201, r.text
    # Efectos: faltaría un médico esa mañana.
    avisos = plani.get(f"/api/solicitudes/{r.json()['id']}/efectos").json()["avisos"]
    assert any("por la mañana falta 1 médico" in a for a in avisos), avisos
    # Probar los efectos no cambia nada.
    assert plani.get(URL).json()["version"] == version
    plani.post(f"/api/solicitudes/{r.json()['id']}/aprobar", json={})
    cal = plani.get(URL).json()
    assert cal["estado"] == "PUBLICADO" and cal["version"] == version + 1  # sin reabrirlo (D-S9)
    assert not any(a["medico_id"] == ana and a["fecha"] == fecha and a["mitad"][0] == "M" for a in cal["asignaciones"])
    # Un turno que no tiene, no.
    otro = _turno_de(plani, equipo_servidor[1])
    if not any(a["medico_id"] == ana and a["fecha"] == otro for a in cal["asignaciones"]):
        r = medico.post("/api/solicitudes", json={"propuesta": propuesta | {"fecha": otro}})
        assert r.status_code == 422 and "No tienes" in r.json()["detail"]


def test_intercambio_acordado_entre_los_dos(servidor, admin, plani, equipo_servidor):
    ana, bea = equipo_servidor[:2]
    medico_ana = cuenta_medico(servidor, admin, ana, "ana")
    medico_bea = cuenta_medico(servidor, admin, bea, "bea")
    plani.post(f"{URL}/publicar")
    fecha_ana, fecha_bea = _turno_de(plani, ana), _turno_de(plani, bea)
    r = medico_ana.post("/api/solicitudes", json={"propuesta": {
        "tipo": "CALENDARIO", "cambio": "INTERCAMBIO", "fecha": fecha_ana, "turno": "MANANA",
        "companero_id": bea, "fecha_companero": fecha_bea, "turno_companero": "MANANA"}})
    assert r.status_code == 201, r.text
    solicitud = r.json()
    assert solicitud["estado"] == "ESPERA_COMPANERO" and solicitud["companero"] == "Bea"
    # Antes de que Bea acepte, el planificador no puede aprobarla.
    r = plani.post(f"/api/solicitudes/{solicitud['id']}/aprobar", json={})
    assert r.status_code == 409 and "compañero" in r.json()["detail"]
    # Bea la ve y la acepta; Ana no puede aceptarla por ella.
    vista = medico_bea.get("/api/solicitudes").json()[0]
    assert vista["me_toca_aceptar"] and not vista["mia"]
    assert medico_ana.post(f"/api/solicitudes/{solicitud['id']}/aceptar", json={"acepta": True}).status_code == 403
    assert medico_bea.post(f"/api/solicitudes/{solicitud['id']}/aceptar", json={"acepta": True}).json()["estado"] == "PENDIENTE"
    plani.post(f"/api/solicitudes/{solicitud['id']}/aprobar", json={})
    cal = plani.get(URL).json()

    def tiene(medico, fecha):
        return {"M1", "M2"} <= {a["mitad"] for a in cal["asignaciones"] if a["medico_id"] == medico and a["fecha"] == fecha}

    assert tiene(ana, fecha_bea) and tiene(bea, fecha_ana)
    if fecha_ana != fecha_bea:
        assert not tiene(ana, fecha_ana) and not tiene(bea, fecha_bea)


def test_el_companero_puede_no_aceptar(servidor, admin, plani, equipo_servidor):
    ana, bea = equipo_servidor[:2]
    medico_ana = cuenta_medico(servidor, admin, ana, "ana")
    medico_bea = cuenta_medico(servidor, admin, bea, "bea")
    plani.post(f"{URL}/publicar")
    r = medico_ana.post("/api/solicitudes", json={"propuesta": {
        "tipo": "CALENDARIO", "cambio": "INTERCAMBIO", "fecha": _turno_de(plani, ana), "turno": "MANANA",
        "companero_id": bea, "fecha_companero": _turno_de(plani, bea), "turno_companero": "MANANA"}})
    r = medico_bea.post(f"/api/solicitudes/{r.json()['id']}/aceptar", json={"acepta": False, "comentario": "Ese día no puedo"})
    assert r.json()["estado"] == "RECHAZADA" and r.json()["respuesta_companero"] == "Ese día no puedo"


def test_cada_medico_solo_ve_y_retira_las_suyas(servidor, admin, plani, equipo_servidor):
    ana, bea = equipo_servidor[:2]
    medico_ana = cuenta_medico(servidor, admin, ana, "ana")
    medico_bea = cuenta_medico(servidor, admin, bea, "bea")
    r = medico_ana.post("/api/solicitudes", json={
        "propuesta": {"tipo": "AUSENCIA", "accion": "CREAR", "desde": "2026-12-02", "hasta": "2026-12-02"}})
    id_ = r.json()["id"]
    assert medico_bea.get("/api/solicitudes").json() == []
    assert medico_bea.post(f"/api/solicitudes/{id_}/retirar").status_code == 404
    for accion in ("aprobar", "rechazar"):
        assert medico_ana.post(f"/api/solicitudes/{id_}/{accion}", json={}).status_code == 403
    assert medico_ana.get(f"/api/solicitudes/{id_}/efectos").status_code == 403
    assert medico_ana.post(f"/api/solicitudes/{id_}/retirar").json()["estado"] == "RETIRADA"
    assert plani.post(f"/api/solicitudes/{id_}/aprobar", json={}).status_code == 409


def test_rechazar_y_resolver_de_otra_forma(servidor, admin, plani, equipo_servidor):
    ana = equipo_servidor[0]
    medico = cuenta_medico(servidor, admin, ana)
    plani.post(f"{URL}/publicar")
    fecha = _turno_de(plani, ana)
    nueva = lambda: medico.post("/api/solicitudes", json={"propuesta": {  # noqa: E731
        "tipo": "CALENDARIO", "cambio": "OTRA_MITAD", "fecha": fecha, "turno": "MANANA"}}).json()
    primera = nueva()
    assert primera["descripcion"] == [f"Prefiere la tarde en lugar de la mañana del {primera['descripcion'][0].split('del ')[-1]}"]
    r = plani.post(f"/api/solicitudes/{primera['id']}/rechazar", json={"comentario": "Esa tarde ya está cubierta"})
    assert (r.json()["estado"], r.json()["comentario_resolucion"]) == ("RECHAZADA", "Esa tarde ya está cubierta")
    antes = plani.get(URL).json()["asignaciones"]
    segunda = nueva()
    r = plani.post(f"/api/solicitudes/{segunda['id']}/aprobar", json={"aplicar": False, "comentario": "Lo cambio yo"})
    assert r.json()["estado"] == "RESUELTA"
    assert plani.get(URL).json()["asignaciones"] == antes  # sin aplicar
