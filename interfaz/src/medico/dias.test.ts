import { describe, expect, it } from "vitest";

import type { Calendario, HorarioTurno } from "../api/tipos";
import { diasDe, textoTurno } from "./dias";

const asig = (medico_id: number, fecha: string, mitad: "M1" | "M2" | "T1" | "T2") => ({
  medico_id,
  fecha,
  mitad,
  origen: "GENERADOR" as const,
  bloqueada: false,
});

const cal = {
  medicos: [
    { id: 1, nombre: "Bea Gil" },
    { id: 2, nombre: "Ana Ruiz" },
  ],
  asignaciones: [
    asig(1, "2026-11-03", "M1"),
    asig(1, "2026-11-03", "M2"),
    asig(1, "2026-11-02", "T2"),
    asig(2, "2026-11-03", "M1"),
    asig(2, "2026-11-03", "M2"),
    asig(2, "2026-11-03", "T1"),
    asig(2, "2026-11-03", "T2"),
  ],
  roles: [{ fecha: "2026-11-03", rol: "URGENCIAS", medico_id: 2, manual: false }],
} as unknown as Calendario;

const horarios: HorarioTurno[] = [
  { turno: "MANANA", inicio: "08:00:00", corte: "11:30:00", fin: "15:00:00" },
  { turno: "TARDE", inicio: "15:00:00", corte: "18:30:00", fin: "22:00:00" },
];

describe("vistas de médico", () => {
  it("lista los días de un médico en orden, con medio turno y sus horas", () => {
    const dias = diasDe(cal, 1, horarios);
    expect(dias.map((d) => d.fecha)).toEqual(["2026-11-02", "2026-11-03"]);
    expect(dias[0].turnos).toEqual([{ turno: "TARDE", medio: true, horas: "18:30–22:00" }]);
    expect(textoTurno(dias[0].turnos[0])).toBe("½ tarde");
    expect(dias[1].turnos).toEqual([{ turno: "MANANA", medio: false, horas: "08:00–15:00" }]);
    expect(dias[1].rol).toBeNull();
  });

  it("indica urgencias o domicilios", () => {
    const [dia] = diasDe(cal, 2, horarios);
    expect(dia.turnos.map(textoTurno)).toEqual(["Mañana", "Tarde"]);
    expect(dia.rol).toBe("URGENCIAS");
  });
});
