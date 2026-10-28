"""Ajustes generales de la aplicación, guardados en la tabla `ajuste`.

Un ajuste que no está en la tabla toma su valor por defecto.
"""

import json
from dataclasses import asdict, dataclass, fields

from sqlalchemy.orm import Session

from turnos.datos.tablas import Ajuste
from turnos.recursos import MUNICIPIO_POR_DEFECTO


@dataclass
class Ajustes:
    # Cada médico tiene algún turno cada día laborable, salvo ausencia o si ese
    # día no tiene ningún turno posible.
    todos_trabajan: bool = True
    # Cómo se decide cuánto trabaja cada médico: «RANGOS» (turnos al mes mínimo y
    # máximo de su ficha) o «PRESENCIA» (todos los días salvo ausencia, sin rangos:
    # implica `todos_trabajan` y el resto se reparte en proporción a su presencia).
    modo_carga: str = "RANGOS"
    # Urgencias y domicilios en proporción a la presencia de cada médico en el mes
    # (las ausencias reducen su parte); si no, por igual.
    roles_segun_presencia: bool = True
    # Qué papel se reparte por igual antes: si hay que forzar alguna desigualdad, va al
    # otro. «URGENCIAS» (por defecto), «DOMICILIOS» o «IGUAL» (los dos a la vez).
    prioridad_roles: str = "URGENCIAS"
    # Vista: en cada turno del calendario, médicos asignados frente a necesarios (p. ej. 6/0–7).
    mostrar_cobertura: bool = False
    # Municipio del centro (código INE): para buscar sus festivos oficiales.
    municipio: str = MUNICIPIO_POR_DEFECTO  # Madrid


def leer_ajustes(sesion: Session) -> Ajustes:
    ajustes = Ajustes()
    for campo in fields(Ajustes):
        fila = sesion.get(Ajuste, campo.name)
        if fila is not None:
            setattr(ajustes, campo.name, json.loads(fila.valor))
    return ajustes


def guardar_ajustes(sesion: Session, ajustes: Ajustes) -> None:
    for clave, valor in asdict(ajustes).items():
        fila = sesion.get(Ajuste, clave) or Ajuste(clave=clave)
        fila.valor = json.dumps(valor)
        sesion.add(fila)
    sesion.flush()
