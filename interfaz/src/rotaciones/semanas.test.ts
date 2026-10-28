import { lunesDe, semanasDelMes, titularDeLaSemana } from "./semanas";

test("lunes de la semana", () => {
  expect(lunesDe("2026-11-05")).toBe("2026-11-02");
  expect(lunesDe("2026-11-02")).toBe("2026-11-02");
  expect(lunesDe("2026-11-08")).toBe("2026-11-02"); // domingo
});

test("a quién le toca cada semana", () => {
  const medicos = [10, 20, 30];
  expect(titularDeLaSemana(medicos, "2026-11-04", "2026-11-02")).toBe(10); // misma semana
  expect(titularDeLaSemana(medicos, "2026-11-04", "2026-11-12")).toBe(20);
  expect(titularDeLaSemana(medicos, "2026-11-04", "2026-11-19")).toBe(30);
  expect(titularDeLaSemana(medicos, "2026-11-04", "2026-11-26")).toBe(10);
  expect(titularDeLaSemana(medicos, "2026-11-04", "2026-10-30")).toBeNull(); // antes de empezar
  expect(titularDeLaSemana([10], "2026-11-04", "2026-11-12")).toBeNull();
  // Cruza el cambio de hora y de mes sin perder la cuenta.
  expect(titularDeLaSemana([1, 2], "2026-10-19", "2026-11-02")).toBe(1);
});

test("semanas de un mes", () => {
  expect(semanasDelMes("2026-11")).toEqual(["2026-11-02", "2026-11-09", "2026-11-16", "2026-11-23", "2026-11-30"]);
  expect(semanasDelMes("2026-08")[0]).toBe("2026-08-03"); // el 1 de agosto es sábado: la primera semana es la del 3
  expect(semanasDelMes("2026-10")[0]).toBe("2026-09-28"); // el 1 de octubre es jueves
});
