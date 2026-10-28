from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from turnos.datos.tablas import CargaAjustada

from turnos.servicios.periodos import _saldo

URL = "/api/periodos/2026/11"


def turnos_en(cal, fecha, turno):
    mitades = ("M1", "M2") if turno == "MANANA" else ("T1", "T2")
    return {a["medico_id"] for a in cal["asignaciones"] if a["fecha"] == fecha and a["mitad"] in mitades}


def test_mes_sin_generar(cliente, equipo):
    cal = cliente.get(URL).json()
    assert cal["estado"] == "SIN_GENERAR" and cal["asignaciones"] == []
    assert len(cal["dias"]) == 21
    festivos = [d for d in cal["dias"] if d["festivo"]]
    assert [d["fecha"] for d in festivos] == ["2026-11-02"]
    assert len(cal["cobertura"]) == 20 * 4  # solo días laborables
    assert all(m["con_carga"] for m in cal["medicos"])


def test_generar(cliente, equipo):
    cal = cliente.post(f"{URL}/generar", json={}).json()
    assert cal["estado"] == "BORRADOR"
    assert cal["avisos"] == []
    assert len(cal["asignaciones"]) == 20 * 4
    ana = equipo[0]
    lunes_9 = [a for a in cal["asignaciones"] if a["fecha"] == "2026-11-09" and a["medico_id"] == ana]
    assert {a["mitad"] for a in lunes_9} == {"M1", "M2"} and lunes_9[0]["origen"] == "FIJO"
    assert sum(m["asignado"] for m in cal["medicos"]) == 80


def test_cambio_manual_bloquea_veta_y_avisa(cliente, equipo):
    cal = cliente.post(f"{URL}/generar", json={}).json()
    fecha = "2026-11-10"
    (medico,) = turnos_en(cal, fecha, "MANANA")
    # Se quita al médico de la mañana: queda vetado y falta personal.
    cal = cliente.post(f"{URL}/cambios", json=[{"medico_id": medico, "fecha": fecha, "mitades": []}]).json()
    assert turnos_en(cal, fecha, "MANANA") == set()
    assert {"medico_id": medico, "fecha": fecha, "turno": "MANANA"} in cal["vetos"]
    assert "El martes 10/11 por la mañana falta 1 médico." in [a["mensaje"] for a in cal["avisos"]]
    # Al regenerar se cubre con otro médico y el vetado no vuelve.
    cal = cliente.post(f"{URL}/generar", json={}).json()
    nuevo = turnos_en(cal, fecha, "MANANA")
    assert len(nuevo) == 1 and medico not in nuevo


def test_asignacion_manual_queda_bloqueada_y_se_respeta(cliente, equipo):
    cal = cliente.post(f"{URL}/generar", json={}).json()
    fecha = "2026-11-11"
    (actual,) = turnos_en(cal, fecha, "TARDE")
    otro = next(m for m in equipo if m != actual and m not in turnos_en(cal, fecha, "MANANA"))
    cambios = [
        {"medico_id": actual, "fecha": fecha, "mitades": []},
        {"medico_id": otro, "fecha": fecha, "mitades": ["T1", "T2"]},
    ]
    cal = cliente.post(f"{URL}/cambios", json=cambios).json()
    asignadas = [a for a in cal["asignaciones"] if a["medico_id"] == otro and a["fecha"] == fecha]
    assert all(a["bloqueada"] and a["origen"] == "MANUAL" for a in asignadas)
    cal = cliente.post(f"{URL}/generar", json={}).json()
    assert turnos_en(cal, fecha, "TARDE") == {otro}


def test_jornada_de_turno_y_medio_manual(cliente, equipo):
    cliente.post(f"{URL}/generar", json={})
    medico = equipo[1]
    cal = cliente.post(f"{URL}/cambios", json=[
        {"medico_id": medico, "fecha": "2026-11-12", "mitades": ["M1", "M2", "T1"]},
    ]).json()
    mitades = {a["mitad"] for a in cal["asignaciones"] if a["medico_id"] == medico and a["fecha"] == "2026-11-12"}
    assert mitades == {"M1", "M2", "T1"}
    assert any("sobra" in a["mensaje"] for a in cal["avisos"])


def test_bloquear_y_desbloquear(cliente, equipo):
    cal = cliente.post(f"{URL}/generar", json={}).json()
    a = next(a for a in cal["asignaciones"] if a["origen"] == "GENERADOR")
    cambio = {"medico_id": a["medico_id"], "fecha": a["fecha"], "bloqueada": True}
    cal = cliente.post(f"{URL}/cambios", json=[cambio]).json()
    del_dia = [x for x in cal["asignaciones"] if x["medico_id"] == a["medico_id"] and x["fecha"] == a["fecha"]]
    assert all(x["bloqueada"] for x in del_dia)
    cal = cliente.post(f"{URL}/cambios", json=[{**cambio, "bloqueada": False}]).json()
    del_dia = [x for x in cal["asignaciones"] if x["medico_id"] == a["medico_id"] and x["fecha"] == a["fecha"]]
    assert not any(x["bloqueada"] for x in del_dia)


