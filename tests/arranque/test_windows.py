"""Versión de Windows (docs/windows.md): lo que se puede probar en Linux. El ejecutable
se prueba en Windows (GitHub Actions) o con Wine (scripts/construir-windows.sh)."""

from pathlib import Path

from turnos import config
from turnos.arranque.windows.autoprueba import autoprueba


def test_rutas_de_windows(monkeypatch):
    monkeypatch.setattr(config, "_en_windows", lambda: True)
    monkeypatch.delenv("TURNOS_DATOS", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", "/c/Users/ana/AppData/Local")
    monkeypatch.setenv("APPDATA", "/c/Users/ana/AppData/Roaming")
    assert config.ruta_datos() == Path("/c/Users/ana/AppData/Local/TurnosMedicos/turnos.sqlite")
    assert config.carpeta_configuracion() == Path("/c/Users/ana/AppData/Roaming/TurnosMedicos")


def test_rutas_de_linux_sin_cambios(monkeypatch, tmp_path):
    monkeypatch.delenv("TURNOS_DATOS", raising=False)
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "datos"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert config.ruta_datos() == tmp_path / "datos" / "turnosMedicos" / "turnos.sqlite"
    assert config.carpeta_configuracion() == tmp_path / "config" / "turnosMedicos"


def test_autoprueba_del_ejecutable(tmp_path):
    """La que ejecuta TurnosMedicos.exe --prueba: servidor, interfaz, API y motor."""
    salida = tmp_path / "autoprueba.txt"
    codigo = autoprueba(salida)
    texto = salida.read_text(encoding="utf-8")
    if not (Path(__file__).resolve().parents[2] / "interfaz" / "dist" / "index.html").exists():
        return  # sin la interfaz compilada no hay página que comprobar
    assert codigo == 0, texto
    assert texto.rstrip().endswith("BIEN") and "Motor (OR-Tools)" in texto
