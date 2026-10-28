#!/bin/sh
# Construye la rueda de Python de la aplicación con la interfaz web dentro
# (turnos/web), lista para instalar en un servidor (Raspberry Pi) o en el Flatpak.
#
#   scripts/construir-rueda.sh [carpeta]     → carpeta/turnos-<versión>-py3-none-any.whl (por defecto build/rueda)
#
# Necesita el .venv del proyecto y Node (para compilar la interfaz).
set -eu
cd "$(dirname "$0")/.."
DESTINO=${1:-build/rueda}

echo "== Interfaz"
(cd interfaz && npm run build --silent)
rm -rf src/turnos/web
cp -r interfaz/dist src/turnos/web     # dentro del paquete (ignorado por git)

echo "== Rueda"
mkdir -p "$DESTINO"
rm -f "$DESTINO"/turnos-*.whl
.venv/bin/python -m pip wheel --quiet --no-deps --no-build-isolation -w "$DESTINO" .
rm -rf build/lib build/bdist.* src/*.egg-info src/turnos/web
ls "$DESTINO"/turnos-*.whl
