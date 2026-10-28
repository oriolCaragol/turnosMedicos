"""Genera un mes de ejemplo e imprime el calendario.

Uso: python -m turnos.motor.ejemplo [AÑO MES]
"""

import sys
import time
from datetime import date

from turnos.dominio.calendario import dias_laborables
from turnos.dominio.carga import ajustar_rango
from turnos.dominio.modelos import (
    Ausencia,
    Elegibilidad,
    Mitad,
    Preferencia,
    RangoCarga,
    TipoJornada,
    Turno,
    formatear_medios,
)
from turnos.motor.entrada import Cobertura, Problema, ReglasMedico
from turnos.motor.modelo_cpsat import generar

F, D, N = Elegibilidad.FIJO, Elegibilidad.DISPONIBLE, Elegibilidad.NO_DISPONIBLE
M, T = Turno.MANANA, Turno.TARDE


def solo(turno: Turno) -> dict:
    otro = T if turno is M else M
    return {(d, otro): N for d in range(5)}


def equipo_de_ejemplo(dias: list[date]) -> tuple[ReglasMedico, ...]:
    """12 médicos con reglas variadas."""
    def medico(id_, nombre, minimo, maximo, ausencias=(), **kw):
        rango = ajustar_rango(RangoCarga(minimo * 2, maximo * 2), dias, ausencias)
        return ReglasMedico(id=id_, nombre=nombre, carga=rango, ausencias=tuple(ausencias), **kw)

    vacaciones = Ausencia(dias[5], dias[9])
    return (
        medico(1, "Dra. García", 12, 16, elegibilidad={(0, M): F, (1, M): F, (4, M): N, (4, T): N}),
        medico(2, "Dr. López", 12, 16, ausencias=[vacaciones]),
        medico(3, "Dra. Martín", 12, 16, elegibilidad=solo(M)),
        medico(4, "Dr. Sánchez", 12, 16, elegibilidad=solo(M)),
        medico(5, "Dra. Pérez", 12, 16, elegibilidad=solo(T)),
        medico(6, "Dr. Gómez", 12, 16, elegibilidad=solo(T)),
        medico(7, "Dra. Ruiz", 8, 10, elegibilidad={(2, M): N, (2, T): N}),  # jornada parcial
        medico(8, "Dr. Díaz", 12, 16, jornadas={1: TipoJornada.MANANA_MAS_MEDIA}),
        medico(9, "Dra. Moreno", 12, 16, preferencias={(d, T): Preferencia.PREFIERE for d in range(5)}),
        medico(10, "Dr. Muñoz", 12, 16, preferencias={(4, T): Preferencia.EVITA}),
        medico(11, "Dra. Álvarez", 12, 16, ausencias=[Ausencia(dias[0], dias[-1], T)]),
        medico(12, "Dr. Romero", 12, 16),
    )


def problema_de_ejemplo(anio: int, mes: int) -> Problema:
    dias = dias_laborables(anio, mes, festivos=[])
    cobertura = {}
    for dia in dias:
        for h in Mitad:
            # Mañanas 4 médicos, tardes 3; la 1.ª mitad de la tarde admite uno más (medios turnos).
            if h.turno is M:
                cobertura[dia, h] = Cobertura(4, 4)
            else:
                cobertura[dia, h] = Cobertura(3, 4 if h is Mitad.T1 else 3)
    return Problema(dias=tuple(dias), cobertura=cobertura, medicos=equipo_de_ejemplo(dias))


def main() -> None:
    anio, mes = (int(a) for a in sys.argv[1:3]) if len(sys.argv) >= 3 else (2026, 11)
    problema = problema_de_ejemplo(anio, mes)
    inicio = time.perf_counter()
    resultado = generar(problema)
    segundos = time.perf_counter() - inicio

    codigos = {m.id: "".join(p[0] for p in m.nombre.split()[1:])[:2] + str(m.id) for m in problema.medicos}
    print(f"Calendario {mes:02d}/{anio} — válido: {resultado.valido}, "
          f"óptimo: {resultado.optimo}, {segundos:.1f} s\n")
    for dia in problema.dias:
        celdas = []
        for turno in Turno:
            mitades: dict[int, int] = {}
            for a in resultado.asignaciones:
                if a.fecha == dia and a.mitad.turno is turno:
                    mitades[a.medico_id] = mitades.get(a.medico_id, 0) + 1
            textos = [codigos[i] + ("" if n == 2 else "½") for i, n in sorted(mitades.items())]
            celdas.append(" ".join(textos).ljust(32))
        print(f"{dia:%a %d}  M: {celdas[0]} T: {celdas[1]}")
    print("\nCarga por médico (turnos asignados / rango):")
    for m in problema.medicos:
        print(f"  {m.nombre:14} {formatear_medios(resultado.carga[m.id]):>5}  "
              f"[{formatear_medios(m.carga.minimo)}–{formatear_medios(m.carga.maximo)}]")
    if resultado.avisos:
        print("\nAvisos:")
        for aviso in resultado.avisos:
            print(f"  [{aviso.tipo.value}] {aviso.mensaje}")


if __name__ == "__main__":
    main()
