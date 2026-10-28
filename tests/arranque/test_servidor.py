"""Arranque compartido por los modos web y escritorio."""

import json
import socket
import urllib.error
import urllib.request

import pytest

from turnos.arranque.servidor import preparar


def _leer(url, cabeceras=None):
    peticion = urllib.request.Request(url, headers=cabeceras or {})
    with urllib.request.urlopen(peticion, timeout=5) as r:
        return r.status, json.loads(r.read())


def test_puerto_libre_al_azar_y_token(tmp_path):
    servidor = preparar(ruta=tmp_path / "t.sqlite")
    servidor.iniciar_en_hilo()
    try:
        assert servidor.puerto > 0
        assert servidor.url == f"http://127.0.0.1:{servidor.puerto}/?token={servidor.token}"
        base = f"http://127.0.0.1:{servidor.puerto}/api/medicos"
        with pytest.raises(urllib.error.HTTPError) as error:
            _leer(base)
        assert error.value.code == 401
        assert _leer(base, {"X-Turnos-Token": servidor.token}) == (200, [])
    finally:
        servidor.detener()
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", servidor.puerto), timeout=1)


def test_dos_servidores_no_comparten_puerto_ni_token(tmp_path):
    a = preparar(ruta=tmp_path / "a.sqlite")
    b = preparar(ruta=tmp_path / "b.sqlite")
    try:
        assert a.puerto != b.puerto and a.token != b.token
    finally:
        a._socket.close()
        b._socket.close()


def test_sin_token(tmp_path):
    servidor = preparar(ruta=tmp_path / "t.sqlite", con_token=False)
    servidor.iniciar_en_hilo()
    try:
        assert servidor.url == f"http://127.0.0.1:{servidor.puerto}/"
        assert _leer(servidor.url + "api/medicos")[0] == 200
    finally:
        servidor.detener()


def test_puerto_ocupado(tmp_path):
    ocupado = socket.socket()
    ocupado.bind(("127.0.0.1", 0))
    ocupado.listen()
    try:
        with pytest.raises(OSError):
            preparar(ruta=tmp_path / "t.sqlite", puerto=ocupado.getsockname()[1])
    finally:
        ocupado.close()


def test_el_modo_web_avisa_si_los_datos_son_mas_nuevos(tmp_path, monkeypatch):
    import sqlite3

    from turnos.arranque import web
    from turnos.datos.bd import inicializar

    ruta = tmp_path / "t.sqlite"
    inicializar(ruta).dispose()
    with sqlite3.connect(ruta) as conexion:
        conexion.execute("UPDATE alembic_version SET version_num = 'futura'")
    monkeypatch.setenv("TURNOS_DATOS", str(ruta))
    monkeypatch.setenv("TURNOS_PUERTO", "0")
    with pytest.raises(SystemExit, match="versión más reciente"):
        web.main()
