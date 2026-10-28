import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * Dos usuarios a la vez sobre el mismo mes (diseño del modo servidor, 8 y 9): cada uno
 * ve los cambios del otro sin recargar, y un cambio ajeno vacía su historial de deshacer.
 */
const MES = "2026-12";

test.beforeAll(async ({ request }) => {
  // Se ejecuta tras calendario.spec.ts, que ya deja el equipo; si se lanza sola, lo crea.
  const medicos = await (await request.get("/api/medicos")).json();
  if (medicos.length > 0) return;
  for (const [nombre, codigo] of [
    ["Ana Ruiz", "ANA"],
    ["Bea Gil", "BEA"],
    ["Carlos Paz", "CAR"],
    ["Dani Sanz", "DAN"],
  ]) {
    const m = await (await request.post("/api/medicos", { data: { nombre, codigo } })).json();
    await request.put(`/api/medicos/${m.id}/reglas`, {
      data: { vigente_desde: "2026-11-01", elegibilidad: [], carga: { minimo: 0, maximo: 40 } },
    });
  }
  const cobertura = [];
  for (let d = 0; d < 5; d++)
    for (const mitad of ["M1", "M2", "T1", "T2"]) cobertura.push({ dia_semana: d, mitad, minimo: 1, maximo: 1 });
  await request.put("/api/cobertura/semanal", { data: cobertura });
  await request.put("/api/ajustes", { data: { todos_trabajan: false } });
});

const fichas = (page: Page, fecha: string) => page.locator(`[data-celda="${fecha}-MANANA"] [data-ficha]`);

async function quitar(page: Page, ficha: Locator) {
  const a = (await ficha.boundingBox())!;
  const b = (await page.getByRole("heading", { name: /Turnos médicos/ }).boundingBox())!;
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
  await page.mouse.down();
  await page.mouse.move(a.x + a.width / 2 + 10, a.y + a.height / 2, { steps: 3 });
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 12 });
  await page.mouse.up();
}

test("dos usuarios ven en vivo los cambios del otro", async ({ browser }) => {
  const [ctxA, ctxB] = [await browser.newContext(), await browser.newContext()];
  const [a, b] = [await ctxA.newPage(), await ctxB.newPage()];
  for (const p of [a, b]) {
    await p.goto(`/?mes=${MES}`);
    await expect(p.getByText("Sin generar", { exact: true })).toBeVisible();
  }

  // A genera: B lo ve sin recargar.
  await a.getByRole("button", { name: "Generar calendario" }).click();
  await expect(a.getByText("Borrador", { exact: true })).toBeVisible();
  await expect(b.getByText("Borrador", { exact: true })).toBeVisible();
  await expect(fichas(b, "2026-12-01")).toHaveCount(1);

  // A quita una ficha: puede deshacerlo; B ve el hueco.
  await quitar(a, fichas(a, "2026-12-01").first());
  await expect(fichas(a, "2026-12-01")).toHaveCount(0);
  await expect(a.getByRole("button", { name: "Deshacer" })).toBeEnabled();
  await expect(fichas(b, "2026-12-01")).toHaveCount(0);

  // B quita otra: A la ve desaparecer y ya no puede deshacer (no se deshace lo de otro);
  // B sí puede deshacer lo suyo.
  await quitar(b, fichas(b, "2026-12-02").first());
  await expect(fichas(b, "2026-12-02")).toHaveCount(0);
  await expect(fichas(a, "2026-12-02")).toHaveCount(0);
  await expect(a.getByRole("button", { name: "Deshacer" })).toBeDisabled();
  await expect(b.getByRole("button", { name: "Deshacer" })).toBeEnabled();

  // B deshace: A vuelve a ver la ficha.
  await b.getByRole("button", { name: "Deshacer" }).click();
  await expect(fichas(a, "2026-12-02")).toHaveCount(1);

  await ctxA.close();
  await ctxB.close();
});

test("un cambio sobre una versión antigua se rechaza y se muestra la actual", async ({ page, request }) => {
  // Esta página no recibe eventos: no se entera de los cambios de otros hasta que choca.
  await page.route("**/api/eventos", (ruta) => ruta.abort());
  await page.goto(`/?mes=${MES}`);
  await expect(page.getByText("Borrador", { exact: true })).toBeVisible();
  await expect(fichas(page, "2026-12-03")).toHaveCount(1);

  // Otro usuario publica el mes.
  expect((await request.post("/api/periodos/2026/12/publicar")).status()).toBe(200);

  // La página intenta cambiar su versión antigua: el servidor lo rechaza y se ve la actual.
  await quitar(page, fichas(page, "2026-12-03").first());
  await expect(page.getByText(/Otro usuario ha cambiado el calendario de este mes/)).toBeVisible();
  await expect(page.getByText("Publicado", { exact: true })).toBeVisible();
  await expect(fichas(page, "2026-12-03")).toHaveCount(1);

  expect((await request.post("/api/periodos/2026/12/reabrir")).status()).toBe(200);
});
