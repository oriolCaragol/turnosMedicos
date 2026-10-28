"""Prueba de humo del modo escritorio: la ventana GTK real, sin pantalla (Xvfb).

Se salta si no hay PyGObject con GTK 4, libadwaita y WebKitGTK 6.0, xvfb-run o
dbus-run-session.
Se ejecuta sola con: pytest -m escritorio"""

import importlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.escritorio


def _hay_gtk() -> bool:
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        gi.require_version("WebKit", "6.0")
        for modulo in ("Gtk", "Adw", "WebKit"):
            importlib.import_module(f"gi.repository.{modulo}")
    except (ImportError, ValueError):
        return False
    return True


INTERFAZ = Path(__file__).resolve().parents[2] / "interfaz" / "dist"


@pytest.mark.skipif(not _hay_gtk(), reason="sin GTK 4 / libadwaita / WebKitGTK 6.0")
@pytest.mark.skipif(shutil.which("xvfb-run") is None, reason="sin xvfb-run")
@pytest.mark.skipif(shutil.which("dbus-run-session") is None, reason="sin dbus-run-session")
@pytest.mark.skipif(not (INTERFAZ / "index.html").exists(), reason="interfaz sin compilar")
def test_abre_carga_guarda_al_cerrar_y_detiene_el_servidor(tmp_path):
    datos = tmp_path / "turnos.sqlite"
    # Sin servicios activables (portales, gvfs, accesibilidad): en una sesión vacía no
    # funcionan y solo retrasan el arranque.
    configuracion_dbus = tmp_path / "sesion.conf"
    configuracion_dbus.write_text(
        '<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"'
        ' "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">'
        "<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen>"
        '<policy context="default"><allow send_destination="*" eavesdrop="true"/>'
        '<allow eavesdrop="true"/><allow own="*"/></policy></busconfig>'
    )
    entorno = {
        **os.environ,
        "TURNOS_DATOS": str(datos),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "GDK_BACKEND": "x11",
        "GDK_DEBUG": "no-portals",
        "LIBGL_ALWAYS_SOFTWARE": "1",
        "NO_AT_BRIDGE": "1",
        "GTK_A11Y": "none",
    }
    proceso = subprocess.run(
        # Sesión de D-Bus propia: si la aplicación ya está abierta, no se le pasa el control.
        ["dbus-run-session", f"--config-file={configuracion_dbus}", "--", "xvfb-run", "-a", "-s", "-screen 0 1400x1000x24", sys.executable, str(Path(__file__).with_name("humo.py"))],
        env=entorno, capture_output=True, text=True, timeout=90,
    )
    lineas = [linea for linea in proceso.stdout.splitlines() if linea.startswith("{")]
    assert lineas, proceso.stdout + proceso.stderr
    resultado = json.loads(lineas[-1])

    assert resultado["preguntado"]  # sin conexión guardada: la pantalla de inicio
    assert resultado["cargada"]
    assert resultado["titulo"] == "Turnos médicos"
    assert resultado["salida"] == 0
    assert resultado["servidor_detenido"]
    with sqlite3.connect(datos) as conexion:
        assert conexion.execute("SELECT nombre FROM medico").fetchall() == [("Al cerrar",)]
    assert (tmp_path / "config" / "turnosMedicos" / "ventana.json").exists()


@pytest.mark.skipif(not _hay_gtk(), reason="sin GTK 4 / libadwaita / WebKitGTK 6.0")
@pytest.mark.skipif(shutil.which("xvfb-run") is None, reason="sin xvfb-run")
@pytest.mark.skipif(shutil.which("dbus-run-session") is None, reason="sin dbus-run-session")
@pytest.mark.skipif(not (INTERFAZ / "index.html").exists(), reason="interfaz sin compilar")
def test_como_cliente_de_un_servidor_y_recuerda_la_sesion(tmp_path, servidor_red):
    """Con la conexión apuntando a un servidor: carga su interfaz por HTTPS con la autoridad
    confirmada, sin servidor interno; tras entrar, la sesión sigue al volver a abrir."""
    from turnos.arranque.conexion import huella_pem

    configuracion = tmp_path / "config" / "turnosMedicos"
    configuracion.mkdir(parents=True)
    pem = servidor_red.autoridad.read_text()
    (configuracion / "conexion-autoridad.pem").write_text(pem)
    (configuracion / "conexion.json").write_text(json.dumps(
        {"modo": "servidor", "direccion": servidor_red.base, "huella": huella_pem(pem), "usuario": "", "preguntar": False}))
    dbus = tmp_path / "sesion.conf"
    dbus.write_text(
        '<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"'
        ' "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">'
        "<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen>"
        '<policy context="default"><allow send_destination="*" eavesdrop="true"/>'
        '<allow eavesdrop="true"/><allow own="*"/></policy></busconfig>'
    )
    entorno = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "config"), "XDG_DATA_HOME": str(tmp_path / "datos"),
               "XDG_CACHE_HOME": str(tmp_path / "cache"), "GDK_BACKEND": "x11", "GDK_DEBUG": "no-portals",
               "LIBGL_ALWAYS_SOFTWARE": "1", "NO_AT_BRIDGE": "1", "GTK_A11Y": "none"}

    def abrir(*argumentos):
        proceso = subprocess.run(
            ["dbus-run-session", f"--config-file={dbus}", "--", "xvfb-run", "-a", "-s", "-screen 0 1400x1000x24",
             sys.executable, str(Path(__file__).with_name("humo_cliente.py")), *argumentos],
            env=entorno, capture_output=True, text=True, timeout=90,
        )
        lineas = [linea for linea in proceso.stdout.splitlines() if linea.startswith("{")]
        assert lineas, proceso.stdout + proceso.stderr
        return json.loads(lineas[-1])

    primera = abrir("entrar")
    assert primera["servidor_interno"] is False and primera["uri"].startswith(servidor_red.base), primera
    assert primera["vistas"][0] == "Entrar"  # sin sesión: la página de entrada
    assert "Calendario" in primera["vistas"][1]  # tras entrar como planificador
    # Al volver a abrir, la sesión sigue (cookie guardada).
    segunda = abrir()
    assert "Calendario" in segunda["vistas"][0], segunda
