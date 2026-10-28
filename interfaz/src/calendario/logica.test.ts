import type { Calendario, MedicoCalendario } from "../api/tipos";
import {
  admiteMedio,
  cambiosAlSoltar,
  cifra,
  estadoCelda,
  idoneidad,
  jornadaDe,
  mitadesConValor,
  foto,
  nombreCorto,
  rolDe,
  valorEnTurno,
} from "./logica";

const medico = (id: number, extra: Partial<MedicoCalendario> = {}): MedicoCalendario => ({
  id,
  nombre: `M${id}`,
  codigo: `M${id}`,
  activo: true,
  con_carga: true,
  carga_manual: false,
  asignado: 0,
  asignado_manana: 0,
  asignado_tarde: 0,
  no_elegibles: [],
  habituales: [],
  urgencias: 0,
  domicilios: 0,
  tardes_disponibles: 0,
  ...extra,
});

const asig = (medico_id: number, fecha: string, mitades: string) =>
  mitades.split(",").map((mitad) => ({
    medico_id,
    fecha,
    mitad: mitad as "M1",
    origen: "GENERADOR" as const,
    bloqueada: false,
  }));

const cal = (asignaciones: ReturnType<typeof asig>): Calendario => ({
  anio: 2026,
  mes: 11,
  estado: "BORRADOR",
  version: 0,
  carga_por_rangos: true,
  publicado_en: null,
  dias: [],
  cobertura: ["M1", "M2", "T1", "T2"].map((mitad) => ({
    fecha: "2026-11-03",
    mitad: mitad as "M1",
    minimo: 1,
    maximo: 1,
  })),
  medicos: [medico(1), medico(2)],
  asignaciones,
  vetos: [],
  roles: [],
  avisos: [],
});

test("mover de mañana a tarde el mismo día", () => {
  const c = cal(asig(1, "2026-11-03", "M1,M2"));
  expect(
    cambiosAlSoltar(c, { tipo: "celda", medico: 1, fecha: "2026-11-03", turno: "MANANA" }, { fecha: "2026-11-03", turno: "TARDE" }),
  ).toEqual([{ medico_id: 1, fecha: "2026-11-03", mitades: ["T1", "T2"] }]);
});

test("mover a otro día cambia los dos días", () => {
  const c = cal(asig(1, "2026-11-03", "M1,M2"));
  expect(
    cambiosAlSoltar(c, { tipo: "celda", medico: 1, fecha: "2026-11-03", turno: "MANANA" }, { fecha: "2026-11-04", turno: "MANANA" }),
  ).toEqual([
    { medico_id: 1, fecha: "2026-11-03", mitades: [] },
    { medico_id: 1, fecha: "2026-11-04", mitades: ["M1", "M2"] },
  ]);
});

test("copiar mantiene el origen", () => {
  const c = cal(asig(1, "2026-11-03", "M1,M2"));
  const origen = { tipo: "celda" as const, medico: 1, fecha: "2026-11-03", turno: "MANANA" as const };
  expect(cambiosAlSoltar(c, origen, { fecha: "2026-11-03", turno: "TARDE" }, true)).toEqual([
    { medico_id: 1, fecha: "2026-11-03", mitades: ["M1", "M2", "T1", "T2"] },
  ]);
});

test("soltar fuera quita el turno, y conserva el resto de la jornada", () => {
  const c = cal(asig(1, "2026-11-03", "M1,M2,T1"));
  expect(cambiosAlSoltar(c, { tipo: "celda", medico: 1, fecha: "2026-11-03", turno: "TARDE" }, null)).toEqual([
    { medico_id: 1, fecha: "2026-11-03", mitades: ["M1", "M2"] },
  ]);
});

test("desde el resumen añade, y no hace nada si ya estaba", () => {
  const c = cal(asig(1, "2026-11-03", "M1,M2"));
  expect(cambiosAlSoltar(c, { tipo: "resumen", medico: 2 }, { fecha: "2026-11-03", turno: "TARDE" })).toEqual([
    { medico_id: 2, fecha: "2026-11-03", mitades: ["T1", "T2"] },
  ]);
  expect(cambiosAlSoltar(c, { tipo: "resumen", medico: 1 }, { fecha: "2026-11-03", turno: "MANANA" })).toEqual([]);
});

