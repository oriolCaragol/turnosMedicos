"""Modo servidor: inicio de sesión, sesiones, permisos por rol, CSRF y cuentas
(diseño del modo servidor, 6.1–6.3 y 13)."""

import sqlite3
from datetime import datetime, timedelta

from apoyo_servidor import URL, cuenta_medico, entrar
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from turnos.api import acceso
from turnos.api.app import crear_app
from turnos.api.rutas.servidor import EstadoServidor
from turnos.datos.bd import inicializar
from turnos.datos.tablas import RegistroCambio, SesionUsuario
from turnos.red.configuracion import ConfigServidor
from turnos.servicios import usuarios

# --- Sesión ---------------------------------------------------------------------------


def test_sin_sesion_solo_lo_publico(servidor):
    cliente = TestClient(servidor)
    assert cliente.get("/api/medicos").status_code == 401
    assert cliente.get("/api/yo").status_code == 401
    assert cliente.get("/api/servidor/publico").json() == {"nombre": "Turnos médicos", "https": False,
                                                           "hay_certificado": False}


def test_entrar_da_una_cookie_protegida_y_salir_la_quita(servidor):
    cliente = TestClient(servidor, headers={"X-Cliente": "x"})
    r = cliente.post("/api/sesion", json={"usuario": " Admin ", "contrasena": "contrasena-admin"})
    assert r.status_code == 200
    assert r.json()["rol"] == "ADMINISTRADOR" and r.json()["token"] is None
    cabecera = r.headers["set-cookie"].lower()
    assert "httponly" in cabecera and "samesite=lax" in cabecera and "max-age=2592000" in cabecera
    assert cliente.get("/api/yo").json()["nombre"] == "admin"
    assert cliente.delete("/api/sesion").status_code == 204
    assert cliente.get("/api/medicos").status_code == 401


def test_con_https_la_cookie_es_segura(tmp_path):
    motor = inicializar(tmp_path / "t.sqlite")
    config = ConfigServidor(datos=tmp_path / "t.sqlite", https=True)
    app = crear_app(motor, interfaz=None, servidor=EstadoServidor(config, None, []))
    with Session(motor) as sesion, sesion.begin():
        usuarios.crear_usuario(sesion, "admin", "A", "ADMINISTRADOR", "contrasena-admin")
    r = TestClient(app, headers={"X-Cliente": "x"}).post(
        "/api/sesion", json={"usuario": "admin", "contrasena": "contrasena-admin"})
    assert "secure" in r.headers["set-cookie"].lower()


def test_la_aplicacion_recibe_el_token_para_la_cabecera(servidor):
    r = TestClient(servidor, headers={"X-Cliente": "x"}).post(
        "/api/sesion", json={"usuario": "admin", "contrasena": "contrasena-admin", "aplicacion": True,
                             "dispositivo": "Turnos médicos (GNOME) en pc-casa"})
    token = r.json()["token"]
    otro = TestClient(servidor, headers={"Authorization": f"Bearer {token}"})
    assert otro.get("/api/yo").json()["nombre"] == "admin"
    assert otro.get("/api/sesiones").json()[0]["dispositivo"] == "Turnos médicos (GNOME) en pc-casa"


def test_contrasena_incorrecta_y_limite_de_intentos(servidor):
    cliente = TestClient(servidor, headers={"X-Cliente": "x"})
    for _ in range(5):
        r = cliente.post("/api/sesion", json={"usuario": "admin", "contrasena": "mala"})
        assert r.status_code == 401 and r.json()["detail"] == "Usuario o contraseña incorrectos."
    # El sexto, aunque sea el bueno, espera.
    r = cliente.post("/api/sesion", json={"usuario": "admin", "contrasena": "contrasena-admin"})
    assert r.status_code == 429
    # Un usuario que no existe responde igual que una contraseña mala.
    r = cliente.post("/api/sesion", json={"usuario": "nadie", "contrasena": "x"})
    assert r.status_code == 401 and r.json()["detail"] == "Usuario o contraseña incorrectos."


def test_una_sesion_caducada_ya_no_vale(servidor, admin):
    with Session(servidor.state.motor) as sesion, sesion.begin():
        sesion.execute(update(SesionUsuario).values(caduca=datetime.now() - timedelta(minutes=1)))
    assert admin.get("/api/medicos").status_code == 401
    with Session(servidor.state.motor) as sesion:
        assert sesion.scalars(select(SesionUsuario)).all() == []


def test_la_sesion_se_alarga_con_el_uso(servidor, admin):
    hace = datetime.now() - timedelta(days=10)
    with Session(servidor.state.motor) as sesion, sesion.begin():
        sesion.execute(update(SesionUsuario).values(ultimo_uso=hace, caduca=hace + timedelta(days=30)))
    assert admin.get("/api/medicos").status_code == 200
    with Session(servidor.state.motor) as sesion:
        caduca = sesion.scalar(select(SesionUsuario.caduca))
    assert caduca > datetime.now() + timedelta(days=29)


# --- CSRF -----------------------------------------------------------------------------


