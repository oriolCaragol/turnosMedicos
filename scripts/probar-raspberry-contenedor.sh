#!/bin/sh
# Prueba la instalación de la Raspberry Pi sin la Pi: un Debian 13 (trixie) para ARM de
# 64 bits en un contenedor emulado (podman + qemu-user-static), como Raspberry Pi OS
# de 64 bits. Comprueba que hay ruedas para aarch64 de todas las dependencias, que
# instalar.sh funciona (sin systemd, que no hay en el contenedor), que el servidor
# arranca como el usuario «turnos» con HTTPS y que se entra.
#
#   scripts/probar-raspberry-contenedor.sh
#
# Bajo emulación todo es varias veces más lento: los tiempos no valen como medida
# (para eso, `turnos servidor medir` en la Pi real).
set -eu
cd "$(dirname "$0")/.."
nombre=turnos-prueba-pi
scripts/construir-rueda.sh build/rueda >/dev/null
rueda=$(basename "$(ls build/rueda/turnos-*.whl)")
podman rm -f "$nombre" >/dev/null 2>&1 || true
trap 'podman rm -f "$nombre" >/dev/null 2>&1 || true' EXIT

echo "== Contenedor arm64 (Debian trixie)"
podman run -d --name "$nombre" --platform linux/arm64 \
  -v "$PWD/build/rueda:/rueda:ro,Z" -v "$PWD/empaquetado/raspberry:/instalacion:ro,Z" \
  docker.io/library/debian:trixie sleep infinity >/dev/null
podman exec "$nombre" sh -c 'apt-get update -qq && apt-get install -y -qq python3 python3-venv curl ca-certificates >/dev/null'
podman exec "$nombre" uname -m

echo "== instalar.sh"
podman exec "$nombre" sh /instalacion/instalar.sh --sin-systemd "/rueda/$rueda"
echo "== Segunda vez (actualizar)"
podman exec "$nombre" sh /instalacion/instalar.sh --sin-systemd "/rueda/$rueda"

echo "== Administrador y arranque como «turnos»"
podman exec "$nombre" sh -c 'echo contrasena-admin | runuser -u turnos -- /opt/turnos/bin/turnos servidor crear-administrador --config /etc/turnos/servidor.toml --usuario admin'
podman exec -d "$nombre" runuser -u turnos -- /opt/turnos/bin/turnos servidor --config /etc/turnos/servidor.toml --sin-anuncio
podman exec "$nombre" sh -c '
  for i in $(seq 1 120); do
    [ -f /var/lib/turnos/certificados/autoridad.crt ] && curl -s -o /dev/null --cacert /var/lib/turnos/certificados/autoridad.crt https://localhost:8443/api/servidor/publico && break
    sleep 1
  done
  curl -s --cacert /var/lib/turnos/certificados/autoridad.crt -H "X-Cliente: prueba" -H "Content-Type: application/json" \
    -d "{\"usuario\":\"admin\",\"contrasena\":\"contrasena-admin\"}" https://localhost:8443/api/sesion; echo
  ls -l /var/lib/turnos /var/lib/turnos/copias
  stat -c "%a %U %n" /var/lib/turnos/certificados/autoridad.key'
echo "== Medición (emulada: solo comprueba que el motor funciona en aarch64)"
podman exec "$nombre" runuser -u turnos -- /opt/turnos/bin/turnos servidor medir --config /etc/turnos/servidor.toml --mes 2026-11
echo "== Bien: la instalación funciona en Debian trixie arm64."
