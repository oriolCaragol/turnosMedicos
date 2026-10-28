"""`turnos servidor`: el modo servidor en la red doméstica (diseño del modo servidor, 10).

    turnos servidor                       arranca (servidor.toml o los valores por defecto)
    turnos servidor crear-administrador   primer usuario (solo desde la terminal del servidor)
    turnos servidor certificado           (re)genera el certificado; --nueva-autoridad, también la autoridad
    turnos servidor copia                 copia de seguridad inmediata
    turnos servidor configuracion         muestra un servidor.toml de ejemplo
    turnos servidor medir [--mes AAAA-MM] cuánto tarda el motor en este equipo (con una copia de los datos)

Opciones comunes: --config FICHERO, --datos RUTA. Para arrancar, además: --puerto N,
--sin-https (solo para pruebas: los datos y las contraseñas irían sin cifrar) y
--sin-anuncio (no usar mDNS).
"""

import argparse
import getpass
import sys
import threading
from pathlib import Path

import uvicorn
from sqlalchemy.orm import Session

from turnos.api.app import crear_app
from turnos.api.rutas.servidor import EstadoServidor
from turnos.datos.bd import DatosMasNuevos, inicializar
from turnos.red import certificados, copias
from turnos.red.anuncio import Anuncio
from turnos.red.configuracion import EJEMPLO, ConfigServidor, ErrorConfiguracion, leer_configuracion
from turnos.servicios import usuarios


def _argumentos(argv: list[str]) -> argparse.Namespace:
    analizador = argparse.ArgumentParser(prog="turnos servidor", description="Servidor de turnos médicos en la red local.")
    analizador.add_argument("accion", nargs="?", default="arrancar",
                            choices=["arrancar", "crear-administrador", "certificado", "copia", "configuracion", "medir"])
    analizador.add_argument("--config", type=Path, help="fichero servidor.toml")
    analizador.add_argument("--datos", type=Path, help="fichero de datos (SQLite)")
    analizador.add_argument("--puerto", type=int)
    analizador.add_argument("--sin-https", action="store_true", help="solo HTTP (pruebas)")
    analizador.add_argument("--sin-anuncio", action="store_true", help="no anunciarse con mDNS")
    analizador.add_argument("--nueva-autoridad", action="store_true", help="con «certificado»: también la autoridad")
    analizador.add_argument("--usuario", help="con «crear-administrador»: nombre de usuario")
    analizador.add_argument("--mes", help="con «medir»: AAAA-MM (por defecto, el mes siguiente)")
    return analizador.parse_args(argv)


def _config(args: argparse.Namespace) -> ConfigServidor:
    config = leer_configuracion(args.config)
    if args.datos:
        config.datos = args.datos.expanduser()
        config.copias = config.datos.parent / "copias"
    if args.puerto is not None:
        config.puerto = args.puerto
    if args.sin_https:
        config.https = False
    if args.sin_anuncio:
        config.anunciar = False
    return config


def main(argv: list[str] | None = None) -> None:
    args = _argumentos(sys.argv[1:] if argv is None else argv)
    if args.accion == "configuracion":
        print(EJEMPLO, end="")
        return
    try:
        config = _config(args)
    except ErrorConfiguracion as error:
        sys.exit(str(error))
    if args.accion == "medir":
        from datetime import date

        from turnos.red.medir import medir

        hoy = date.today()
        anio, mes = (int(x) for x in args.mes.split("-")) if args.mes else (
            (hoy.year + 1, 1) if hoy.month == 12 else (hoy.year, hoy.month + 1))
        print(medir(config.datos, anio, mes).informe())
        return
    if args.accion == "certificado":
        ficheros, _ = certificados.preparar(config.certificados, config.nombre, nueva_autoridad=args.nueva_autoridad)
        print(f"Certificado del servidor: {ficheros.servidor}")
        print(f"Autoridad: {ficheros.autoridad}")
        print(f"Huella de la autoridad (SHA-256): {certificados.huella(certificados.leer_certificado(ficheros.autoridad))}")
        if args.nueva_autoridad:
            print("Autoridad nueva: hay que volver a instalarla en todos los dispositivos.")
        return
    try:
        motor = inicializar(config.datos, wal=True)
    except DatosMasNuevos as error:
        sys.exit(str(error))
    try:
        if args.accion == "crear-administrador":
            _crear_administrador(motor, args.usuario)
        elif args.accion == "copia":
            print(f"Copia hecha: {copias.copiar_ahora(config.datos, config.copias)}")
        else:
            _arrancar(motor, config)
    finally:
        motor.dispose()


