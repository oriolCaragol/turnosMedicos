/** Cálculos de las vistas de médico, sin React (se prueban con Vitest). */
import type { Calendario, HorarioTurno, Mitad, Rol, Turno } from "../api/tipos";
import { MITADES_DE, NOMBRE_TURNO, TURNOS } from "../util/textos";

export interface TurnoDia {
  turno: Turno;
  medio: boolean; // solo una de las dos mitades
  horas: string; // «08:00–15:00» (o la mitad que le toca)
}

export interface DiaMedico {
  fecha: string;
  turnos: TurnoDia[];
  rol: Rol | null;
}

function horasDe(horario: HorarioTurno | undefined, mitades: Mitad[]): string {
  if (!horario) return "";
  const corta = (h: string) => h.slice(0, 5);
  const [primera, segunda] = MITADES_DE[horario.turno];
  const inicio = mitades.includes(primera) ? horario.inicio : horario.corte;
  const fin = mitades.includes(segunda) ? horario.fin : horario.corte;
  return `${corta(inicio)}–${corta(fin)}`;
}

/** Los días que trabaja un médico en el mes, con sus turnos y si tiene urgencias o domicilios. */
export function diasDe(cal: Calendario, medico: number, horarios: HorarioTurno[] = []): DiaMedico[] {
  const porDia = new Map<string, Mitad[]>();
  for (const a of cal.asignaciones)
    if (a.medico_id === medico) porDia.set(a.fecha, [...(porDia.get(a.fecha) ?? []), a.mitad]);
  return [...porDia.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([fecha, mitades]) => ({
      fecha,
      turnos: TURNOS.filter((t) => MITADES_DE[t].some((m) => mitades.includes(m))).map((turno) => ({
        turno,
        medio: !MITADES_DE[turno].every((m) => mitades.includes(m)),
        horas: horasDe(
          horarios.find((h) => h.turno === turno),
          mitades,
        ),
      })),
      rol: (cal.roles ?? []).find((r) => r.medico_id === medico && r.fecha === fecha)?.rol ?? null,
    }));
}

export const textoTurno = (t: TurnoDia) => (t.medio ? `½ ${NOMBRE_TURNO[t.turno].toLowerCase()}` : NOMBRE_TURNO[t.turno]);
