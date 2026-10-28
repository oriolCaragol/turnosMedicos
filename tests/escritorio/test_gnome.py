"""Prueba de la interfaz nativa GNOME (prototipo) con Xvfb: acciones reales desde los widgets.

Se salta si no hay GTK 4 y libadwaita ≥ 1.7, xvfb-run o dbus-run-session.
Se ejecuta sola con: pytest -m escritorio"""

import json
import re
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from turnos.api.app import crear_app
from turnos.datos.bd import inicializar

pytestmark = pytest.mark.escritorio


def _hay_adwaita() -> bool:
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw

        return hasattr(Adw, "ToggleGroup")
    except (ImportError, ValueError):
        return False


def _preparar(tmp_path):
    """Equipo de 5 médicos, cobertura de 2–3 por la tarde, y la sesión de D-Bus de la prueba."""
    datos = tmp_path / "turnos.sqlite"
    api = TestClient(crear_app(inicializar(datos), interfaz=None))
    for i, nombre in enumerate(["Ana Ruiz", "Bea Gil", "Carlos Paz", "Dani Sanz", "Eva Mora"]):
        m = api.post("/api/medicos", json={"nombre": nombre, "codigo": f"M{i}"}).json()
        api.put(f"/api/medicos/{m['id']}/reglas",
                json={"vigente_desde": "2026-11-01", "elegibilidad": [], "carga": {"minimo": 0, "maximo": 40}})
    api.put("/api/cobertura/semanal", json=[
        {"dia_semana": d, "mitad": h, "minimo": 2 if h[0] == "T" else 1, "maximo": 3 if h[0] == "T" else 2}
        for d in range(5) for h in ("M1", "M2", "T1", "T2")
    ])
    api.put("/api/ajustes", json={"todos_trabajan": False, "roles_segun_presencia": True, "municipio": "28079"})
    conf = tmp_path / "sesion.conf"
    conf.write_text(
        '<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"'
        ' "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">'
        "<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen>"
        '<policy context="default"><allow send_destination="*" eavesdrop="true"/>'
        '<allow eavesdrop="true"/><allow own="*"/></policy></busconfig>'
    )
    return api, datos, conf


def _ejecutar(programa: str, datos, conf, *argumentos, configuracion=None, preguntar=False) -> dict:
    # Configuración y datos de usuario aparte: la prueba no ve la conexión (ni el tamaño de
    # ventana) del usuario real, y no la cambia. Por defecto, en este equipo sin preguntar
    # al abrir (la pantalla de inicio tiene sus propias pruebas).
    if configuracion is None:
        configuracion = Path(datos).parent / "config"
        if not preguntar:
            (configuracion / "turnosMedicos").mkdir(parents=True, exist_ok=True)
            (configuracion / "turnosMedicos" / "conexion.json").write_text('{"modo": "personal", "preguntar": false}')
    entorno = {**os.environ, "TURNOS_DATOS": str(datos), "GDK_BACKEND": "x11", "GDK_DEBUG": "no-portals",
               "LIBGL_ALWAYS_SOFTWARE": "1", "NO_AT_BRIDGE": "1", "GTK_A11Y": "none",
               "XDG_CONFIG_HOME": str(configuracion),
               "XDG_DATA_HOME": str(Path(datos).parent / "datos-usuario")}
    proceso = subprocess.run(
        ["dbus-run-session", f"--config-file={conf}", "--", "xvfb-run", "-a", "-s", "-screen 0 1400x1000x24",
         sys.executable, str(Path(__file__).with_name(programa)), *argumentos],
        env=entorno, capture_output=True, text=True, timeout=150,
    )
    lineas = [linea for linea in proceso.stdout.splitlines() if linea.startswith("{")]
    assert lineas, proceso.stdout + proceso.stderr
    return json.loads(lineas[-1])


requiere_gtk = [
    pytest.mark.skipif(not _hay_adwaita(), reason="sin GTK 4 / libadwaita 1.7"),
    pytest.mark.skipif(shutil.which("xvfb-run") is None, reason="sin xvfb-run"),
    pytest.mark.skipif(shutil.which("dbus-run-session") is None, reason="sin dbus-run-session"),
]


