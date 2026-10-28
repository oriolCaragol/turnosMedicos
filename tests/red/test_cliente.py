"""Lo que usan las aplicaciones de escritorio para conectarse a un servidor
(turnos.arranque.conexion; diseño del modo servidor, 11.2)."""

import ssl
import urllib.error
import urllib.request

import pytest

pytest.importorskip("gi")

from turnos.arranque import conexion as cx  # noqa: E402


@pytest.fixture(autouse=True)
def _configuracion_aparte(tmp_path, monkeypatch):
    monkeypatch.setattr(cx, "carpeta", lambda: tmp_path / "config")


def test_normalizar_la_direccion():
    assert cx.normalizar("turnos.local") == "https://turnos.local:8443"
    assert cx.normalizar(" https://192.168.1.50:9443/ ") == "https://192.168.1.50:9443"
    assert cx.normalizar("http://casa.local:8000") == "http://casa.local:8000"
    with pytest.raises(ValueError):
        cx.normalizar("ftp://x")


def test_guardar_y_leer_la_conexion():
    assert cx.leer() == cx.Conexion()  # sin fichero: este equipo
    cx.guardar(cx.Conexion(modo="servidor", direccion="https://turnos.local:8443", huella="AB", usuario="ana"), "PEM")
    leida = cx.leer()
    assert leida.en_servidor and leida.usuario == "ana"
    assert leida.autoridad.read_text() == "PEM"


def test_resolver_deja_igual_lo_que_no_es_local():
    assert cx.resolver("https://192.168.1.50:8443") == "https://192.168.1.50:8443"
    assert cx.resolver("https://localhost:8443") == "https://localhost:8443"


def test_confirmar_la_autoridad_y_entrar(servidor_red):
    # Primera vez: se descarga sin verificar y su huella es la del servidor.
    pem = cx.descargar_autoridad(servidor_red.base)
    assert pem == servidor_red.autoridad.read_text()
    assert cx.formatear_huella(cx.huella_pem(pem)).count(":") == 31
    conexion = cx.Conexion(modo="servidor", direccion=servidor_red.base, huella=cx.huella_pem(pem))
    cx.guardar(conexion, pem)
    # Después, solo se confía en esa autoridad: se habla con el servidor…
    contexto = cx.contexto_ssl(conexion)
    with urllib.request.urlopen(f"{servidor_red.base}/api/servidor/publico", context=contexto) as r:
        assert r.status == 200
    # …y se entra con usuario y contraseña (la sesión, para la cabecera Authorization).
    respuesta = cx.entrar(conexion, "plani", "contrasena-plani", "Turnos médicos (GNOME)")
    assert respuesta["rol"] == "PLANIFICADOR" and respuesta["token"]
    sesiones = servidor_red.pedir("GET", "/sesiones")
    assert any(s["dispositivo"].startswith("Turnos médicos (GNOME) en ") for s in sesiones)


def test_otra_autoridad_no_vale(servidor_red, tmp_path):
    """Si el servidor cambiara de autoridad (o fuera otro), la conexión se rechaza."""
    from turnos.red import certificados

    otra, _ = certificados.preparar(tmp_path / "otra", "turnos")
    conexion = cx.Conexion(modo="servidor", direccion=servidor_red.base)
    cx.guardar(conexion, otra.autoridad.read_text())
    with pytest.raises(urllib.error.URLError) as error:
        urllib.request.urlopen(f"{servidor_red.base}/api/servidor/publico", context=cx.contexto_ssl(conexion))
    assert isinstance(error.value.reason, ssl.SSLCertVerificationError)
