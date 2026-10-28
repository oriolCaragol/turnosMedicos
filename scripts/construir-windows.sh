#!/bin/sh
# Construye la versión de Windows desde Linux, con Wine en un contenedor (podman):
#
#   scripts/construir-windows.sh      → build/turnos-medicos-<versión>-windows.zip
#
# El zip lleva la carpeta TurnosMedicos con TurnosMedicos.exe (docs/windows.md). Al
# terminar, el ejecutable se prueba bajo Wine (TurnosMedicos.exe --prueba): arranca
# el servidor interno y genera un mes con el motor.
# Necesita podman, el .venv del proyecto y Node. La primera vez prepara la imagen
# (Debian + Wine + Python de python.org, ~1,5 GB) y descarga las dependencias.
set -eu
cd "$(dirname "$0")/.."
imagen=turnos-windows-construir
version=$(.venv/bin/python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
salida=build/windows
rm -rf "$salida"
mkdir -p "$salida"

echo "== Imagen de construcción (Wine + Python de Windows)"
podman build -q --platform linux/amd64 -t "$imagen" -f empaquetado/windows/Containerfile empaquetado/windows >/dev/null

echo "== Rueda de la aplicación (con la interfaz web)"
scripts/construir-rueda.sh "$salida/rueda" >/dev/null
rueda=$(basename "$(ls "$salida"/rueda/turnos-*.whl)")

echo "== TurnosMedicos.exe (PyInstaller bajo Wine)"
# La caché de pip, en un volumen: las dependencias (OR-Tools, numpy…) se descargan una vez.
podman run --rm -v "$PWD:/proyecto:Z" -v turnos-windows-pip:/wine/drive_c/users/root/AppData/Local/pip:Z \
  -w /proyecto --platform linux/amd64 "$imagen" sh -c "
    set -e
    wine C:\\\\Python\\\\python.exe -m pip install -q --no-warn-script-location 'Z:\\\\proyecto\\\\$salida\\\\rueda\\\\$rueda[cliente]'
    cd empaquetado/windows
    wine C:\\\\Python\\\\python.exe -m PyInstaller --noconfirm --log-level WARN \
      --distpath 'Z:\\\\proyecto\\\\$salida\\\\dist' --workpath 'Z:\\\\proyecto\\\\$salida\\\\obra' turnos-medicos.spec
    echo '== Autoprueba bajo Wine'
    wine 'Z:\\\\proyecto\\\\$salida\\\\dist\\\\TurnosMedicos\\\\TurnosMedicos.exe' --prueba 'Z:\\\\proyecto\\\\$salida\\\\autoprueba.txt'
    wineserver -w
  "
cat "$salida/autoprueba.txt"
tr -d '\r' < "$salida/autoprueba.txt" | grep -q '^BIEN$'
# La biblioteca de C++ de Visual Studio que usa OR-Tools debe ir dentro (ver el spec).
ls "$salida"/dist/TurnosMedicos/_internal/msvcp140.dll >/dev/null

echo "== Comprimiendo"
.venv/bin/python - "$salida/dist" "build/turnos-medicos-$version-windows.zip" <<'PY'
import shutil, sys
shutil.make_archive(sys.argv[2].removesuffix(".zip"), "zip", sys.argv[1], "TurnosMedicos")
PY
ls -la "build/turnos-medicos-$version-windows.zip"
