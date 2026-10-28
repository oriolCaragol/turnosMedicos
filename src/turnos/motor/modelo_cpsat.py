"""Modelo de asignación con OR-Tools CP-SAT (diseño, 6.3–6.8).

Todas las cantidades van en medios turnos para trabajar con enteros. El motor
solo decide turnos completos (`x[m, d, t]`); lo fijado de antemano entra como
constante. Se resuelve por pasadas lexicográficas: en cada una se optimiza un
objetivo y su valor queda como restricción para las siguientes.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction
from math import ceil, floor

from ortools.sat.python import cp_model

from turnos.dominio.modelos import (
    Asignacion,
    Elegibilidad,
    Mitad,
    OrigenAsignacion,
    Preferencia,
    RangoCarga,
    Rol,
    Turno,
)
from turnos.motor import diagnostico
from turnos.motor.entrada import (
    Preparado,
    Problema,
    ReglasMedico,
    dias_obligatorios,
    preparar,
    presencia,
    tardes_disponibles,
)
from turnos.motor.resultado import (
    Aviso,
    Resultado,
    aviso_rol_sin_cubrir,
    aviso_sin_turno,
    avisos_carga,
    avisos_cobertura,
)


@dataclass(frozen=True)
class Parametros:
    """Parámetros del resolvedor.

    - `tiempo_por_pasada`: límite en tiempo *determinista* de CP-SAT (≈ segundos),
      para que el resultado no dependa de la velocidad del PC.
    - `alternativa_de` / `cambios_minimos`: para "generar alternativa", obliga a
      cambiar al menos ese número de turnos respecto a un calendario dado.
    - `limite_saldo`: cuánto se compensa como máximo por mes la desigualdad
      acumulada de meses anteriores (medios turnos).
    """

    semilla: int = 1
    tiempo_por_pasada: float = 5.0
    alternativa_de: frozenset[Asignacion] | None = None
    cambios_minimos: int = 1
    limite_saldo: int = 2


class SinAlternativa(Exception):
    """No existe un calendario con los cambios mínimos pedidos."""


def generar(problema: Problema, parametros: Parametros = Parametros()) -> Resultado:
    prep = preparar(problema)
    causas = diagnostico.comprobar(problema, prep)
    return _Modelo(problema, prep, parametros).resolver(causas)


@dataclass
class _Rango:
    """Carga de un médico (total o de un turno) con sus holguras."""

    medico_id: int
    nombre: str
    unidad: str
    rango: RangoCarga
    expr: cp_model.LinearExprT
    defecto: cp_model.IntVar
    exceso: cp_model.IntVar


@dataclass
class _Modelo:
    problema: Problema
    prep: Preparado
    parametros: Parametros
    m: cp_model.CpModel = field(default_factory=cp_model.CpModel)
    optimo: bool = True

    def __post_init__(self) -> None:
        orden = sorted(self.prep.candidatos, key=lambda c: (c[0], c[1], c[2].value))
        self.x = {c: self.m.new_bool_var(f"x{c}") for c in orden}
        self.medicos = {med.id: med for med in self.problema.medicos}
        self.x_por_fecha: dict[date, list] = {}
        self.x_por_medico: dict[int, list] = {}
        for clave, var in self.x.items():
            self.x_por_fecha.setdefault(clave[1], []).append((clave, var))
            self.x_por_medico.setdefault(clave[0], []).append((clave, var))
        self._un_turno_al_dia()
        self._cobertura()
        self._carga()
        self._roles()
        self._todos_trabajan()

    # --- Restricciones -----------------------------------------------------

    def _un_turno_al_dia(self) -> None:
        por_dia: dict[tuple[int, date], list] = {}
        for (m_id, dia, _), var in self.x.items():
            por_dia.setdefault((m_id, dia), []).append(var)
        for variables in por_dia.values():
            self.m.add_at_most_one(variables)

    def _cobertura(self) -> None:
        fijados = Counter((a.fecha, a.mitad) for a in self.prep.fijadas)
        self.falta, self.sobra = {}, {}
        num_medicos = len(self.problema.medicos)
        for dia in self.problema.dias:
            for h in Mitad:
                cob = self.problema.cob(dia, h)
                expr = fijados[dia, h] + sum(
                    var for (_, _, t), var in self.x_por_fecha.get(dia, []) if t is h.turno
                )
                falta = self.m.new_int_var(0, cob.minimo, f"falta{dia}{h}")
                sobra = self.m.new_int_var(0, num_medicos, f"sobra{dia}{h}")
                self.m.add(expr + falta >= cob.minimo)
                self.m.add(expr - sobra <= cob.maximo)
                self.falta[dia, h], self.sobra[dia, h] = falta, sobra

    def _carga(self) -> None:
        fijados = Counter((a.medico_id, a.mitad.turno) for a in self.prep.fijadas)
        cota = 4 * len(self.problema.dias)
        self.rangos: list[_Rango] = []
        self.carga_expr: dict[int, cp_model.LinearExprT] = {}
        for med in self.problema.medicos:
            por_turno = {
                t: fijados[med.id, t]
                + 2 * sum(var for (_, _, tt), var in self.x_por_medico.get(med.id, []) if tt is t)
                for t in Turno
            }
            total = sum(por_turno.values())
            self.carga_expr[med.id] = total
            self._rango(med, "turnos", med.carga, total, cota)
            for t, rango in med.carga_por_turno.items():
                unidad = "mañanas" if t is Turno.MANANA else "tardes"
                self._rango(med, unidad, rango, por_turno[t], cota)

    def _rango(self, med: ReglasMedico, unidad: str, rango: RangoCarga, expr, cota: int) -> None:
        defecto = self.m.new_int_var(0, rango.minimo, f"def{med.id}{unidad}")
        exceso = self.m.new_int_var(0, cota, f"exc{med.id}{unidad}")
        self.m.add(expr + defecto >= rango.minimo)
        self.m.add(expr - exceso <= rango.maximo)
        self.rangos.append(_Rango(med.id, med.nombre, unidad, rango, expr, defecto, exceso))

    def _todos_trabajan(self) -> None:
        """Opción «todos trabajan cada día»: cada médico, algún turno cada día que pueda."""
        self.falta_dia: dict[tuple[int, date], cp_model.IntVar] = {}
        fijados = {(a.medico_id, a.fecha) for a in self.prep.fijadas}
        for m_id, dias in dias_obligatorios(self.problema, self.prep).items():
            for dia in dias:
                if (m_id, dia) in fijados:
                    continue  # ya trabaja ese día
                falta = self.m.new_bool_var(f"falta_dia{m_id}{dia}")
                turnos = [var for (m, d, _), var in self.x_por_medico.get(m_id, []) if d == dia]
                self.m.add(sum(turnos) + falta >= 1)
                self.falta_dia[m_id, dia] = falta

    def _roles(self) -> None:
        """Urgencias y domicilios de cada tarde con servicio: un médico para cada papel,
        distintos, y solo entre los que hacen la tarde completa ese día."""
        mitades_fijadas: dict[tuple[int, date], set[Mitad]] = {}
        for a in self.prep.fijadas:
            mitades_fijadas.setdefault((a.medico_id, a.fecha), set()).add(a.mitad)
        self.r: dict[tuple[int, date, Rol], cp_model.IntVar] = {}
        self.falta_rol: dict[tuple[date, Rol], cp_model.IntVar] = {}
        for dia in self.problema.dias_con_roles():
            # Quién hace la tarde completa: fijo (constante 1) o decidido por el motor (x).
            tarde: dict[int, object] = {
                m_id: 1 for (m_id, d), hs in mitades_fijadas.items() if d == dia and set(Turno.TARDE.mitades) <= hs
            }
            for (m_id, d, t), var in self.x_por_fecha.get(dia, []):
                if t is Turno.TARDE:
                    tarde[m_id] = var
            for m_id, trabaja in sorted(tarde.items()):
                papeles = [self.m.new_bool_var(f"rol{m_id}{dia}{rol.value}") for rol in Rol]
                for rol, var in zip(Rol, papeles):
                    self.r[m_id, dia, rol] = var
                self.m.add(sum(papeles) <= trabaja)  # un papel como mucho, y solo si trabaja
            for rol in Rol:
                falta = self.m.new_bool_var(f"falta_rol{dia}{rol.value}")
                self.m.add(sum(self.r[m_id, dia, rol] for m_id in tarde) + falta == 1)
                self.falta_rol[dia, rol] = falta
                elegido = self.problema.roles_fijados.get((dia, rol))
                if elegido is not None and (elegido, dia, rol) in self.r:
                    self.m.add(self.r[elegido, dia, rol] == 1)

    def _desviaciones_roles(self) -> dict[Rol | str, tuple]:
        """Reparto de urgencias y de domicilios lo más ajustado posible a la parte de cada uno.

        La parte sale de `partes`: igual para todos o, con `roles_segun_presencia`,
        proporcional a las tardes del mes en que cada médico no está ausente; y nunca
        más de las tardes que puede hacer (lo que no puede, se reparte entre los demás).
        La parte exacta se convierte en una banda de enteros con `bandas` y se mide
        cuánto se sale cada uno de la suya, para cada papel y para los dos juntos
        (bandas que casi siempre se pueden cumplir del todo: el resolvedor lo
        demuestra enseguida, a diferencia de minimizar la distancia a la parte exacta).

        Devuelve (mayor desviación, suma de desviaciones) de cada papel, de los dos
        juntos («total») y de todo («todo»), para que `_objetivos` decida el orden."""
        dias = self.problema.dias_con_roles()
        tardes = {med.id: tardes_disponibles(med, dias) for med in self.problema.medicos}
        tardes = {m_id: n for m_id, n in tardes.items() if n > 0}
        if not dias or not tardes:
            return {clave: (0, 0) for clave in (*Rol, "total", "todo")}
        if self.problema.roles_segun_presencia:
            pesos = {m_id: presencia(self.medicos[m_id], dias) for m_id in tardes}
        else:
            pesos = {m_id: 1 for m_id in tardes}
        por_medico: dict[tuple[int, Rol], list] = {}
        for (m_id, _, rol), var in self.r.items():
            por_medico.setdefault((m_id, rol), []).append(var)
        por_papel = bandas(partes(len(dias), tardes, pesos))
        juntos = {}
        for m_id, (bajo, alto) in bandas(partes(2 * len(dias), tardes, pesos)).items():
            # Coherente con las de cada papel: dentro de su suma (si no se solapan, manda la suma).
            suma = (2 * por_papel[m_id][0], 2 * por_papel[m_id][1])
            cruce = (max(bajo, suma[0]), min(alto, suma[1]))
            juntos[m_id] = cruce if cruce[0] <= cruce[1] else suma
        cota = 2 * len(dias)
        grupos = (*Rol, "total", "todo")
        mayores = {g: self.m.new_int_var(0, cota, f"dev_roles_mayor_{g}") for g in grupos}
        desviaciones: dict = {g: [] for g in grupos}

        def desviacion(terminos: list, banda: tuple[int, int], grupo, nombre: str) -> None:
            veces = sum(terminos)
            dev = self.m.new_int_var(0, cota, f"dev_rol{nombre}")
            self.m.add(dev >= veces - banda[1])
            self.m.add(dev >= banda[0] - veces)
            for g in (grupo, "todo"):
                self.m.add(mayores[g] >= dev)
                desviaciones[g].append(dev)

        for m_id in tardes:
            if m_id not in por_papel:
                continue  # ausente todo el mes con papel
            for rol in Rol:
                desviacion(por_medico.get((m_id, rol), []), por_papel[m_id], rol, f"{m_id}{rol.value}")
            desviacion([v for rol in Rol for v in por_medico.get((m_id, rol), [])], juntos[m_id], "total", f"{m_id}total")
        return {g: (mayores[g], sum(desviaciones[g])) for g in grupos}

    def _pasadas_roles(self) -> list[tuple[str, cp_model.LinearExprT]]:
        """Reparto de urgencias y domicilios. Con `prioridad_roles`, primero se iguala ese
        papel (su peor desviación y después la suma), luego el otro y por último los dos
        juntos: si hay que repartir alguno de forma desigual, es el segundo. Sin
        prioridad, los dos a la vez."""
        dev = self._desviaciones_roles()
        primero = self.problema.prioridad_roles
        if primero is None:
            return [("reparto de urgencias y domicilios (mayor desviación)", dev["todo"][0]),
                    ("reparto de urgencias y domicilios (suma)", dev["todo"][1])]
        segundo = Rol.DOMICILIOS if primero is Rol.URGENCIAS else Rol.URGENCIAS
        nombre = {Rol.URGENCIAS: "urgencias", Rol.DOMICILIOS: "domicilios"}
        return [
            (f"reparto de {nombre[primero]} (mayor desviación)", dev[primero][0]),
            (f"reparto de {nombre[primero]} (suma)", dev[primero][1]),
            (f"reparto de {nombre[segundo]} (mayor desviación)", dev[segundo][0]),
            (f"reparto de {nombre[segundo]} (suma)", dev[segundo][1]),
            ("reparto de urgencias y domicilios juntos (mayor desviación)", dev["total"][0]),
            ("reparto de urgencias y domicilios juntos (suma)", dev["total"][1]),
        ]

    def _cambios_roles(self):
        return sum(
            1 - self.r[m_id, dia, rol]
            for (dia, rol), m_id in self.problema.roles_anteriores.items()
            if (m_id, dia, rol) in self.r
        )

    def _cambios(self, referencia: frozenset[Asignacion]):
        """Número de turnos generados que difieren de un calendario de referencia."""
        previos = {(a.medico_id, a.fecha, a.mitad.turno) for a in referencia}
        return sum((1 - var) if clave in previos else var for clave, var in self.x.items())

    # --- Objetivos -----------------------------------------------------------

    def _objetivos(self) -> list[tuple[str, cp_model.LinearExprT]]:
        """Pasadas en orden de prioridad; todas se minimizan."""
        mayor, suma = self._desviaciones_equidad()
        pasadas = [
            # Mejor un médico de más que un hueco sin cubrir.
            ("cobertura mínima", sum(self.falta.values())),
            # Con la opción activada, que todos trabajen cada día va por delante del
            # máximo de cobertura y de la carga: si chocan, se avisa.
            ("todos trabajan cada día", sum(self.falta_dia.values())),
            ("cobertura máxima", sum(self.sobra.values())),
            ("urgencias y domicilios", sum(self.falta_rol.values())),
            ("carga", sum(r.defecto + r.exceso for r in self.rangos)),
            # Reparto de urgencias y domicilios: antes que la equidad de carga y
            # las preferencias, porque es una exigencia del servicio.
            *self._pasadas_roles(),
            # Equidad en dos pasos: primero nadie muy lejos de su objetivo, y
            # después lo más cerca posible en conjunto.
            ("equidad (mayor desviación)", mayor),
            ("equidad (suma)", suma),
            ("preferencias", -self._puntuacion_preferencias()),
        ]
        if self.problema.anterior or self.problema.roles_anteriores:
            pasadas.append(("estabilidad", self._cambios(self.problema.anterior) + self._cambios_roles()))
        return pasadas

    def _desviaciones_equidad(self) -> tuple:
        """Mayor desviación y suma de desviaciones respecto al objetivo de cada médico."""
        objetivos = objetivos_equidad(self.problema, self.parametros.limite_saldo)
        cota = 4 * len(self.problema.dias)
        mayor = self.m.new_int_var(0, cota, "dev_mayor")
        desviaciones = []
        for med in self.problema.medicos:
            dev = self.m.new_int_var(0, cota, f"dev{med.id}")
            self.m.add(dev >= self.carga_expr[med.id] - objetivos[med.id])
            self.m.add(dev >= objetivos[med.id] - self.carga_expr[med.id])
            self.m.add(mayor >= dev)
            desviaciones.append(dev)
        return mayor, sum(desviaciones)

    def _puntuacion_preferencias(self):
        """Prefiere: +1. Evita: −1. Turno habitual (cuadrícula): +2, una preferencia fuerte."""
        puntos = {Preferencia.PREFIERE: 1, Preferencia.EVITA: -1}
        total = 0
        for (m_id, dia, t), var in self.x.items():
            medico = self.medicos[m_id]
            p = medico.preferencias.get((dia.weekday(), t))
            peso = (puntos[p] if p is not None else 0) + (2 if medico.eleg(dia, t) is Elegibilidad.HABITUAL else 0)
            if peso:
                total += peso * var
        return total

    # --- Resolución ----------------------------------------------------------

    def _solver(self) -> cp_model.CpSolver:
        solver = cp_model.CpSolver()
        solver.parameters.random_seed = self.parametros.semilla
        # Un solo hilo: el resultado es reproducible y, para este tamaño de
        # problema, más rápido que la búsqueda paralela determinista.
        solver.parameters.num_workers = 1
        solver.parameters.max_deterministic_time = self.parametros.tiempo_por_pasada
        return solver

    def resolver(self, causas: list[Aviso]) -> Resultado:
        solver = self._solver()
        solver.solve(self.m)  # por si todos los objetivos son constantes (mes vacío)
        for nombre, objetivo in self._objetivos():
            if isinstance(objetivo, int):
                continue  # objetivo constante (p. ej. sin preferencias): nada que optimizar
            self.m.minimize(objetivo)
            solver = self._solver()
            estado = solver.solve(self.m)
            if estado == cp_model.INFEASIBLE:
                raise SinAlternativa(
                    f"No hay un calendario distinto con al menos "
                    f"{self.parametros.cambios_minimos} turnos cambiados."
                )
            if estado not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                raise RuntimeError(f"El resolvedor no encontró solución en la pasada '{nombre}'")
            self.optimo &= estado == cp_model.OPTIMAL
            # Fija el valor alcanzado y usa la solución como punto de partida.
            self.m.add(objetivo <= round(solver.objective_value))
            self.m.clear_hints()
            for var in [*self.x.values(), *self.r.values()]:
                self.m.add_hint(var, solver.boolean_value(var))
            if nombre == "carga" and self.parametros.alternativa_de is not None:
                # La alternativa debe ser tan válida como la mejor posible: se
                # exige el cambio una vez fijados cobertura y carga.
                cambios = self._cambios(self.parametros.alternativa_de)
                self.m.add(cambios >= self.parametros.cambios_minimos)
                self.m.clear_hints()
        return self._resultado(solver, causas)

    def _resultado(self, solver: cp_model.CpSolver, causas: list[Aviso]) -> Resultado:
        asignaciones = dict(self.prep.fijadas)
        for (m_id, dia, t), var in self.x.items():
            if solver.boolean_value(var):
                for h in t.mitades:
                    asignaciones[Asignacion(m_id, dia, h)] = OrigenAsignacion.GENERADOR
        incumplimientos = self._incumplimientos(solver)
        return Resultado(
            asignaciones=asignaciones,
            valido=not incumplimientos,
            optimo=self.optimo,
            avisos=tuple(causas + incumplimientos),
            carga={m_id: solver.value(expr) for m_id, expr in self.carga_expr.items()},
            roles={(dia, rol): m_id for (m_id, dia, rol), v in self.r.items() if solver.boolean_value(v)},
        )

    def _incumplimientos(self, solver: cp_model.CpSolver) -> list[Aviso]:
        avisos = []
        for dia in self.problema.dias:
            avisos += avisos_cobertura(
                dia,
                {h: solver.value(self.falta[dia, h]) for h in Mitad},
                {h: solver.value(self.sobra[dia, h]) for h in Mitad},
            )
        for r in self.rangos:
            avisos += avisos_carga(r.medico_id, r.nombre, r.unidad, solver.value(r.expr), r.rango)
        for (dia, rol), falta in sorted(self.falta_rol.items(), key=lambda i: (i[0][0], i[0][1].value)):
            if solver.value(falta):
                avisos.append(aviso_rol_sin_cubrir(dia, rol))
        for (m_id, dia), falta in sorted(self.falta_dia.items()):
            if solver.value(falta):
                avisos.append(aviso_sin_turno(dia, m_id, self.medicos[m_id].nombre))
        return avisos


def objetivos_equidad(problema: Problema, limite_saldo: int) -> dict[int, int]:
    """Carga objetivo de cada médico, en medios turnos (diseño, 6.5).

    La demanda del mes (suma de mínimos de cobertura) se reparte en proporción
    al punto medio del rango de cada médico; se compensa parte del saldo de
    meses anteriores y se recorta al rango.
    """
    demanda = sum(problema.cob(dia, h).minimo for dia in problema.dias for h in Mitad)
    pesos = {med.id: med.carga.minimo + med.carga.maximo for med in problema.medicos}
    total = sum(pesos.values())
    objetivos = {}
    for med in problema.medicos:
        reparto = Fraction(demanda * pesos[med.id], total) if total else Fraction(0)
        compensacion = max(-limite_saldo, min(limite_saldo, med.saldo))
        objetivo = floor(reparto - compensacion + Fraction(1, 2))
        objetivos[med.id] = max(med.carga.minimo, min(med.carga.maximo, objetivo))
    return objetivos


def partes(total: int, capacidad: dict[int, int], pesos: dict[int, int]) -> dict[int, Fraction]:
    """Parte exacta de `total` que corresponde a cada uno, proporcional a su peso
    («llenado por niveles»): quien tiene menos `capacidad` que su parte se queda con
    su capacidad, y lo que no puede hacer se reparte entre los demás según su peso.
    Con pesos iguales, todos lo mismo."""
    resultado: dict[int, Fraction] = {}
    pendientes = {m for m in capacidad if pesos.get(m, 0) > 0}
    restante = Fraction(total)
    while pendientes:
        nivel = restante / sum(pesos[m] for m in pendientes)
        limitados = {m for m in pendientes if capacidad[m] < nivel * pesos[m]}
        if not limitados:
            resultado.update({m: nivel * pesos[m] for m in pendientes})
            break
        for m in limitados:
            resultado[m] = Fraction(capacidad[m])
            restante -= capacidad[m]
        pendientes -= limitados
    return resultado


def bandas(partes_exactas: dict[int, Fraction]) -> dict[int, tuple[int, int]]:
    """Banda de enteros (mínimo, máximo) para cada parte exacta, por restos mayores.

    Cada uno tiene al menos ⌊parte⌋; las unidades que sobran son para quien tiene el
    mayor resto. Si varios empatan en el resto y no hay para todos, su banda queda
    abierta (⌊parte⌋ a ⌈parte⌉) y el motor elige. Así, partes de 2,06 y 1,75 dan 2
    a todos, y no 3 a unos y 1 a otros."""
    sobran = round(sum(partes_exactas.values()) - sum(floor(p) for p in partes_exactas.values()))
    resultado = {m: (floor(p), floor(p)) for m, p in partes_exactas.items()}
    restos = sorted({p - floor(p) for p in partes_exactas.values() if p != floor(p)}, reverse=True)
    for resto in restos:
        grupo = [m for m, p in partes_exactas.items() if p - floor(p) == resto]
        if sobran >= len(grupo):
            resultado.update({m: (ceil(partes_exactas[m]), ceil(partes_exactas[m])) for m in grupo})
            sobran -= len(grupo)
        elif sobran > 0:
            resultado.update({m: (floor(partes_exactas[m]), ceil(partes_exactas[m])) for m in grupo})
            sobran = 0
    return resultado

