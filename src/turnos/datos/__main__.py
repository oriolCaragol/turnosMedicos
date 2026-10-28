"""Crea o actualiza la base de datos y muestra un resumen.

Uso: python -m turnos.datos
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from turnos.config import ruta_datos
from turnos.datos.bd import inicializar
from turnos.datos.tablas import CargaFestivos, Festivo


def main() -> None:
    ruta = ruta_datos()
    motor = inicializar(ruta)
    print(f"Base de datos: {ruta}")
    with Session(motor) as sesion:
        for carga in sesion.scalars(select(CargaFestivos).order_by(CargaFestivos.anio)):
            festivos = [f for f in sesion.scalars(select(Festivo).order_by(Festivo.fecha))
                        if f.fecha.year == carga.anio]
            estado = "completo" if carga.completo else "INCOMPLETO (faltan festivos por publicar)"
            print(f"  {carga.anio}: {len(festivos)} festivos ({carga.calendario}, {estado})")


if __name__ == "__main__":
    main()
