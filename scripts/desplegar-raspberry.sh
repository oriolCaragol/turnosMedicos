#!/bin/sh
# Instala o actualiza el servidor en la Raspberry Pi desde este PC
# (docs/instalacion-raspberry.md, 4 y 7).
#
#   scripts/desplegar-raspberry.sh usuario@192.168.1.50
#
# Construye la rueda (con la interfaz web), la copia por SSH junto con
# empaquetado/raspberry/ y ejecuta allí instalar.sh con sudo (pedirá la contraseña
# del usuario de la Pi). Los datos de la Pi no se tocan.
set -eu
cd "$(dirname "$0")/.."
[ $# -eq 1 ] || { echo "Uso: $0 usuario@equipo   (p. ej. pi@raspberrypi.local)" >&2; exit 2; }
destino=$1
remoto=/tmp/turnos-instalacion

scripts/construir-rueda.sh build/rueda >/dev/null
rueda=$(ls build/rueda/turnos-*.whl)
echo "== Copiando $(basename "$rueda") a $destino"
ssh "$destino" "rm -rf $remoto && mkdir -p $remoto"
scp -q "$rueda" empaquetado/raspberry/instalar.sh empaquetado/raspberry/turnos.service \
  empaquetado/raspberry/servidor.toml "$destino:$remoto/"
echo "== Instalando en $destino"
ssh -t "$destino" "sudo sh $remoto/instalar.sh $remoto/$(basename "$rueda"); rm -rf $remoto"
