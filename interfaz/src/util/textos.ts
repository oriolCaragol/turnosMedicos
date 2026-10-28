import type { AmbitoFestivo, Elegibilidad, Mitad, Preferencia, TipoJornada, Turno } from "../api/tipos";

export const DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"] as const;
export const DIAS_CORTOS = ["Lun", "Mar", "Mié", "Jue", "Vie"] as const;
export const TURNOS: Turno[] = ["MANANA", "TARDE"];
export const MITADES: Mitad[] = ["M1", "M2", "T1", "T2"];

export const NOMBRE_TURNO: Record<Turno, string> = { MANANA: "Mañana", TARDE: "Tarde" };

export const NOMBRE_MITAD: Record<Mitad, string> = {
  M1: "Mañana (1.ª mitad)",
  M2: "Mañana (2.ª mitad)",
  T1: "Tarde (1.ª mitad)",
  T2: "Tarde (2.ª mitad)",
};

export const MITADES_DE: Record<Turno, [Mitad, Mitad]> = { MANANA: ["M1", "M2"], TARDE: ["T1", "T2"] };

export const NOMBRE_ELEGIBILIDAD: Record<Elegibilidad, string> = {
  FIJO: "Fijo",
  HABITUAL: "Habitual",
  DISPONIBLE: "Disponible",
  NO_DISPONIBLE: "No disponible",
};

export const NOMBRE_JORNADA: Record<TipoJornada, string> = {
  MANANA_MAS_MEDIA: "Mañana + ½ tarde",
  TARDE_MAS_MEDIA: "½ mañana + tarde",
  DOBLE: "Mañana y tarde",
};

export const NOMBRE_PREFERENCIA: Record<Preferencia, string> = { PREFIERE: "Prefiere", EVITA: "Evita" };

export const NOMBRE_AMBITO: Record<AmbitoFestivo, string> = {
  NACIONAL: "Nacional",
  AUTONOMICO: "Autonómico",
  LOCAL: "Local",
  OTRO: "Otro",
};

/** Medios turnos → texto en turnos con coma decimal: 37 → "18,5". */
export function formatearMedios(medios: number): string {
  return medios % 2 ? `${(medios - 1) / 2},5` : String(medios / 2);
}

/** Turnos (admite coma o punto) → medios turnos; null si no es múltiplo de 0,5. */
export function turnosAMedios(texto: string): number | null {
  const valor = Number(texto.trim().replace(",", "."));
  if (texto.trim() === "" || !Number.isFinite(valor) || valor < 0) return null;
  const medios = valor * 2;
  return Number.isInteger(medios) ? medios : null;
}
