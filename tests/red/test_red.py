"""Modo servidor: configuración, certificados, copias y la orden `turnos servidor`
(diseño del modo servidor, 7 y 10)."""

import json
import plistlib
import signal
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.x509 import verification

from turnos.red import certificados, copias
from turnos.red.configuracion import ErrorConfiguracion, leer_configuracion


# --- Configuración ---------------------------------------------------------------------


def test_configuracion_por_defecto_aparte_de_los_datos_personales(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr("turnos.red.configuracion.buscar_configuracion", lambda: None)
    config = leer_configuracion()
    assert (config.puerto, config.https, config.direccion, config.nombre) == (8443, True, "0.0.0.0", "turnos")
    assert config.datos == tmp_path / "turnosMedicos" / "servidor" / "turnos.sqlite"
    assert config.copias == config.datos.parent / "copias"
    assert config.certificados == config.datos.parent / "certificados"


def test_leer_servidor_toml(tmp_path):
    fichero = tmp_path / "servidor.toml"
    fichero.write_text('[red]\npuerto = 9443\nnombre = "casa"\n[datos]\nruta = "/var/lib/turnos/turnos.sqlite"\n'
                       'conservar_copias = 7\n[seguridad]\nhttps = false\n', encoding="utf-8")
    config = leer_configuracion(fichero)
    assert (config.puerto, config.nombre, config.conservar_copias, config.https) == (9443, "casa", 7, False)
    assert str(config.copias) == "/var/lib/turnos/copias"
    fichero.write_text("[red]\npuerto = \n", encoding="utf-8")
    with pytest.raises(ErrorConfiguracion):
        leer_configuracion(fichero)


# --- Certificados ----------------------------------------------------------------------


def _verificar(ficheros, nombre: str):
    """Verifica la cadena como un navegador (incluidas las restricciones de nombre)."""
    raiz = certificados.leer_certificado(ficheros.autoridad)
    hoja = certificados.leer_certificado(ficheros.servidor)
    sujeto = (x509.IPAddress(__import__("ipaddress").ip_address(nombre)) if nombre[0].isdigit()
              else x509.DNSName(nombre))
    almacen = verification.Store([raiz])
    politica = verification.PolicyBuilder().store(almacen).time(datetime.now(timezone.utc))
    if isinstance(sujeto, x509.DNSName):
        verificador = politica.build_server_verifier(verification.DNSName(nombre))
    else:
        verificador = politica.build_server_verifier(verification.IPAddress(sujeto.value))
    return verificador.verify(hoja, [])


def test_autoridad_y_certificado_del_servidor(tmp_path):
    ficheros, creado = certificados.preparar(tmp_path / "certificados", "turnos")
    assert creado
    autoridad = certificados.leer_certificado(ficheros.autoridad)
    servidor = certificados.leer_certificado(ficheros.servidor)
    # Restricciones de nombre: solo .local, localhost y redes privadas.
    restricciones = autoridad.extensions.get_extension_for_class(x509.NameConstraints)
    assert restricciones.critical
    assert x509.DNSName("local") in restricciones.value.permitted_subtrees
    # Un año, con los nombres y direcciones del equipo.
    assert timedelta(days=364) < servidor.not_valid_after_utc - servidor.not_valid_before_utc < timedelta(days=366)
    nombres = servidor.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert "turnos.local" in nombres.get_values_for_type(x509.DNSName)
    # La cadena es válida para turnos.local, localhost y 127.0.0.1.
    for nombre in ("turnos.local", "localhost", "127.0.0.1"):
        _verificar(ficheros, nombre)
    # Las claves, solo para el dueño.
    assert oct(ficheros.clave_autoridad.stat().st_mode & 0o777) == "0o600"
    assert oct(ficheros.clave_servidor.stat().st_mode & 0o777) == "0o600"


def test_la_autoridad_no_vale_para_webs_de_internet(tmp_path):
    """Aunque alguien se hiciera con la clave de la autoridad y firmara un certificado
    para un nombre de internet, no sería válido."""
    ficheros, _ = certificados.preparar(tmp_path, "turnos")
    monkey = pytest.MonkeyPatch()
    monkey.setattr(certificados, "nombres_del_servidor", lambda _n: (["www.banco.es"], []))
    certificados.crear_certificado_servidor(ficheros, "turnos")
    monkey.undo()
    with pytest.raises(verification.VerificationError):
        _verificar(ficheros, "www.banco.es")


def test_renovar_solo_cuando_hace_falta(tmp_path, monkeypatch):
    ficheros, _ = certificados.preparar(tmp_path, "turnos")
    antes = ficheros.servidor.read_bytes()
    autoridad = ficheros.autoridad.read_bytes()
    assert certificados.preparar(tmp_path, "turnos") == (ficheros, False)
    # Otra IP en la red (DHCP): se renueva, con la misma autoridad.
    monkeypatch.setattr(certificados, "direcciones_locales", lambda: ["192.168.50.7"])
    assert certificados.preparar(tmp_path, "turnos")[1]
    assert ficheros.servidor.read_bytes() != antes and ficheros.autoridad.read_bytes() == autoridad
    # A menos de un mes de caducar, también.
    monkeypatch.setattr(certificados, "DURACION_SERVIDOR", timedelta(days=20))
    certificados.crear_certificado_servidor(ficheros, "turnos")
    assert certificados.preparar(tmp_path, "turnos")[1]


def test_perfil_para_iphone(tmp_path):
    ficheros, _ = certificados.preparar(tmp_path, "turnos")
    perfil = plistlib.loads(certificados.perfil_ios(ficheros))
    contenido = perfil["PayloadContent"][0]
    assert contenido["PayloadType"] == "com.apple.security.root"
    assert contenido["PayloadContent"] == certificados.autoridad_der(ficheros)
    assert perfil["PayloadIdentifier"] == plistlib.loads(certificados.perfil_ios(ficheros))["PayloadIdentifier"]


# --- Copias ----------------------------------------------------------------------------


def test_copia_diaria_y_limpieza(tmp_path):
    from turnos.datos.bd import inicializar

    datos = tmp_path / "turnos.sqlite"
    inicializar(datos, wal=True).dispose()
    carpeta = tmp_path / "copias"
    hoy = date(2026, 10, 18)
    for dias in (20, 14, 13, 1):
        copias.copia_diaria(datos, carpeta, conservar=14, hoy=hoy - timedelta(days=dias))
    manual = copias.copiar_ahora(datos, carpeta)
    assert copias.copia_diaria(datos, carpeta, conservar=14, hoy=hoy) is not None
    assert copias.copia_diaria(datos, carpeta, conservar=14, hoy=hoy) is None  # ya estaba
    nombres = sorted(f.name for f in carpeta.iterdir())
    assert nombres == sorted(["turnos-20261005.sqlite", "turnos-20261017.sqlite", "turnos-20261018.sqlite", manual.name])
    # Cada copia es un único fichero completo (sin -wal).
    assert not list(carpeta.glob("*-wal"))
    assert copias.listar(carpeta)[0].tamano > 0


# --- La orden y un servidor real ---------------------------------------------------------


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _turnos(*argumentos, entrada=None, **opciones):
    return subprocess.run([sys.executable, "-m", "turnos", "servidor", *argumentos], input=entrada,
                          capture_output=True, text=True, timeout=60, **opciones)


def test_crear_administrador_desde_la_terminal(tmp_path):
    datos = tmp_path / "turnos.sqlite"
    r = _turnos("crear-administrador", "--datos", str(datos), "--usuario", "Admin", entrada="contrasena-larga\n")
    assert r.returncode == 0 and "Administrador «admin» creado." in r.stdout, r.stderr
    r = _turnos("crear-administrador", "--datos", str(datos), "--usuario", "admin", entrada="contrasena-larga\n")
    assert r.returncode != 0 and "Ya existe" in r.stderr
    r = _turnos("crear-administrador", "--datos", str(datos), "--usuario", "otro", entrada="corta\n")
    assert r.returncode != 0 and "al menos 8" in r.stderr


def test_servidor_https_de_principio_a_fin(tmp_path):
    datos, puerto = tmp_path / "turnos.sqlite", _puerto_libre()
    _turnos("crear-administrador", "--datos", str(datos), "--usuario", "admin", entrada="contrasena-larga\n")
    proceso = subprocess.Popen(
        [sys.executable, "-m", "turnos", "servidor", "--datos", str(datos), "--puerto", str(puerto), "--sin-anuncio"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        base = f"https://localhost:{puerto}"
        for _ in range(100):
            try:
                contexto = ssl.create_default_context(cafile=str(tmp_path / "certificados" / "autoridad.crt"))
                with urllib.request.urlopen(f"{base}/api/servidor/publico", context=contexto, timeout=2) as r:
                    assert json.load(r)["https"] is True
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("el servidor no arrancó")
        # Entrar y consultar.
        peticion = urllib.request.Request(
            f"{base}/api/sesion", method="POST", headers={"Content-Type": "application/json", "X-Cliente": "x"},
            data=json.dumps({"usuario": "admin", "contrasena": "contrasena-larga", "aplicacion": True}).encode())
        with urllib.request.urlopen(peticion, context=contexto) as r:
            token = json.load(r)["token"]
        autorizado = {"Authorization": f"Bearer {token}"}
        with urllib.request.urlopen(urllib.request.Request(f"{base}/api/servidor", headers=autorizado),
                                    context=contexto) as r:
            info = json.load(r)
        assert info["direcciones"][0] == f"https://turnos.local:{puerto}/"
        assert [c["nombre"] for c in info["copias"]] == [f"turnos-{date.today():%Y%m%d}.sqlite"]  # la diaria
        # El certificado de la autoridad se descarga sin sesión.
        with urllib.request.urlopen(f"{base}/certificado/turnos-autoridad.crt", context=contexto) as r:
            assert r.read() == certificados.autoridad_der(certificados.Ficheros(tmp_path / "certificados"))
        # Sin la autoridad, el navegador desconfía.
        with pytest.raises(urllib.error.URLError):
            urllib.request.urlopen(f"{base}/api/servidor/publico", context=ssl.create_default_context(), timeout=5)
        # Con un cliente de eventos conectado, para enseguida.
        eventos = urllib.request.urlopen(urllib.request.Request(f"{base}/api/eventos", headers=autorizado),
                                         context=contexto, timeout=10)
        eventos.readline()
        inicio = time.monotonic()
        proceso.send_signal(signal.SIGTERM)
        proceso.wait(10)
        assert time.monotonic() - inicio < 4
    finally:
        if proceso.poll() is None:
            proceso.kill()
        salida = proceso.stdout.read()
    assert "Turnos médicos (HTTPS)" in salida and "Huella de la autoridad" in salida


def test_configuracion_de_ejemplo():
    r = _turnos("configuracion")
    assert "[seguridad]" in r.stdout and "https = true" in r.stdout


def test_medir_con_una_copia_sin_cambiar_los_datos(tmp_path):
    from turnos.red.medir import medir

    sin_datos = medir(None, 2026, 11)
    assert sin_datos.origen == "equipo de ejemplo" and sin_datos.medicos == 12 and sin_datos.segundos > 0
    assert "Generar un mes" in sin_datos.informe()

    from fastapi.testclient import TestClient

    from turnos.api.app import crear_app
    from turnos.datos.bd import inicializar

    datos = tmp_path / "turnos.sqlite"
    motor = inicializar(datos)
    api = TestClient(crear_app(motor, interfaz=None))
    m = api.post("/api/medicos", json={"nombre": "Ana", "codigo": "ANA"}).json()
    api.put(f"/api/medicos/{m['id']}/reglas", json={"vigente_desde": "2026-11-01", "elegibilidad": [],
                                                     "carga": {"minimo": 0, "maximo": 40}})
    motor.dispose()
    antes = datos.read_bytes()
    medida = medir(datos, 2026, 11)
    assert medida.medicos == 1 and medida.origen.startswith("copia de")
    assert datos.read_bytes() == antes  # el mes se ha generado en la copia