@requiere_gtk[0]
@requiere_gtk[1]
@requiere_gtk[2]
def test_generar_retocar_y_guardar_desde_la_interfaz_nativa(tmp_path):
    api, datos, conf = _preparar(tmp_path)
    r = _ejecutar("gnome_humo.py", datos, conf)
    assert r["errores"] == []
    assert r["estado"] == "BORRADOR"
    assert r["en_la_tarde_despues"] == r["en_la_tarde_antes"] - 1

    cal = api.get("/api/periodos/2026/11").json()
    nombres = {m["id"]: m["nombre"] for m in cal["medicos"]}
    urgencias = next(x for x in cal["roles"] if x["fecha"] == "2026-11-04" and x["rol"] == "URGENCIAS")
    assert nombres[urgencias["medico_id"]] == r["nuevo_de_urgencias"] and urgencias["manual"]
    assert any(a["bloqueada"] for a in cal["asignaciones"] if a["fecha"] == "2026-11-04")

    primero = sorted(cal["medicos"], key=lambda m: m["nombre"])[0]  # la API los lista por nombre
    reglas = api.get(f"/api/medicos/{primero['id']}/reglas", params={"fecha": "2026-11-01"}).json()
    assert reglas["carga"]["maximo"] == 60
    assert {"dia_semana": 0, "turno": "MANANA", "valor": "NO_DISPONIBLE"} in reglas["elegibilidad"]
    assert "Nochebuena" in [f["descripcion"] for f in api.get("/api/festivos", params={"anio": 2026}).json()]


@requiere_gtk[0]
@requiere_gtk[1]
@requiere_gtk[2]
def test_resto_de_funciones_desde_la_interfaz_nativa(tmp_path):
    api, datos, conf = _preparar(tmp_path)
    r = _ejecutar("gnome_completa.py", datos, conf, str(tmp_path))
    assert r["errores"] == [] and r["pasos_sin_hacer"] == 0, r

    # Calendario: alternativa distinta, deshacer y rehacer, arrastre y rango del mes.
    assert r["alternativa_distinta"] and r["deshacer_vuelve"] and r["rehacer_vuelve"]
    cal = api.get("/api/periodos/2026/11").json()
    medico = r["arrastrado"]
    suyas = {(a["fecha"], a["mitad"]) for a in cal["asignaciones"] if a["medico_id"] == medico}
    assert ("2026-11-04", "M1") not in suyas and {("2026-11-05", "T1"), ("2026-11-05", "T2")} <= suyas
    rango = next(m for m in cal["medicos"] if m["id"] == r["rango_medico"])
    assert rango["carga_manual"] and (rango["minimo"], rango["maximo"]) == (2, 30)
    for nombre, paginas in (("calendario.pdf", 2), ("roles.pdf", 1)):
        assert (tmp_path / nombre).read_bytes().startswith(b"%PDF")
        if shutil.which("pdfinfo"):  # cuenta las páginas (la estructura del PDF va comprimida)
            info = subprocess.run(["pdfinfo", str(tmp_path / nombre)], capture_output=True, text=True).stdout
            assert re.search(rf"^Pages:\s+{paginas}$", info, re.M), info

    # Médicos: ausencia y más reglas.
    primero = sorted(cal["medicos"], key=lambda m: m["nombre"])[0]
    ausencias = api.get("/api/ausencias", params={"desde": "2026-11-01"}).json()
    assert [(a["medico_id"], a["desde"]) for a in ausencias] == [(primero["id"], "2026-11-01")]
    reglas = api.get(f"/api/medicos/{primero['id']}/reglas", params={"fecha": "2026-11-01"}).json()
    assert reglas["jornadas"] == [{"dia_semana": 2, "tipo": "DOBLE"}]
    assert reglas["carga_por_turno"] == [{"turno": "TARDE", "minimo": 4, "maximo": 16}]
    assert reglas["preferencias"] == [{"dia_semana": 4, "turno": "TARDE", "valor": "EVITA"}]

    # Turno rotativo, cobertura, horarios y festivos.
    rotacion = api.get("/api/rotaciones").json()[0]
    assert rotacion["nombre"] == "Lunes de mañana" and rotacion["medicos"] == r["rotacion_medicos"]
    assert rotacion["huecos"] == [{"dia_semana": 0, "turno": "MANANA"}]
    viernes = {c["mitad"]: c for c in api.get("/api/cobertura/semanal").json() if c["dia_semana"] == 4}
    assert viernes["T1"]["maximo"] == viernes["T2"]["maximo"] == 4
    assert {c["mitad"]: c["maximo"] for c in api.get("/api/cobertura/fechas").json()} == {"M1": 1, "M2": 1, "T1": 2, "T2": 2}
    assert next(h for h in api.get("/api/horarios").json() if h["turno"] == "MANANA")["inicio"] == "08:30:00"


