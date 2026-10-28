/** Lógica pura del calendario del mes (sin React), probada aparte. */

import type { Calendario, Cambio, EstadoManual, MedicoCalendario, Mitad, Rol, TipoJornada, Turno } from "../api/tipos";
import { MITADES, MITADES_DE } from "../util/textos";

export type Origen =
  | { tipo: "celda"; medico: number; fecha: string; turno: Turno }
  | { tipo: "resumen"; medico: number };

export type Destino = { fecha: string; turno: Turno } | null;

export function mitadesDe(cal: Calendario, medico: number, fecha: string): Set<Mitad> {
  return new Set(
    cal.asignaciones.filter((a) => a.medico_id === medico && a.fecha === fecha).map((a) => a.mitad),
  );
}

const ordenar = (mitades: Set<Mitad>) => MITADES.filter((h) => mitades.has(h));

/**
 * Cambios que produce soltar un médico arrastrado (especificaciones, 7):
 * - de una celda a otra: lo mueve (con `copiar`, lo copia);
 * - desde el resumen a una celda: lo añade;
 * - fuera del calendario: lo quita de la celda de origen.
 * Devuelve [] si no cambia nada.
 */
export function cambiosAlSoltar(cal: Calendario, origen: Origen, destino: Destino, copiar = false): Cambio[] {
  const medico = origen.medico;
  const porFecha = new Map<string, Set<Mitad>>();
  const actuales = (fecha: string) => {
    if (!porFecha.has(fecha)) porFecha.set(fecha, mitadesDe(cal, medico, fecha));
    return porFecha.get(fecha)!;
  };

  if (origen.tipo === "celda") {
    if (destino && destino.fecha === origen.fecha && destino.turno === origen.turno) return [];
    if (!copiar || destino === null) {
      for (const h of MITADES_DE[origen.turno]) actuales(origen.fecha).delete(h);
    }
  }
  if (destino) {
    const ya = MITADES_DE[destino.turno].every((h) => mitadesDe(cal, medico, destino.fecha).has(h));
    if (ya && origen.tipo === "resumen") return [];
    for (const h of MITADES_DE[destino.turno]) actuales(destino.fecha).add(h);
  }

  const cambios: Cambio[] = [];
  for (const [fecha, mitades] of porFecha) {
    const antes = mitadesDe(cal, medico, fecha);
    const igual = antes.size === mitades.size && [...mitades].every((h) => antes.has(h));
    if (!igual) cambios.push({ medico_id: medico, fecha, mitades: ordenar(mitades) });
  }
  return cambios;
}

export type Jornada = "" | Turno | TipoJornada | "OTRA";

export const MITADES_JORNADA: Record<Exclude<Jornada, "OTRA">, Mitad[]> = {
  "": [],
  MANANA: ["M1", "M2"],
  TARDE: ["T1", "T2"],
  MANANA_MAS_MEDIA: ["M1", "M2", "T1"],
  TARDE_MAS_MEDIA: ["M2", "T1", "T2"],
  DOBLE: ["M1", "M2", "T1", "T2"],
};

export function jornadaDe(mitades: Set<Mitad>): Jornada {
  const clave = ordenar(mitades).join(",");
  const encontrada = Object.entries(MITADES_JORNADA).find(([, hs]) => hs.join(",") === clave);
  return encontrada ? (encontrada[0] as Jornada) : "OTRA";
}

export type EstadoCelda = "vacia" | "cubierta" | "falta" | "sobra";

/** Compara los médicos de cada mitad del turno con su cobertura; manda el peor caso. */
export function estadoCelda(cal: Calendario, fecha: string, turno: Turno): EstadoCelda {
  let estado: EstadoCelda = "vacia";
  for (const h of MITADES_DE[turno]) {
    const cob = cal.cobertura.find((c) => c.fecha === fecha && c.mitad === h);
    if (!cob) continue;
    const n = cal.asignaciones.filter((a) => a.fecha === fecha && a.mitad === h).length;
    if (n < cob.minimo) return "falta";
    if (n > cob.maximo) estado = "sobra";
    else if (estado === "vacia" && (n > 0 || cob.minimo > 0)) estado = "cubierta";
  }
  return estado;
}

export type Idoneidad = "si" | "ya" | "AUSENTE" | "NO_DISPONIBLE";

/** Si el médico puede ir a esa celda (para colorear al arrastrar). */
export function idoneidad(cal: Calendario, medico: MedicoCalendario, fecha: string, turno: Turno): Idoneidad {
  const mitades = mitadesDe(cal, medico.id, fecha);
  if (MITADES_DE[turno].every((h) => mitades.has(h))) return "ya";
  const no = medico.no_elegibles.find((n) => n.fecha === fecha && n.turno === turno);
  return no ? (no.motivo as Idoneidad) : "si";
}

export function foto(cal: Calendario): EstadoManual {
  return { asignaciones: cal.asignaciones, vetos: cal.vetos, roles: cal.roles ?? [] };
}

/** Papel (urgencias o domicilios) del médico esa tarde, si tiene. */
export function rolDe(cal: Calendario, medico: number, fecha: string): Rol | null {
  return (cal.roles ?? []).find((r) => r.medico_id === medico && r.fecha === fecha)?.rol ?? null;
}

export const NOMBRE_ROL: Record<Rol, string> = { URGENCIAS: "Urgencias", DOMICILIOS: "Domicilios" };


// --- Selector No / ½ / 1 del panel de un turno ---------------------------------------

export type Valor = 0 | 0.5 | 1;

const OTRO: Record<Turno, Turno> = { MANANA: "TARDE", TARDE: "MANANA" };

/** Mitad que se hace en un medio turno: la contigua al otro turno (especificaciones, 5.3). */
export const MITAD_CONTIGUA: Record<Turno, Mitad> = { MANANA: "M2", TARDE: "T1" };

/** Cuánto hace el médico de ese turno ese día. */
export function valorEnTurno(mitades: Set<Mitad>, turno: Turno): Valor {
  const n = MITADES_DE[turno].filter((h) => mitades.has(h)).length;
  return n === 2 ? 1 : n === 1 ? 0.5 : 0;
}

/** El medio turno solo tiene sentido pegado a un turno completo del mismo día. */
export function admiteMedio(mitades: Set<Mitad>, turno: Turno): boolean {
  return valorEnTurno(mitades, OTRO[turno]) === 1;
}

/** Mitades del día tras poner el turno a 0, ½ o 1, conservando el otro turno. */
export function mitadesConValor(mitades: Set<Mitad>, turno: Turno, valor: Valor): Mitad[] {
  const nuevas = new Set([...mitades].filter((h) => !MITADES_DE[turno].includes(h)));
  if (valor === 1) MITADES_DE[turno].forEach((h) => nuevas.add(h));
  if (valor === 0.5) nuevas.add(MITAD_CONTIGUA[turno]);
  return ordenar(nuevas);
}

/** Medios turnos → texto con ½: 7 → "3½", 1 → "½", 4 → "2". */
export function cifra(medios: number): string {
  const enteros = Math.floor(medios / 2);
  if (medios % 2 === 0) return String(enteros);
  return enteros === 0 ? "½" : `${enteros}½`;
}

/** "Dra. García" → "García" (como en las fichas del calendario). */
export const nombreCorto = (nombre: string) => nombre.replace(/^Dra?\.\s*/, "");
