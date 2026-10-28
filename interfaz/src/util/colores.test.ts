import { colorLibre, PALETA, textoSobre } from "./colores";

test("texto legible sobre cada color", () => {
  expect(textoSobre("#ffffff")).toBe("#15232a");
  expect(textoSobre("#000000")).toBe("#ffffff");
  expect(textoSobre("#f6e27f")).toBe("#15232a"); // amarillo claro → texto oscuro
  expect(textoSobre("#2f6f9f")).toBe("#ffffff"); // azul oscuro → texto blanco
  for (const [color] of PALETA) expect(["#15232a", "#ffffff"]).toContain(textoSobre(color));
});

test("color libre para un médico nuevo", () => {
  expect(colorLibre([])).toBe(PALETA[0][0]);
  expect(colorLibre([PALETA[0][0].toUpperCase(), null])).toBe(PALETA[1][0]);
});