test("soltar en la misma celda no cambia nada", () => {
  const c = cal(asig(1, "2026-11-03", "M1,M2"));
  const origen = { tipo: "celda" as const, medico: 1, fecha: "2026-11-03", turno: "MANANA" as const };
  expect(cambiosAlSoltar(c, origen, { fecha: "2026-11-03", turno: "MANANA" })).toEqual([]);
});

test("jornadas", () => {
  expect(jornadaDe(new Set(["M1", "M2"]))).toBe("MANANA");
  expect(jornadaDe(new Set(["M2", "T1", "T2"]))).toBe("TARDE_MAS_MEDIA");
  expect(jornadaDe(new Set())).toBe("");
  expect(jornadaDe(new Set(["M1"]))).toBe("OTRA");
});

test("estado de la celda según la cobertura", () => {
  expect(estadoCelda(cal([]), "2026-11-03", "MANANA")).toBe("falta");
  expect(estadoCelda(cal(asig(1, "2026-11-03", "M1,M2")), "2026-11-03", "MANANA")).toBe("cubierta");
  const doble = cal([...asig(1, "2026-11-03", "M1,M2"), ...asig(2, "2026-11-03", "M1,M2")]);
  expect(estadoCelda(doble, "2026-11-03", "MANANA")).toBe("sobra");
  // Solo la 1.ª mitad de la tarde: falta en la 2.ª.
  expect(estadoCelda(cal(asig(1, "2026-11-03", "T1")), "2026-11-03", "TARDE")).toBe("falta");
});

test("idoneidad para arrastrar", () => {
  const c = cal(asig(1, "2026-11-03", "M1,M2"));
  const ausente = medico(2, { no_elegibles: [{ fecha: "2026-11-03", turno: "TARDE", motivo: "AUSENTE" }] });
  expect(idoneidad(c, medico(1), "2026-11-03", "MANANA")).toBe("ya");
  expect(idoneidad(c, ausente, "2026-11-03", "TARDE")).toBe("AUSENTE");
  expect(idoneidad(c, ausente, "2026-11-03", "MANANA")).toBe("si");
});

test("selector No / ½ / 1", () => {
  const manana = new Set<"M1" | "M2" | "T1" | "T2">(["M1", "M2"]);
  expect(valorEnTurno(manana, "MANANA")).toBe(1);
  expect(valorEnTurno(manana, "TARDE")).toBe(0);
  expect(admiteMedio(manana, "TARDE")).toBe(true);
  expect(admiteMedio(manana, "MANANA")).toBe(false);
  expect(mitadesConValor(manana, "TARDE", 0.5)).toEqual(["M1", "M2", "T1"]);
  expect(mitadesConValor(manana, "TARDE", 1)).toEqual(["M1", "M2", "T1", "T2"]);
  expect(mitadesConValor(new Set(["T1", "T2"]), "MANANA", 0.5)).toEqual(["M2", "T1", "T2"]);
  expect(mitadesConValor(new Set(["M1", "M2", "T1"]), "TARDE", 0)).toEqual(["M1", "M2"]);
  expect(valorEnTurno(new Set(["M1", "M2", "T1"]), "TARDE")).toBe(0.5);
});

test("cifras y nombres cortos", () => {
  expect(cifra(7)).toBe("3½");
  expect(cifra(1)).toBe("½");
  expect(cifra(4)).toBe("2");
  expect(nombreCorto("Dra. García")).toBe("García");
  expect(nombreCorto("Dr. López")).toBe("López");
  expect(nombreCorto("Ana Ruiz")).toBe("Ana Ruiz");
});

test("papel de urgencias o domicilios y foto para deshacer", () => {
  const c = { ...cal(asig(1, "2026-11-03", "T1,T2")), roles: [{ fecha: "2026-11-03", rol: "URGENCIAS" as const, medico_id: 1, manual: false }] };
  expect(rolDe(c, 1, "2026-11-03")).toBe("URGENCIAS");
  expect(rolDe(c, 2, "2026-11-03")).toBeNull();
  expect(foto(c).roles).toEqual(c.roles);
});