def test_deshacer_restaurando_el_estado(cliente, equipo):
    antes = cliente.post(f"{URL}/generar", json={}).json()
    a = antes["asignaciones"][0]
    cliente.post(f"{URL}/cambios", json=[{"medico_id": a["medico_id"], "fecha": a["fecha"], "mitades": []}])
    cal = cliente.put(f"{URL}/manual", json={"asignaciones": antes["asignaciones"], "vetos": antes["vetos"]}).json()
    clave = lambda x: (x["medico_id"], x["fecha"], x["mitad"], x["origen"], x["bloqueada"])  # noqa: E731
    assert Counter(map(clave, cal["asignaciones"])) == Counter(map(clave, antes["asignaciones"]))
    assert cal["vetos"] == []


def test_publicar_impide_cambios_hasta_reabrir(cliente, equipo):
    cliente.post(f"{URL}/generar", json={})
    cal = cliente.post(f"{URL}/publicar").json()
    assert cal["estado"] == "PUBLICADO" and cal["publicado_en"]
    assert cliente.post(f"{URL}/generar", json={}).status_code == 409
    a = cal["asignaciones"][0]
    r = cliente.post(f"{URL}/cambios", json=[{"medico_id": a["medico_id"], "fecha": a["fecha"], "mitades": []}])
    assert r.status_code == 409
    assert cliente.post(f"{URL}/reabrir").json()["estado"] == "BORRADOR"


def test_alternativa(cliente, equipo):
    antes = cliente.post(f"{URL}/generar", json={}).json()
    despues = cliente.post(f"{URL}/generar", json={"alternativa": True}).json()
    clave = lambda x: (x["medico_id"], x["fecha"], x["mitad"])  # noqa: E731
    assert set(map(clave, antes["asignaciones"])) != set(map(clave, despues["asignaciones"]))
    assert despues["avisos"] == []


def test_carga_manual(cliente, equipo):
    medico = equipo[2]
    cal = cliente.put(f"{URL}/carga/{medico}", json={"minimo": 10, "maximo": 12}).json()
    m = next(m for m in cal["medicos"] if m["id"] == medico)
    assert (m["minimo"], m["maximo"], m["carga_manual"]) == (10, 12, True)
    assert m["maximo_calculado"] == 40
    cal = cliente.post(f"{URL}/generar", json={}).json()
    m = next(m for m in cal["medicos"] if m["id"] == medico)
    assert 10 <= m["asignado"] <= 12
    cal = cliente.put(f"{URL}/carga/{medico}", json={}).json()
    assert next(m for m in cal["medicos"] if m["id"] == medico)["carga_manual"] is False


def test_medico_sin_carga_no_se_asigna(cliente, equipo):
    sin = cliente.post("/api/medicos", json={"nombre": "Eva", "codigo": "EVA"}).json()
    cal = cliente.post(f"{URL}/generar", json={}).json()
    eva = next(m for m in cal["medicos"] if m["id"] == sin["id"])
    assert eva["con_carga"] is False and eva["asignado"] == 0


def test_turnos_habituales_en_el_calendario(cliente, equipo):
    medico = equipo[1]
    reglas = cliente.get(f"/api/medicos/{medico}/reglas", params={"fecha": "2026-11-01"}).json()
    reglas.update(vigente_desde="2026-11-01", elegibilidad=[{"dia_semana": 0, "turno": "TARDE", "valor": "HABITUAL"}])
    cliente.put(f"/api/medicos/{medico}/reglas", json=reglas)
    cal = cliente.get(URL).json()
    m = next(m for m in cal["medicos"] if m["id"] == medico)
    assert {"fecha": "2026-11-09", "turno": "TARDE"} in m["habituales"]
    assert {"fecha": "2026-11-02", "turno": "TARDE"} not in m["habituales"]  # festivo


def test_ausencias_y_no_elegibles(cliente, equipo):
    medico = equipo[3]
    cliente.post("/api/ausencias", json={"medico_id": medico, "desde": "2026-11-16", "hasta": "2026-11-20"})
    cal = cliente.post(f"{URL}/generar", json={}).json()
    m = next(m for m in cal["medicos"] if m["id"] == medico)
    assert m["maximo"] == 30  # 40 × 15/20 días
    assert {"fecha": "2026-11-16", "turno": "MANANA", "motivo": "AUSENTE"} in m["no_elegibles"]
    assert not any(a["medico_id"] == medico and "2026-11-16" <= a["fecha"] <= "2026-11-20"
                   for a in cal["asignaciones"])