def _pedir(texto: str) -> str:
    if sys.stdin.isatty():
        return input(texto).strip()
    return sys.stdin.readline().strip()


def _pedir_contrasena() -> str:
    if not sys.stdin.isatty():  # para guiones: la contraseña por la entrada estándar
        return sys.stdin.readline().rstrip("\n")
    while True:
        primera = getpass.getpass("Contraseña: ")
        if getpass.getpass("Repítela: ") == primera:
            return primera
        print("No coinciden; vuelve a escribirla.")


def _crear_administrador(motor, nombre: str | None) -> None:
    nombre = nombre or _pedir("Nombre de usuario: ")
    visible = _pedir("Nombre visible (Enter para usar el de usuario): ") if sys.stdin.isatty() else nombre
    contrasena = _pedir_contrasena()
    with Session(motor) as sesion, sesion.begin():
        try:
            usuario = usuarios.crear_usuario(sesion, nombre, visible or nombre, "ADMINISTRADOR", contrasena)
        except usuarios.ErrorUsuario as error:
            sys.exit(str(error))
        print(f"Administrador «{usuario.nombre}» creado.")


class _Uvicorn(uvicorn.Server):
    """Al pedir que pare (Ctrl+C, systemd), cierra antes las conexiones de eventos, que
    si no tendrían esperando al apagado ordenado."""

    def handle_exit(self, sig, frame) -> None:
        self.config.app.state.difusor.cerrar()
        super().handle_exit(sig, frame)


def _direcciones(config: ConfigServidor) -> list[str]:
    esquema = "https" if config.https else "http"
    if config.direccion not in ("0.0.0.0", "::"):
        return [f"{esquema}://{config.direccion}:{config.puerto}/"]
    return [f"{esquema}://{config.nombre}.local:{config.puerto}/",
            *(f"{esquema}://{ip}:{config.puerto}/" for ip in certificados.direcciones_locales())]


def _arrancar(motor, config: ConfigServidor) -> None:
    ficheros = None
    if config.https:
        ficheros, _ = certificados.preparar(config.certificados, config.nombre)
    estado = EstadoServidor(config, ficheros, _direcciones(config))
    app = crear_app(motor, servidor=estado)
    opciones = {}
    if ficheros is not None:
        opciones = {"ssl_certfile": str(ficheros.servidor), "ssl_keyfile": str(ficheros.clave_servidor)}
    servidor = _Uvicorn(uvicorn.Config(app, host=config.direccion, port=config.puerto, log_level="warning",
                                       timeout_graceful_shutdown=3, **opciones))

    def renovar() -> None:
        if ficheros is None:
            return
        _, renovado = certificados.preparar(config.certificados, config.nombre)
        if renovado and servidor.config.ssl is not None:
            # Las conexiones nuevas usan ya el certificado nuevo, sin reiniciar.
            servidor.config.ssl.load_cert_chain(str(ficheros.servidor), str(ficheros.clave_servidor))
            estado.direcciones = _direcciones(config)
            print("Certificado del servidor renovado.", flush=True)

    tareas = copias.Tareas(config.datos, config.copias, config.conservar_copias, cada_hora=renovar)
    anuncio = Anuncio(config.nombre, config.puerto, config.https, certificados.direcciones_locales())

    with Session(motor) as sesion:
        sin_usuarios = not usuarios.hay_usuarios(sesion)
    print(f"Turnos médicos {'(HTTPS)' if config.https else '(SOLO HTTP: sin cifrar, solo para pruebas)'}", flush=True)
    print(f"  Datos: {config.datos}" + (f"  (configuración: {config.origen})" if config.origen else ""))
    for direccion in estado.direcciones:
        print(f"  {direccion}")
    if sin_usuarios:
        print("  Aún no hay usuarios: crea el administrador con «turnos servidor crear-administrador».")
    if ficheros is not None:
        huella = certificados.huella(certificados.leer_certificado(ficheros.autoridad))
        print(f"  Huella de la autoridad: {huella}")
    tareas.iniciar()
    if config.anunciar:
        # El registro en mDNS tarda unos segundos (comprueba que el nombre está libre): aparte.
        def anunciar() -> None:
            if aviso := anuncio.iniciar():
                print(f"  {aviso}", flush=True)

        threading.Thread(target=anunciar, name="anuncio-mdns", daemon=True).start()
    print("  Ctrl+C para parar.", flush=True)
    try:
        servidor.run()
    finally:
        anuncio.detener()
        tareas.detener()
