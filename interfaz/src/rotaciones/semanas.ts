/** Cálculo de a quién le toca cada semana un turno rotativo (igual que el motor). */

const DIA = 24 * 3600 * 1000;

function aFecha(iso: string): Date {
  const [a, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(a, m - 1, d));
}

function aIso(f: Date): string {
  return f.toISOString().slice(0, 10);
}

/** Lunes de la semana de una fecha ISO. */
export function lunesDe(iso: string): string {
  const f = aFecha(iso);
  return aIso(new Date(f.getTime() - ((f.getUTCDay() + 6) % 7) * DIA));
}

/** Médico al que le toca la semana de `fecha` (o null si es antes de empezar). */
export function titularDeLaSemana(medicos: number[], desde: string, fecha: string): number | null {
  if (medicos.length < 2) return null;
  const inicio = aFecha(lunesDe(desde)).getTime();
  const lunes = aFecha(lunesDe(fecha)).getTime();
  if (lunes < inicio) return null;
  const semana = Math.round((lunes - inicio) / (7 * DIA));
  return medicos[semana % medicos.length];
}

/** Lunes de las semanas que tocan días laborables de un mes ("AAAA-MM"). */
export function semanasDelMes(mes: string): string[] {
  const [a, m] = mes.split("-").map(Number);
  const semanas: string[] = [];
  for (let d = 1; d <= new Date(Date.UTC(a, m, 0)).getUTCDate(); d++) {
    const f = new Date(Date.UTC(a, m - 1, d));
    if (f.getUTCDay() === 0 || f.getUTCDay() === 6) continue;
    const lunes = lunesDe(aIso(f));
    if (!semanas.includes(lunes)) semanas.push(lunes);
  }
  return semanas;
}