def test_cambios_no_validos(cliente, equipo):
    r = cliente.post(f"{URL}/cambios", json=[{"medico_id": equipo[0], "fecha": "2026-12-01", "mitades": []}])
    assert r.status_code == 422
    r = cliente.post(f"{URL}/cambios", json=[{"medico_id": equipo[0], "fecha": "2026-11-10"}])
    assert r.status_code == 422
    assert cliente.get("/api/periodos/2026/13").status_code == 422


def test_saldo_de_meses_publicados(cliente, equipo, motor):
    cliente.post(f"{URL}/generar", json={})
    cal = cliente.post(f"{URL}/publicar").json()
    with Session(motor) as s:
        objetivos = dict(s.execute(select(CargaAjustada.medico_id, CargaAjustada.objetivo).where(
            CargaAjustada.turno.is_(None)
        )).all())
        for m in cal["medicos"]:
            assert _saldo(s, m["id"], 2026, 12) == m["asignado"] - objetivos[m["id"]]
            assert _saldo(s, m["id"], 2026, 11) == 0  # el propio mes no cuenta


def test_volver_a_automatico(cliente, equipo):
    cal = cliente.post(f"{URL}/generar", json={}).json()
    fecha = "2026-11-10"
    (manana,) = turnos_en(cal, fecha, "MANANA")
    (tarde,) = turnos_en(cal, fecha, "TARDE")
    cliente.post(f"{URL}/cambios", json=[
        {"medico_id": manana, "fecha": fecha, "mitades": []},
        {"medico_id": tarde, "fecha": fecha, "bloqueada": True},
    ])
    # Solo la mañana: se retira el veto; la tarde sigue bloqueada.
    cal = cliente.post(f"{URL}/liberar", json={"fecha": fecha, "turno": "MANANA"}).json()
    assert cal["vetos"] == []
    assert any(a["bloqueada"] for a in cal["asignaciones"] if a["fecha"] == fecha)
    # Todo el mes.
    cal = cliente.post(f"{URL}/liberar", json={}).json()
    assert not any(a["bloqueada"] for a in cal["asignaciones"])
    assert cliente.post(f"{URL}/liberar", json={"fecha": "2026-12-01"}).status_code == 422
    cliente.post(f"{URL}/publicar")
    assert cliente.post(f"{URL}/liberar", json={}).status_code == 409


# --- Urgencias y domicilios ---------------------------------------------------------


def con_dos_de_tarde(cliente):
    cobertura = [
        {"dia_semana": d, "mitad": h, "minimo": 1 if h[0] == "M" else 2, "maximo": 1 if h[0] == "M" else 2}
        for d in range(5) for h in ("M1", "M2", "T1", "T2")
    ]
    cliente.put("/api/cobertura/semanal", json=cobertura)


def roles_de(cal, fecha):
    return {r["rol"]: r["medico_id"] for r in cal["roles"] if r["fecha"] == fecha}


def test_urgencias_y_domicilios_cada_tarde(cliente, equipo):
    con_dos_de_tarde(cliente)
    cal = cliente.post(f"{URL}/generar", json={}).json()
    assert cal["avisos"] == []
    for dia in {a["fecha"] for a in cal["asignaciones"]}:
        r = roles_de(cal, dia)
        assert set(r) == {"URGENCIAS", "DOMICILIOS"} and r["URGENCIAS"] != r["DOMICILIOS"]
        assert {r["URGENCIAS"], r["DOMICILIOS"]} == turnos_en(cal, dia, "TARDE")
    # Reparto uniforme: 20 tardes entre 4 médicos → 5 de cada papel.
    assert {(m["urgencias"], m["domicilios"]) for m in cal["medicos"]} == {(5, 5)}
    assert all(m["tardes_disponibles"] == 20 for m in cal["medicos"])


def test_cambiar_el_papel_a_mano_intercambia_y_se_respeta(cliente, equipo):
    con_dos_de_tarde(cliente)
    cal = cliente.post(f"{URL}/generar", json={}).json()
    fecha = "2026-11-10"
    antes = roles_de(cal, fecha)
    # El de domicilios pasa a urgencias: los dos se intercambian el papel.
    cal = cliente.post(f"{URL}/cambios", json=[
        {"medico_id": antes["DOMICILIOS"], "fecha": fecha, "rol": "URGENCIAS"},
    ]).json()
    despues = roles_de(cal, fecha)
    assert despues == {"URGENCIAS": antes["DOMICILIOS"], "DOMICILIOS": antes["URGENCIAS"]}
    assert all(r["manual"] for r in cal["roles"] if r["fecha"] == fecha)
    # Al regenerar se mantiene.
    cal = cliente.post(f"{URL}/generar", json={}).json()
    assert roles_de(cal, fecha) == despues
    # Volver a automático quita la marca manual.
    cal = cliente.post(f"{URL}/liberar", json={"fecha": fecha, "turno": "TARDE"}).json()
    assert not any(r["manual"] for r in cal["roles"] if r["fecha"] == fecha)


