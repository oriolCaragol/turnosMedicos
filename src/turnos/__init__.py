"""turnosMedicos: asignación automática de turnos para un equipo de médicos."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("turnos")
except PackageNotFoundError:  # ejecutado desde el código fuente sin instalar
    __version__ = "desarrollo"