def test_las_modificaciones_exigen_la_cabecera_y_el_mismo_origen(servidor, admin):
    sin_cabecera = TestClient(servidor, cookies=admin.cookies)
    r = sin_cabecera.post("/api/medicos", json={"nombre": "X", "codigo": "X"})
    assert r.status_code == 403 and "no viene de la aplicación" in r.json()["detail"]
    r = admin.post("/api/medicos", json={"nombre": "X", "codigo": "X"}, headers={"Origin": "https://otra.web"})
    assert r.status_code == 403
    r = admin.post("/api/medicos", json={"nombre": "X", "codigo": "X"}, headers={"Origin": "http://testserver"})
    assert r.status_code == 201
    # Las lecturas no la necesitan.
    assert sin_cabecera.get("/api/medicos").status_code == 200


# --- Permisos -------------------------------------------------------------------------


def test_el_planificador_trabaja_pero_no_administra(plani):
    assert plani.post("/api/medicos", json={"nombre": "X", "codigo": "X"}).status_code == 201
    assert plani.get("/api/servidor").status_code == 200
    for metodo, ruta in [("GET", "/api/usuarios"), ("GET", "/api/sesiones"), ("POST", "/api/servidor/copias"),
                         ("POST", "/api/usuarios/1/restablecer")]:
        r = plani.request(metodo, ruta)
        assert r.status_code == 403 and r.json()["detail"] == acceso.SIN_PERMISO, ruta


def test_el_medico_solo_consulta_su_ficha_y_los_meses_publicados(servidor, admin, equipo_servidor):
    ana, bea = equipo_servidor[:2]
    medico = cuenta_medico(servidor, admin, ana)
    assert medico.get("/api/yo").json() | {"id": None} == {
        "modo": "servidor", "id": None, "nombre": "ana", "nombre_visible": "Ana", "rol": "MEDICO",
        "medico_id": ana, "debe_cambiar": False}
    # Su ficha sí; la de otro, no.
    assert medico.get(f"/api/medicos/{ana}/reglas").status_code == 200
    assert medico.get(f"/api/medicos/{bea}/reglas").status_code == 403
    assert medico.get(f"/api/ausencias?medico_id={ana}").status_code == 200
    assert medico.get("/api/ausencias").status_code == 403
    assert medico.get(f"/api/ausencias?medico_id={bea}").status_code == 403
    # Los borradores, no; tras publicar, sí (también sus informes).
    assert medico.get(URL).status_code == 403
    admin.post(f"{URL}/publicar")
    assert medico.get(URL).status_code == 200
    assert medico.get(f"{URL}/urgencias-domicilios.xlsx").status_code == 200
    # No modifica nada, aunque haga las peticiones a mano.
    for metodo, ruta, cuerpo in [
        ("PUT", f"/api/medicos/{ana}/reglas", {"vigente_desde": "2026-11-01", "elegibilidad": [], "carga": None}),
        ("POST", "/api/ausencias", {"medico_id": ana, "desde": "2026-11-02", "hasta": "2026-11-02"}),
        ("POST", f"{URL}/reabrir", None),
        ("GET", "/api/copia-de-seguridad", None),
        ("GET", "/api/estado", None),
        ("GET", "/api/registro", None),
        ("GET", "/api/usuarios", None),
    ]:
        assert medico.request(metodo, ruta, json=cuerpo).status_code == 403, ruta
    # Su contraseña sí la cambia, y sale.
    assert medico.post("/api/yo/contrasena", json={"actual": "contrasena-ana", "nueva": "otra-contrasena"}).status_code == 204
    assert medico.delete("/api/sesion").status_code == 204


def test_con_contrasena_temporal_solo_se_puede_cambiarla(servidor, admin, equipo_servidor):
    r = admin.post("/api/usuarios", json={"nombre": "bea", "nombre_visible": "Bea", "rol": "MEDICO",
                                          "medico_id": equipo_servidor[1]})
    temporal = r.json()["contrasena_temporal"]
    assert r.json()["usuario"]["debe_cambiar"]
    cliente = entrar(servidor, "bea", temporal)
    assert cliente.get("/api/yo").json()["debe_cambiar"] is True
    r = cliente.get("/api/medicos")
    assert r.status_code == 403 and r.json()["detail"] == acceso.CAMBIA_CONTRASENA
    r = cliente.post("/api/yo/contrasena", json={"actual": temporal, "nueva": "corta"})
    assert r.status_code == 422 and "al menos 8" in r.json()["detail"]
    assert cliente.post("/api/yo/contrasena", json={"actual": temporal, "nueva": "la-de-bea-1"}).status_code == 204
    assert cliente.get("/api/medicos").status_code == 200


# --- Cuentas --------------------------------------------------------------------------


def test_cuentas_validacion(admin, equipo_servidor):
    def crear(**datos):
        return admin.post("/api/usuarios", json={"nombre_visible": "X", **datos})

    assert "vinculada a su ficha" in crear(nombre="sin", rol="MEDICO").json()["detail"]
    assert crear(nombre="ana", rol="MEDICO", medico_id=equipo_servidor[0]).status_code == 201
    assert "ya está vinculada" in crear(nombre="ana2", rol="MEDICO", medico_id=equipo_servidor[0]).json()["detail"]
    assert "Ya existe" in crear(nombre="ANA", rol="PLANIFICADOR").json()["detail"]
    assert "solo puede tener" in crear(nombre="con espacio", rol="PLANIFICADOR").json()["detail"]


