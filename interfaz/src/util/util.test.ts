import { diaSemana, formatearFecha, nombreMes, ultimoDia } from "./fechas";
import { formatearMedios, turnosAMedios } from "./textos";

test("medios turnos", () => {
  expect(formatearMedios(37)).toBe("18,5");
  expect(formatearMedios(32)).toBe("16");
  expect(formatearMedios(1)).toBe("0,5");
  expect(turnosAMedios("18,5")).toBe(37);
  expect(turnosAMedios("16")).toBe(32);
  expect(turnosAMedios("16.25")).toBeNull();
  expect(turnosAMedios("")).toBeNull();
  expect(turnosAMedios("-1")).toBeNull();
});

test("fechas", () => {
  expect(ultimoDia("2026-11")).toBe("2026-11-30");
  expect(ultimoDia("2028-02")).toBe("2028-02-29");
  expect(formatearFecha("2026-11-03")).toBe("03/11/2026");
  expect(nombreMes("2026-11")).toBe("noviembre de 2026");
  expect(diaSemana("2026-11-02")).toBe(0); // lunes
  expect(diaSemana("2026-11-08")).toBe(6); // domingo
});
