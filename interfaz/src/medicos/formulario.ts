/** Conversión entre las reglas de la API y el formulario de la tarjeta de un médico. */

import type { Preferencia, ReglasGuardar, ReglasLeidas, TipoJornada, Turno } from "../api/tipos";
import { clave, cuadriculaUniforme, type Cuadricula } from "../componentes/CuadriculaElegibilidad";
import { TURNOS } from "../util/textos";

export interface Formulario {
  elegibilidad: Cuadricula;
  jornadas: Record<number, TipoJornada | "">;
  minimo: number | null;
  maximo: number | null;
  porTurno: Record<Turno, { minimo: number | null; maximo: number | null }>;
  preferencias: Record<string, Preferencia | "">;
}

export function aFormulario(r: ReglasLeidas): Formulario {
  const f: Formulario = {
    elegibilidad: cuadriculaUniforme(() => "DISPONIBLE"),
    jornadas: {},
    minimo: r.carga?.minimo ?? null,
    maximo: r.carga?.maximo ?? null,
    porTurno: { MANANA: { minimo: null, maximo: null }, TARDE: { minimo: null, maximo: null } },
    preferencias: {},
  };
  for (const c of r.elegibilidad) f.elegibilidad[clave(c.dia_semana, c.turno)] = c.valor;
  for (const j of r.jornadas ?? []) f.jornadas[j.dia_semana] = j.tipo;
  for (const c of r.carga_por_turno ?? []) f.porTurno[c.turno] = { minimo: c.minimo || null, maximo: c.maximo ?? null };
  for (const p of r.preferencias ?? []) f.preferencias[clave(p.dia_semana, p.turno)] = p.valor;
  return f;
}

export const cargaValida = (f: Formulario) => f.minimo !== null && f.maximo !== null && f.minimo <= f.maximo;

/**
 * Reglas listas para guardar. Si la carga mensual falta o no es válida, se
 * guarda todo lo demás y la carga se omite (el servidor la deja como estaba).
 */
export function aGuardar(f: Formulario, vigente_desde: string): ReglasGuardar {
  const separar = (k: string) => {
    const [d, turno] = k.split("-");
    return { dia_semana: Number(d), turno: turno as Turno };
  };
  return {
    vigente_desde,
    elegibilidad: Object.entries(f.elegibilidad).map(([k, valor]) => ({ ...separar(k), valor })),
    jornadas: Object.entries(f.jornadas)
      .filter(([, tipo]) => tipo)
      .map(([d, tipo]) => ({ dia_semana: Number(d), tipo: tipo as TipoJornada })),
    carga: cargaValida(f) ? { minimo: f.minimo!, maximo: f.maximo! } : undefined,
    carga_por_turno: TURNOS.filter((t) => f.porTurno[t].minimo !== null || f.porTurno[t].maximo !== null).map((t) => ({
      turno: t,
      minimo: f.porTurno[t].minimo ?? 0,
      maximo: f.porTurno[t].maximo,
    })),
    preferencias: Object.entries(f.preferencias)
      .filter(([, valor]) => valor)
      .map(([k, valor]) => ({ ...separar(k), valor: valor as Preferencia })),
  };
}
