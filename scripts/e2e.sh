#!/bin/sh
# Prueba de flujo completo (Playwright): compila la interfaz, arranca la
# aplicación con una base de datos temporal vacía y ejecuta interfaz/e2e.
# Arranca dos: el modo personal (casi todas las pruebas) y el modo servidor con
# HTTPS (e2e/servidor.spec.ts), con un administrador «admin» ya creado.
#
# Uso: scripts/e2e.sh        (desde la raíz del proyecto)
# Variables: E2E_PUERTO (8790; el modo servidor usa el siguiente), CHROMIUM (ruta del
# navegador; por defecto el del sistema).
set -eu

raiz=$(cd "$(dirname "$0")/.." && pwd)
puerto=${E2E_PUERTO:-8790}
puerto_red=$((puerto + 1))
datos=$(mktemp -d)
servidor=""
servidor_red=""
trap '[ -n "$servidor" ] && kill "$servidor" 2>/dev/null; [ -n "$servidor_red" ] && kill "$servidor_red" 2>/dev/null; rm -rf "$datos"' EXIT

(cd "$raiz/interfaz" && npm run build >/dev/null)

# Sin token: Playwright también llama a la API directamente (el token se prueba con pytest).
# Fuentes de festivos oficiales: ficheros de prueba, sin depender de internet.
TURNOS_FUENTE_FESTIVOS_IO="file://$raiz/interfaz/e2e/datos/festivos-io/{anio}-{ine}.json" \
TURNOS_FUENTE_MADRID="file://$raiz/interfaz/e2e/datos/madrid-locales.json" \
TURNOS_DATOS="$datos/turnos.sqlite" TURNOS_PUERTO=$puerto TURNOS_SIN_NAVEGADOR=1 TURNOS_SIN_TOKEN=1 \
  "$raiz/.venv/bin/turnos" >"$datos/servidor.log" 2>&1 &
servidor=$!

# Modo servidor (sin mDNS: no anunciar nada en la red durante las pruebas).
mkdir -p "$datos/red"
echo "contrasena-admin" | "$raiz/.venv/bin/turnos" servidor crear-administrador --datos "$datos/red/turnos.sqlite" --usuario admin >/dev/null
"$raiz/.venv/bin/turnos" servidor --datos "$datos/red/turnos.sqlite" --puerto "$puerto_red" --sin-anuncio \
  >"$datos/servidor-red.log" 2>&1 &
servidor_red=$!
intentos=0
until curl -sk -o /dev/null "https://127.0.0.1:$puerto_red/api/servidor/publico"; do
  intentos=$((intentos + 1))
  if [ "$intentos" -gt 60 ]; then
    echo "El servidor en red no arrancó:" >&2
    cat "$datos/servidor-red.log" >&2
    exit 1
  fi
  sleep 0.5
done

intentos=0
until curl -s -o /dev/null "http://127.0.0.1:$puerto/api/estado"; do
  intentos=$((intentos + 1))
  if [ "$intentos" -gt 60 ]; then
    echo "El servidor no arrancó:" >&2
    cat "$datos/servidor.log" >&2
    exit 1
  fi
  sleep 0.5
done

cd "$raiz/interfaz" && E2E_URL="http://127.0.0.1:$puerto" E2E_URL_SERVIDOR="https://localhost:$puerto_red" npx playwright test "$@"
