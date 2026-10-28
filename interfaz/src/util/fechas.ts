/** Fechas en formato ISO (AAAA-MM-DD), sin zonas horarias. */

const MESES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

const dos = (n: number) => String(n).padStart(2, "0");

export function iso(fecha: Date): string {
  return `${fecha.getFullYear()}-${dos(fecha.getMonth() + 1)}-${dos(fecha.getDate())}`;
}

export const hoy = () => iso(new Date());

/** "2026-11" → "2026-11-01" */
export const primerDia = (mes: string) => `${mes}-01`;

/** "2026-11" → "2026-11-30" */
export function ultimoDia(mes: string): string {
  const [a, m] = mes.split("-").map(Number);
  return `${mes}-${dos(new Date(a, m, 0).getDate())}`;
}

/** Mes actual como "AAAA-MM". */
export const mesActual = () => hoy().slice(0, 7);

/** "2026-11-03" → "03/11/2026" */
export function formatearFecha(fecha: string): string {
  const [a, m, d] = fecha.split("-");
  return `${d}/${m}/${a}`;
}

/** "2026-11" → "noviembre de 2026" */
export function nombreMes(mes: string): string {
  const [a, m] = mes.split("-").map(Number);
  return `${MESES[m - 1]} de ${a}`;
}

/** Día de la semana (0 = lunes … 6 = domingo) de una fecha ISO. */
export function diaSemana(fecha: string): number {
  const [a, m, d] = fecha.split("-").map(Number);
  return (new Date(a, m - 1, d).getDay() + 6) % 7;
}

/** Mes siguiente al actual como "AAAA-MM": el que normalmente se planifica. */
export function mesSiguiente(): string {
  const [a, m] = mesActual().split("-").map(Number);
  return m === 12 ? `${a + 1}-01` : `${a}-${dos(m + 1)}`;
}

/** «lun 3 nov» (para listas en el móvil). */
export function fechaCorta(fecha: string): string {
  const [a, m, d] = fecha.split("-").map(Number);
  return new Date(a, m - 1, d).toLocaleDateString("es-ES", { weekday: "short", day: "numeric", month: "short" });
}
