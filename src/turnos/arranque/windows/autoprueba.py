"""Autoprueba del ejecutable (sin ventana): arranca el servidor interno con datos
temporales, comprueba la interfaz y la API y genera un mes con el motor. La usa la
compilación (GitHub Actions y scripts/construir-windows.sh) para saber que el
ejecutable tiene todo lo necesario (OR-Tools, migraciones, interfaz…)."""

import json
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path


def autoprueba(salida: Path | None) -> int:
    lineas: list[str] = []
    try:
        from turnos import __version__
        from turnos.arranque.servidor import preparar

        with tempfile.TemporaryDirectory() as carpeta:
            servidor = preparar(puerto=0, ruta=Path(carpeta) / "turnos.sqlite")
            servidor.iniciar_en_hilo()
            base = f"http://127.0.0.1:{servidor.puerto}"
            cabeceras = {"X-Turnos-Token": servidor.token, "Content-Type": "application/json", "X-Cliente": "prueba"}

            def api(metodo: str, ruta: str, cuerpo=None):
                datos = None if cuerpo is None else json.dumps(cuerpo).encode()
                peticion = urllib.request.Request(base + "/api" + ruta, data=datos, method=metodo, headers=cabeceras)
                with urllib.request.urlopen(peticion, timeout=120) as r:
                    contenido = r.read()
                return json.loads(contenido) if contenido else None

            with urllib.request.urlopen(base + "/", timeout=30) as r:
                assert b"<div id=\"raiz\">" in r.read(), "falta la interfaz web"
            lineas.append(f"Turnos médicos {__version__}: interfaz y servidor, bien")
            assert api("GET", "/festivos/anios"), "faltan los festivos precargados"
            for nombre, codigo in [("Ana", "ANA"), ("Bea", "BEA"), ("Carlos", "CAR")]:
                m = api("POST", "/medicos", {"nombre": nombre, "codigo": codigo})
                api("PUT", f"/medicos/{m['id']}/reglas", {
                    "vigente_desde": "2026-11-01", "elegibilidad": [], "carga": {"minimo": 0, "maximo": 40}})
            api("PUT", "/cobertura/semanal", [
                {"dia_semana": d, "mitad": h, "minimo": 1, "maximo": 1} for d in range(5) for h in ("M1", "M2", "T1", "T2")])
            api("PUT", "/ajustes", {"todos_trabajan": False})
            inicio = time.perf_counter()
            cal = api("POST", "/periodos/2026/11/generar", {})
            assert cal["asignaciones"], "el motor no ha asignado turnos"
            lineas.append(f"Motor (OR-Tools): {len(cal['asignaciones'])} medios turnos en {time.perf_counter() - inicio:.1f} s")
            servidor.detener()
        lineas.append("BIEN")
        codigo = 0
    except Exception:  # noqa: BLE001 — se informa en el fichero
        lineas.append(traceback.format_exc())
        lineas.append("MAL")
        codigo = 1
    texto = "\n".join(lineas) + "\n"
    if salida is not None:
        salida.write_text(texto, encoding="utf-8")
    else:
        print(texto)
    return codigo