def test_papel_sin_tarde_completa_y_avisos(cliente, equipo):
    con_dos_de_tarde(cliente)
    cal = cliente.post(f"{URL}/generar", json={}).json()
    fecha = "2026-11-11"
    de_manana = next(iter(turnos_en(cal, fecha, "MANANA")))
    r = cliente.post(f"{URL}/cambios", json=[{"medico_id": de_manana, "fecha": fecha, "rol": "URGENCIAS"}])
    assert r.status_code == 422
    # Si quien hace urgencias deja la tarde, su papel queda libre y se avisa.
    urg = roles_de(cal, fecha)["URGENCIAS"]
    cal = cliente.post(f"{URL}/cambios", json=[{"medico_id": urg, "fecha": fecha, "mitades": []}]).json()
    assert "URGENCIAS" not in roles_de(cal, fecha)
    assert "El miércoles 11/11 por la tarde nadie hace urgencias." in [a["mensaje"] for a in cal["avisos"]]


def test_deshacer_restaura_los_papeles(cliente, equipo):
    con_dos_de_tarde(cliente)
    antes = cliente.post(f"{URL}/generar", json={}).json()
    fecha = "2026-11-12"
    r = roles_de(antes, fecha)
    cliente.post(f"{URL}/cambios", json=[{"medico_id": r["DOMICILIOS"], "fecha": fecha, "rol": "URGENCIAS"}])
    cal = cliente.put(f"{URL}/manual", json={
        "asignaciones": antes["asignaciones"], "vetos": antes["vetos"], "roles": antes["roles"],
    }).json()
    assert roles_de(cal, fecha) == r


def test_cambio_con_mas_de_una_operacion(cliente, equipo):
    r = cliente.post(f"{URL}/cambios", json=[
        {"medico_id": equipo[0], "fecha": "2026-11-10", "mitades": [], "rol": "URGENCIAS"},
    ])
    assert r.status_code == 422


def test_la_prioridad_de_urgencias_o_domicilios_llega_al_motor(cliente, motor, equipo):
    from sqlalchemy.orm import Session

    from turnos.dominio.modelos import Rol
    from turnos.servicios.periodos import construir

    def prioridad():
        with Session(motor) as sesion:
            return construir(sesion, 2026, 11).problema.prioridad_roles

    assert prioridad() is Rol.URGENCIAS  # por defecto
    cliente.put("/api/ajustes", json={"prioridad_roles": "DOMICILIOS"})
    assert prioridad() is Rol.DOMICILIOS
    cliente.put("/api/ajustes", json={"prioridad_roles": "IGUAL"})
    assert prioridad() is None


def test_segun_la_presencia_todos_trabajan_cada_dia_sin_rangos(cliente, equipo):
    """Modo de carga según la presencia: sin rangos de la ficha (tampoco hacen falta),
    cada médico trabaja todos los días laborables salvo ausencia."""
    cliente.put("/api/ajustes", json={"todos_trabajan": False, "modo_carga": "PRESENCIA"})
    nuevo = cliente.post("/api/medicos", json={"nombre": "Sin rango", "codigo": "SIN"}).json()  # sin carga en su ficha
    cliente.post("/api/ausencias", json={"medico_id": equipo[1], "desde": "2026-11-16", "hasta": "2026-11-20"})
    cliente.put("/api/cobertura/semanal", json=[
        {"dia_semana": d, "mitad": h, "minimo": 1, "maximo": 3} for d in range(5) for h in ("M1", "M2", "T1", "T2")])
    assert cliente.get("/api/estado").json()["medicos_sin_carga"] == []
    cal = cliente.post(f"{URL}/generar", json={}).json()
    laborables = [d["fecha"] for d in cal["dias"] if not d["festivo"]]
    for m in [*equipo, nuevo["id"]]:
        dias = {a["fecha"] for a in cal["asignaciones"] if a["medico_id"] == m}
        esperados = {d for d in laborables if not (m == equipo[1] and "2026-11-16" <= d <= "2026-11-20")}
        assert dias == esperados, m
    # Ningún aviso de carga (no hay rangos que cumplir).
    assert not [a for a in cal["avisos"] if "mínimo" in a["mensaje"] or "máximo" in a["mensaje"]]
    assert all(m["con_carga"] for m in cal["medicos"])
