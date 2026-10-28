#!/usr/bin/env python3
"""Genera empaquetado/flatpak/python3-dependencias.json: el módulo de Flatpak con las
dependencias de Python de la aplicación, como ruedas ya compiladas para el Python del
runtime de GNOME (sin compilar nada ni descargar durante el empaquetado).

Las versiones son las del .venv del proyecto (las que pasan las pruebas). Se ejecuta
cuando cambian las dependencias:

    .venv/bin/python scripts/generar-dependencias-flatpak.py

Necesita red (consulta PyPI). Sustituye a flatpak-pip-generator, que no permite
elegir la plataforma de las ruedas.
"""

import json
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "empaquetado" / "flatpak" / "python3-dependencias.json"
PYTHON_RUNTIME = "3.14"  # el de org.gnome.Platform 51
PLATAFORMAS = [f"manylinux_2_{n}_x86_64" for n in range(17, 40)] + ["manylinux2014_x86_64", "linux_x86_64"]


def versiones_del_venv() -> list[str]:
    paquetes = sysconfig.get_path("purelib")
    salida = subprocess.run(
        [sys.executable, "-m", "pip", "freeze", "--exclude-editable", "--path", paquetes],
        check=True, capture_output=True, text=True,
    ).stdout
    return [linea for linea in salida.splitlines() if "==" in linea]


def resolver(restricciones: list[str]) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        fichero = Path(tmp) / "restricciones.txt"
        fichero.write_text("\n".join(restricciones) + "\n")
        informe = Path(tmp) / "informe.json"
        orden = [
            sys.executable, "-m", "pip", "install", "--quiet", "--dry-run", "--ignore-installed",
            "--report", str(informe), "--target", str(Path(tmp) / "nada"),
            "--only-binary=:all:", "--implementation", "cp", "--python-version", PYTHON_RUNTIME,
            "--abi", "cp" + PYTHON_RUNTIME.replace(".", ""), "--abi", "abi3", "--abi", "none",
            "-c", str(fichero),
        ]
        for plataforma in PLATAFORMAS:
            orden += ["--platform", plataforma]
        # Con el extra «cliente»: las aplicaciones buscan servidores en la red (mDNS).
        subprocess.run([*orden, f"{RAIZ}[cliente]"], check=True)
        return json.loads(informe.read_text())["install"]


def main() -> None:
    instalar = [p for p in resolver(versiones_del_venv()) if p["metadata"]["name"] != "turnos"]
    fuentes, nombres = [], []
    for paquete in sorted(instalar, key=lambda p: p["metadata"]["name"].lower()):
        info = paquete["download_info"]
        fuentes.append({"type": "file", "url": info["url"], "sha256": info["archive_info"]["hashes"]["sha256"]})
        nombres.append(f'{paquete["metadata"]["name"]}=={paquete["metadata"]["version"]}')
    modulo = {
        "name": "python3-dependencias",
        "buildsystem": "simple",
        "build-commands": [
            "pip3 install --ignore-installed --no-index --no-deps --find-links=\"file://${PWD}\" --prefix=${FLATPAK_DEST} "
            "--no-build-isolation " + " ".join(f'"{n}"' for n in nombres),
        ],
        "sources": fuentes,
        "cleanup": ["/bin/f2py", "/bin/numpy-config", "/bin/fastapi", "/bin/alembic", "/bin/uvicorn"],
    }
    SALIDA.write_text(json.dumps(modulo, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(nombres)} paquetes en {SALIDA.relative_to(RAIZ)}:")
    print("  " + ", ".join(nombres))


if __name__ == "__main__":
    main()
