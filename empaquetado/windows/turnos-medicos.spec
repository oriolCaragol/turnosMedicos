# PyInstaller: TurnosMedicos.exe para Windows (docs/windows.md).
# Lo usan scripts/construir-windows.sh (Wine, en Linux) y .github/workflows/windows.yml.
# Necesita la interfaz web compilada dentro del paquete (src/turnos/web, ver
# scripts/construir-rueda.sh) y el paquete instalado con el extra «cliente».
import glob
import os
import shutil
import tempfile

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datos, binarios, ocultos = [], [], []
# OR-Tools, numpy, pandas y protobuf traen bibliotecas nativas y módulos que se cargan
# de forma dinámica: se incluyen enteros.
for paquete in ("ortools", "zeroconf"):
    d, b, o = collect_all(paquete)
    datos += d
    binarios += b
    ocultos += o
# OR-Tools usa la biblioteca de C++ de Visual Studio del sistema (MSVCP140.dll), que no
# todos los Windows tienen. numpy trae una copia de esa misma DLL de Microsoft, con otro
# nombre: se incluye también como msvcp140.dll para que el ejecutable no dependa del
# redistribuible (y para que, construido con Wine, no se quede sin ella).
import numpy  # noqa: E402

copias = glob.glob(os.path.join(os.path.dirname(numpy.__file__), os.pardir, "numpy.libs", "msvcp140-*.dll"))
if copias:
    carpeta = tempfile.mkdtemp()
    shutil.copy(copias[0], os.path.join(carpeta, "msvcp140.dll"))
    binarios.append((os.path.join(carpeta, "msvcp140.dll"), "."))
# La aplicación: recursos (festivos, municipios), la interfaz web y las migraciones de
# Alembic, que se cargan como ficheros .py desde su carpeta.
datos += collect_data_files("turnos", include_py_files=True, excludes=["**/__pycache__/**"])
# Sin los módulos de GNOME (GTK, WebKit y libsecret no existen en Windows).
SOLO_GNOME = ("turnos.arranque.gnome", "turnos.arranque.escritorio", "turnos.arranque.dialogos", "turnos.arranque.llavero")
ocultos += collect_submodules("uvicorn") + ["sqlalchemy.dialects.sqlite"]
ocultos += collect_submodules("turnos", filter=lambda nombre: not nombre.startswith(SOLO_GNOME))

a = Analysis(
    ["principal.py"],
    pathex=[],
    binaries=binarios,
    datas=datos,
    hiddenimports=ocultos,
    excludes=["gi", *SOLO_GNOME, "pytest", "matplotlib", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TurnosMedicos",
    icon="turnos.ico",
    console=False,  # aplicación con ventana: sin consola negra
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="TurnosMedicos")
