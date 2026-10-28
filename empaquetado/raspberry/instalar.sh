#!/bin/sh
# Instala (o actualiza) el servidor de Turnos médicos en una Raspberry Pi con
# Raspberry Pi OS de 64 bits (o cualquier Debian/Ubuntu de 64 bits).
# Se ejecuta en la Pi, como root, con la rueda construida en el PC:
#
#   sudo sh instalar.sh turnos-2.13.0-py3-none-any.whl
#
# Lo normal es no llamarlo a mano: scripts/desplegar-raspberry.sh lo copia y lo lanza.
# Opción --sin-systemd: no instala el servicio (para probar en un contenedor).
#
# Qué hace (docs/instalacion-raspberry.md, 4):
#   - usuario de sistema «turnos» (sin acceso a la consola);
#   - entorno de Python en /opt/turnos con la aplicación y sus extras de servidor;
#   - /etc/turnos/servidor.toml (si no existe; si existe, no se toca);
#   - servicio systemd «turnos», arrancado y activado al encender.
# Los datos (/var/lib/turnos) no se tocan: al arrancar, la aplicación los migra si
# hace falta, con una copia previa.
set -eu

uso() {
  echo "Uso: sudo sh $0 [--sin-systemd] turnos-<versión>-py3-none-any.whl" >&2
  exit 2
}

con_systemd=1
rueda=""
for arg in "$@"; do
  case "$arg" in
    --sin-systemd) con_systemd=0 ;;
    -*) uso ;;
    *) rueda=$arg ;;
  esac
done
[ -n "$rueda" ] && [ -f "$rueda" ] || uso
[ "$(id -u)" -eq 0 ] || { echo "Hay que ejecutarlo como root (sudo)." >&2; exit 1; }
carpeta=$(cd "$(dirname "$0")" && pwd)

# --- Comprobaciones -------------------------------------------------------------------
arquitectura=$(uname -m)
case "$arquitectura" in
  aarch64 | x86_64) ;;
  armv7l | armv6l)
    echo "Este sistema es de 32 bits ($arquitectura): el motor (OR-Tools) no existe para él." >&2
    echo "Instala Raspberry Pi OS Lite de 64 bits (docs/instalacion-raspberry.md, 2)." >&2
    exit 1 ;;
  *) echo "Arquitectura no probada: $arquitectura. Se intenta igualmente." >&2 ;;
esac
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
  echo "Hace falta Python 3.11 o más reciente (hay: $(python3 --version 2>&1))." >&2
  exit 1
fi
if ! python3 -c 'import venv, ensurepip' 2>/dev/null; then
  echo "== Instalando python3-venv"
  apt-get update -qq
  apt-get install -y -qq python3-venv >/dev/null
fi

# --- Usuario --------------------------------------------------------------------------
if ! id turnos >/dev/null 2>&1; then
  echo "== Creando el usuario de sistema «turnos»"
  useradd --system --home-dir /var/lib/turnos --no-create-home --shell /usr/sbin/nologin turnos
fi
install -d -o turnos -g turnos -m 0750 /var/lib/turnos

# --- Aplicación -----------------------------------------------------------------------
actualizacion=0
[ -x /opt/turnos/bin/turnos ] && actualizacion=1
if [ ! -x /opt/turnos/bin/python ]; then
  echo "== Creando el entorno de Python en /opt/turnos"
  python3 -m venv /opt/turnos
fi
echo "== Instalando $(basename "$rueda") y sus dependencias (la primera vez tarda unos minutos)"
/opt/turnos/bin/pip install --quiet --upgrade pip
/opt/turnos/bin/pip install --quiet --upgrade "$rueda[servidor]"

# --- Configuración --------------------------------------------------------------------
if [ ! -f /etc/turnos/servidor.toml ]; then
  install -d -m 0755 /etc/turnos
  install -m 0644 "$carpeta/servidor.toml" /etc/turnos/servidor.toml
  echo "== Configuración en /etc/turnos/servidor.toml"
fi

# --- Servicio -------------------------------------------------------------------------
if [ "$con_systemd" -eq 1 ]; then
  install -m 0644 "$carpeta/turnos.service" /etc/systemd/system/turnos.service
  systemctl daemon-reload
  systemctl enable --quiet turnos
  systemctl restart turnos
  echo "== Servicio «turnos» arrancado (se arranca solo al encender)"
fi

version=$(/opt/turnos/bin/python -c 'import turnos; print(turnos.__version__)')
if [ "$actualizacion" -eq 1 ]; then
  echo "Turnos médicos actualizado a la versión $version."
else
  cat <<FIN
Turnos médicos $version instalado.

Falta crear el administrador (una sola vez):
  sudo -u turnos /opt/turnos/bin/turnos servidor crear-administrador --config /etc/turnos/servidor.toml

Después, desde el navegador de cualquier equipo de casa: https://turnos.local:8443/
Registro del servicio: journalctl -u turnos -f
FIN
fi