@requiere_gtk[0]
@requiere_gtk[1]
@requiere_gtk[2]
def test_la_interfaz_nativa_ve_los_cambios_de_otro_cliente(tmp_path):
    api, datos, conf = _preparar(tmp_path)
    r = _ejecutar("gnome_varios.py", datos, conf)
    assert r["errores"] == [] and r["pasos_sin_hacer"] == 0, r
    # Lo ve sin recargar y ya no deshace (no se deshace lo que hizo otro).
    assert r["visto_sin_recargar"] and r["puede_deshacer_antes"] and not r["puede_deshacer_despues"]
    # Con una versión antigua, el cambio se rechaza y se muestra la actual.
    assert r["version_antigua"] < r["version_final"] == r["version_mostrada"]
    cal = api.get("/api/periodos/2026/11").json()
    assert cal["version"] == r["version_final"]
    assert any(a["fecha"] == "2026-11-06" for a in cal["asignaciones"])


def _configurar_cliente(tmp_path, servidor_red) -> Path:
    """La configuración de una aplicación ya conectada a `servidor_red` (huella confirmada)."""
    from turnos.arranque.conexion import huella_pem

    carpeta = tmp_path / "config"
    (carpeta / "turnosMedicos").mkdir(parents=True)
    pem = servidor_red.autoridad.read_text()
    (carpeta / "turnosMedicos" / "conexion-autoridad.pem").write_text(pem)
    (carpeta / "turnosMedicos" / "conexion.json").write_text(json.dumps(
        {"modo": "servidor", "direccion": servidor_red.base, "huella": huella_pem(pem), "usuario": "", "preguntar": False}))
    return carpeta


@requiere_gtk[0]
@requiere_gtk[1]
@requiere_gtk[2]
def test_la_interfaz_nativa_como_cliente_de_un_servidor(tmp_path, servidor_red):
    _, datos, conf = _preparar(tmp_path)
    configuracion = _configurar_cliente(tmp_path, servidor_red)
    r = _ejecutar("gnome_cliente.py", datos, conf, "plani", configuracion=configuracion)
    assert r["errores"] == [] and r["pasos_sin_hacer"] == 0, r
    assert r["usuario"] == "Pablo Planificador" and r["estado"] == "BORRADOR"
    # Lo ha generado en el servidor, como «plani», y sin servidor interno.
    assert servidor_red.pedir("GET", "/periodos/2026/11")["estado"] == "BORRADOR"
    assert servidor_red.pedir("GET", "/registro?limite=1")[0]["usuario"] == "plani"
    assert r["servidor_interno"] is False
    # Recuerda el usuario para la próxima vez.
    assert json.loads((configuracion / "turnosMedicos" / "conexion.json").read_text())["usuario"] == "plani"


@requiere_gtk[0]
@requiere_gtk[1]
@requiere_gtk[2]
def test_un_medico_en_la_interfaz_nativa_va_a_la_web(tmp_path, servidor_red):
    _, datos, conf = _preparar(tmp_path)
    r = _ejecutar("gnome_cliente.py", datos, conf, "ana", configuracion=_configurar_cliente(tmp_path, servidor_red))
    assert r["errores"] == [] and r["pasos_sin_hacer"] == 0, r
    assert r["titulo"] == "Hola, Ana Ruiz"


@requiere_gtk[0]
@requiere_gtk[1]
@requiere_gtk[2]
def test_bandeja_de_solicitudes_en_la_interfaz_nativa(tmp_path, servidor_red):
    _, datos, conf = _preparar(tmp_path)
    pedida = servidor_red.pedir("POST", "/solicitudes", {
        "propuesta": {"tipo": "AUSENCIA", "accion": "CREAR", "desde": "2026-12-09", "hasta": "2026-12-09"},
        "comentario": "Médico"}, usuario=("ana", "contrasena-ana"))
    r = _ejecutar("gnome_cliente.py", datos, conf, "bandeja", configuracion=_configurar_cliente(tmp_path, servidor_red))
    assert r["errores"] == [] and r["pasos_sin_hacer"] == 0, r
    assert r["contador"] == 1 and r["contador_despues"] == 0 and r["solicitud"] == pedida["id"]
    assert r["efectos"] == "Aprobarla no produce avisos nuevos en el calendario"
    resuelta = servidor_red.pedir("GET", "/solicitudes")[0]
    assert (resuelta["estado"], resuelta["comentario_resolucion"], resuelta["resuelta_por"]) == (
        "APROBADA", "Aprobada desde la nativa", "Pablo Planificador")
    ana = next(m["id"] for m in servidor_red.pedir("GET", "/medicos") if m["codigo"] == "ANA")
    assert [a["desde"] for a in servidor_red.pedir("GET", f"/ausencias?medico_id={ana}")] == ["2026-12-09"]


