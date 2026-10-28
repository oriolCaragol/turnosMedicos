#!/bin/sh
# Regenera las capturas de la interfaz web de la guía de uso (docs/imagenes/*.png, las
# que no empiezan por «nativa-») con un equipo ficticio, sobre una base de datos temporal.
#
#   scripts/capturas-guia.sh
#
# Necesita el .venv, Node y el Chromium del sistema (como scripts/e2e.sh).
set -eu
raiz=$(cd "$(dirname "$0")/.." && pwd)
puerto=8795
datos=$(mktemp -d)
servidor=""
trap '[ -n "$servidor" ] && kill "$servidor" 2>/dev/null; rm -rf "$datos"' EXIT

(cd "$raiz/interfaz" && npm run build >/dev/null)
TURNOS_DATOS="$datos/turnos.sqlite" TURNOS_PUERTO=$puerto TURNOS_SIN_NAVEGADOR=1 TURNOS_SIN_TOKEN=1 \
  "$raiz/.venv/bin/turnos" >"$datos/servidor.log" 2>&1 &
servidor=$!
until curl -s -o /dev/null "http://127.0.0.1:$puerto/api/estado"; do sleep 0.3; done
cd "$raiz/interfaz" && node herramientas/capturas-guia.mjs "http://127.0.0.1:$puerto" "$raiz/docs/imagenes"