def test_restablecer_cierra_sus_sesiones(servidor, admin, plani):
    plani_id = next(u["id"] for u in admin.get("/api/usuarios").json() if u["nombre"] == "plani")
    temporal = admin.post(f"/api/usuarios/{plani_id}/restablecer").json()["contrasena_temporal"]
    assert plani.get("/api/medicos").status_code == 401
    assert entrar(servidor, "plani", temporal).get("/api/yo").json()["debe_cambiar"]


def test_desactivar_cierra_sus_sesiones_y_queda_un_administrador(servidor, admin, plani):
    lista = {u["nombre"]: u for u in admin.get("/api/usuarios").json()}
    r = admin.put(f"/api/usuarios/{lista['plani']['id']}",
                  json={"nombre_visible": "P", "rol": "PLANIFICADOR", "activo": False})
    assert r.status_code == 200
    assert plani.get("/api/medicos").status_code == 401
    r = admin.put(f"/api/usuarios/{lista['admin']['id']}", json={"nombre_visible": "A", "rol": "PLANIFICADOR"})
    assert r.status_code == 422 and "a ti mismo" in r.json()["detail"]


def test_dispositivos_conectados_y_cerrar_uno(servidor, admin, plani):
    sesiones = admin.get("/api/sesiones").json()
    assert {s["usuario"] for s in sesiones} == {"admin", "plani"}
    assert [s["actual"] for s in sesiones if s["usuario"] == "admin"] == [True]
    otra = next(s for s in sesiones if s["usuario"] == "plani")
    assert admin.delete(f"/api/sesiones/{otra['id']}").status_code == 204
    assert plani.get("/api/medicos").status_code == 401


def test_el_registro_anota_quien_hizo_cada_cambio(servidor, plani):
    plani.post("/api/medicos", json={"nombre": "X", "codigo": "X"})
    with Session(servidor.state.motor) as sesion:
        ultimo = sesion.scalars(select(RegistroCambio).order_by(RegistroCambio.id.desc())).first()
    assert (ultimo.usuario, ultimo.accion) == ("plani", "Alta de un médico")


# --- Datos ------------------------------------------------------------------------------


def test_importar_conserva_las_cuentas_y_la_copia_no_lleva_sesiones(servidor, admin, equipo_servidor, tmp_path):
    ana = equipo_servidor[0]
    cuenta_medico(servidor, admin, ana)
    copia = admin.get("/api/copia-de-seguridad").content
    fichero = tmp_path / "copia.sqlite"
    fichero.write_bytes(copia)
    with sqlite3.connect(fichero) as c:
        assert c.execute("SELECT count(*) FROM sesion").fetchone() == (0,)
        # Una copia del modo personal: sin usuarios y con los médicos en otro orden.
        c.execute("DELETE FROM usuario")
        c.execute("UPDATE medico SET id = id + 100")
    r = admin.post("/api/importar", content=fichero.read_bytes())
    assert r.status_code == 200, r.text
    # El administrador sigue dentro y la cuenta de Ana sigue vinculada a su ficha (por el código).
    cuentas = {u["nombre"]: u for u in admin.get("/api/usuarios").json()}
    assert set(cuentas) == {"admin", "plani", "ana"}
    assert cuentas["ana"]["medico_id"] == ana + 100


def test_en_el_modo_personal_no_hay_cuentas(cliente):
    assert cliente.get("/api/yo").json() == {"modo": "personal", "id": None, "nombre": None, "nombre_visible": None,
                                             "rol": "ADMINISTRADOR", "medico_id": None, "debe_cambiar": False}
    assert cliente.get("/api/usuarios").status_code == 404
    assert cliente.post("/api/medicos", json={"nombre": "X", "codigo": "X"}).status_code == 201  # sin X-Cliente


def test_contrasenas_con_scrypt():
    guardada = usuarios.resumir_contrasena("una contraseña")
    assert guardada.startswith("scrypt$16384$8$1$") and "una contraseña" not in guardada
    assert usuarios.comprobar_contrasena("una contraseña", guardada)
    assert not usuarios.comprobar_contrasena("otra", guardada)
    assert not usuarios.comprobar_contrasena("x", "no-es-un-resumen")
    assert usuarios.resumir_contrasena("una contraseña") != guardada  # sal distinta


# --- Fase 3: lo que consultan los médicos -----------------------------------------------


def test_meses_publicados(servidor, admin, equipo_servidor):
    ana = equipo_servidor[0]
    medico = cuenta_medico(servidor, admin, ana)
    assert medico.get("/api/periodos/publicados").json() == []  # noviembre es un borrador
    admin.post(f"{URL}/publicar")
    publicados = medico.get("/api/periodos/publicados").json()
    assert [(m["anio"], m["mes"]) for m in publicados] == [(2026, 11)]
    admin.post(f"{URL}/reabrir")
    assert medico.get("/api/periodos/publicados").json() == []