@requiere_gtk[0]
@requiere_gtk[1]
@requiere_gtk[2]
def test_al_abrir_se_elige_trabajar_en_este_equipo(tmp_path):
    _, datos, conf = _preparar(tmp_path)
    r = _ejecutar("gnome_inicio.py", datos, conf, "local", preguntar=True)
    assert r["errores"] == [] and r["pasos_sin_hacer"] == 0, r
    assert r["servidor_interno"] is True and r["estado"] in ("SIN_GENERAR", "BORRADOR")
    guardada = json.loads((Path(datos).parent / "config" / "turnosMedicos" / "conexion.json").read_text())
    assert guardada["modo"] == "personal" and guardada["preguntar"] is True  # sin «recordar»: preguntará otra vez


@requiere_gtk[0]
@requiere_gtk[1]
@requiere_gtk[2]
def test_al_abrir_se_elige_un_servidor_y_se_confirma_su_huella(tmp_path, servidor_red):
    _, datos, conf = _preparar(tmp_path)
    r = _ejecutar("gnome_inicio.py", datos, conf, servidor_red.base, preguntar=True)
    assert r["errores"] == [] and r["pasos_sin_hacer"] == 0, r
    assert r["servidor_interno"] is False and r["usuario"] == "Pablo Planificador"
    assert r["huella"] in r["texto_confirmacion"]
    guardada = json.loads((Path(datos).parent / "config" / "turnosMedicos" / "conexion.json").read_text())
    assert (guardada["modo"], guardada["direccion"], guardada["preguntar"]) == ("servidor", servidor_red.base, False)


def test_soltar_un_medico_como_en_la_web():
    from turnos.arranque.gnome.calendario import cambios_al_soltar

    cal = {"asignaciones": [
        {"medico_id": 1, "fecha": "2026-11-03", "mitad": "M1"}, {"medico_id": 1, "fecha": "2026-11-03", "mitad": "M2"},
        {"medico_id": 2, "fecha": "2026-11-03", "mitad": "T1"}, {"medico_id": 2, "fecha": "2026-11-03", "mitad": "T2"},
    ]}
    celda = {"tipo": "celda", "medico": 1, "fecha": "2026-11-03", "turno": "MANANA"}
    tarde4 = {"fecha": "2026-11-04", "turno": "TARDE"}
    # Mover: sale de la mañana del 3 y entra en la tarde del 4.
    assert cambios_al_soltar(cal, celda, tarde4) == [
        {"medico_id": 1, "fecha": "2026-11-03", "mitades": []},
        {"medico_id": 1, "fecha": "2026-11-04", "mitades": ["T1", "T2"]},
    ]
    # Copiar (Ctrl): se queda también en el origen.
    assert cambios_al_soltar(cal, celda, tarde4, copiar=True) == [{"medico_id": 1, "fecha": "2026-11-04", "mitades": ["T1", "T2"]}]
    # Mismo día, otro turno: mañana y tarde a la vez solo si se copia.
    assert cambios_al_soltar(cal, celda, {"fecha": "2026-11-03", "turno": "TARDE"}, copiar=True) == [
        {"medico_id": 1, "fecha": "2026-11-03", "mitades": ["M1", "M2", "T1", "T2"]}]
    # Soltar fuera: lo quita. Soltar en el mismo turno: nada.
    assert cambios_al_soltar(cal, celda, None) == [{"medico_id": 1, "fecha": "2026-11-03", "mitades": []}]
    assert cambios_al_soltar(cal, celda, {"fecha": "2026-11-03", "turno": "MANANA"}) == []
    # Desde la tabla de carga: lo añade (si ya estaba, nada).
    assert cambios_al_soltar(cal, {"tipo": "resumen", "medico": 2}, {"fecha": "2026-11-03", "turno": "MANANA"}) == [
        {"medico_id": 2, "fecha": "2026-11-03", "mitades": ["M1", "M2", "T1", "T2"]}]
    assert cambios_al_soltar(cal, {"tipo": "resumen", "medico": 2}, {"fecha": "2026-11-03", "turno": "TARDE"}) == []


def test_orden_estable_de_los_medicos_como_en_la_web():
    from turnos.arranque.gnome.medicos import orden_estable

    assert orden_estable(None, [3, 1, 2]) == [3, 1, 2]
    assert orden_estable([1, 2, 3], [4, 1, 2, 3]) == [1, 2, 3, 4]  # el nuevo, al final
    assert orden_estable([1, 2, 3, 4], [1, 4, 2, 3]) == [1, 2, 3, 4]  # cambiar el nombre no lo mueve
    assert orden_estable([1, 2, 3], [3, 1]) == [1, 3]
