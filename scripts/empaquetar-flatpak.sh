#!/bin/sh
# Empaqueta Turnos médicos como Flatpak (docs/diseno-escritorio.md, 11.3).
#
#   scripts/empaquetar-flatpak.sh            → build/turnos-medicos-<versión>.flatpak
#   scripts/empaquetar-flatpak.sh --instalar → además lo instala para el usuario actual
#
# Para todos los usuarios del equipo:
#   sudo flatpak install --system build/turnos-medicos-<versión>.flatpak
#
# Requisitos: flatpak-builder (sudo dnf install flatpak-builder) y el SDK de GNOME 51,
# que este guion ofrece instalar la primera vez (~900 MB, solo para empaquetar).
# Usa el .venv del proyecto (para la rueda) y Node (para la interfaz).
set -eu
cd "$(dirname "$0")/.."

ID=io.oriol.TurnosMedicos
RAMA=51
DESTINO=build/flatpak

if ! command -v flatpak-builder >/dev/null; then
  echo "Falta flatpak-builder. Instálalo con: sudo dnf install flatpak-builder" >&2
  exit 1
fi
if ! flatpak info org.gnome.Sdk//$RAMA >/dev/null 2>&1; then
  echo "Falta el SDK de GNOME $RAMA (se necesita solo para empaquetar)."
  # Flathub para el usuario: en Fedora el del sistema viene filtrado y pide permisos.
  flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
  flatpak install --user --noninteractive flathub org.gnome.Sdk//$RAMA
fi

version=$(.venv/bin/python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
echo "== Turnos médicos $version"

echo "== Rueda de la aplicación (con la interfaz web dentro)"
rm -rf "$DESTINO/fuentes"
scripts/construir-rueda.sh "$DESTINO/fuentes"

echo "== Flatpak"
flatpak-builder --force-clean --disable-rofiles-fuse --repo="$DESTINO/repo" --state-dir="$DESTINO/estado" \
  "$DESTINO/compilacion" empaquetado/flatpak/$ID.yml
paquete="build/turnos-medicos-$version.flatpak"
flatpak build-bundle "$DESTINO/repo" "$paquete" $ID
echo "== Listo: $paquete ($(du -h "$paquete" | cut -f1))"

if [ "${1:-}" = "--instalar" ]; then
  flatpak install --user --reinstall --noninteractive "$paquete"
  echo "Instalado para este usuario. Ábrelo desde el menú o con: flatpak run $ID"
else
  echo "Para instalarlo para todos los usuarios: sudo flatpak install --system $paquete"
fi
