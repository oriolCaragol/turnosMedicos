import { expect, test } from "@playwright/test";

// Las fuentes de festivos son ficheros de interfaz/e2e/datos (ver scripts/e2e.sh).

test("festivos oficiales: cambiar el municipio, buscar y añadir los que faltan", async ({ page, request }) => {
  const municipioAntes = (await (await request.get("/api/ajustes")).json()).municipio;
  await page.goto("/configuracion");
  const seccion = page.locator("section", { has: page.getByRole("heading", { name: "Festivos oficiales" }) });
  await expect(seccion.getByText("Madrid", { exact: true })).toBeVisible();
  await expect(page.locator("header small")).toContainText("festivos de Madrid (Comunidad de Madrid)");

  await seccion.getByRole("button", { name: "Cambiar" }).click();
  await seccion.getByLabel("Municipio").fill("valenc");
  await seccion.getByRole("button", { name: /^València/ }).click();
  await expect(page.getByText("Municipio del centro: València")).toBeVisible();
  await expect(page.locator("header small")).toContainText("festivos de València (Comunitat Valenciana)");

  await seccion.getByLabel("Año").selectOption("2026");
  await seccion.getByRole("button", { name: "Buscar festivos oficiales" }).click();
  const filas = seccion.locator("tbody tr");
  await expect(filas).toHaveCount(4);
  await expect(filas.filter({ hasText: "San Vicente Mártir" })).toContainText("Falta");
  await expect(filas.filter({ hasText: "Año Nuevo" })).toContainText("Ya está"); // precargado de 2026
  await expect(seccion.getByRole("link", { name: "BOE-A-2025-21667" }).first()).toHaveAttribute("href", /boe\.es/);
  await expect(seccion.getByText(/En tus festivos de 2026, pero no en las fuentes/)).toBeVisible();

  await seccion.getByRole("button", { name: "Añadir los 3 que faltan" }).click();
  await expect(page.getByText("Añadidos 3 festivos")).toBeVisible();
  await expect(seccion.getByRole("button", { name: "No falta ninguno" })).toBeDisabled();
  await expect(filas.filter({ hasText: "San Vicente Mártir" })).toContainText("Ya está");

  await page.goto("/festivos?mes=2026-01");
  await expect(page.getByRole("cell", { name: "San Vicente Mártir", exact: true })).toBeVisible();
  await expect(page.getByText(/Nacionales, autonómicos y locales de València/)).toBeVisible();

  // Deja los datos como estaban para las demás pruebas.
  for (const f of await (await request.get("/api/festivos?anio=2026")).json())
    if (["2026-01-22", "2026-04-13", "2026-10-09"].includes(f.fecha)) await request.delete(`/api/festivos/${f.id}`);
  const ajustes = await (await request.get("/api/ajustes")).json();
  await request.put("/api/ajustes", { data: { ...ajustes, municipio: municipioAntes } });
});

test("datos: importar una copia sustituye los datos (y se pueden recuperar)", async ({ page, request }) => {
  const original = await (await request.get("/api/copia-de-seguridad")).body();
  const antes = (await (await request.get("/api/medicos")).json()).length;
  await request.post("/api/medicos", { data: { nombre: "Médico temporal", codigo: "TMP" } });

  await page.goto("/configuracion");
  const seccion = page.locator("section", { has: page.getByRole("heading", { name: "Datos: exportar e importar" }) });
  await expect(seccion.getByRole("link", { name: "Exportar copia de los datos" })).toHaveAttribute("href", "/api/copia-de-seguridad");

  page.once("dialog", (d) => d.accept());
  await seccion.getByLabel("Copia de los datos para importar").setInputFiles({
    name: "copia.sqlite",
    mimeType: "application/vnd.sqlite3",
    buffer: original,
  });
  await expect(seccion.getByText(`Datos importados: ${antes} médicos`)).toBeVisible();
  await expect(seccion.getByText(/antes-de-importar/)).toBeVisible();
  const despues = await (await request.get("/api/medicos")).json();
  expect(despues.map((m: { nombre: string }) => m.nombre)).not.toContain("Médico temporal");

  // Un fichero que no es una copia: error y nada cambia.
  page.once("dialog", (d) => d.accept());
  await seccion.getByLabel("Copia de los datos para importar").setInputFiles({
    name: "notas.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("hola"),
  });
  await expect(seccion.getByRole("alert")).toContainText("no es una base de datos SQLite");
  expect((await (await request.get("/api/medicos")).json()).length).toBe(antes);
});

test("vista del calendario: asignados frente a necesarios, oculto por defecto", async ({ page }) => {
  const cabecera = page.locator('[data-celda="2026-11-03-MANANA"] button').first();
  await page.goto("/?mes=2026-11");
  await expect(cabecera).toContainText("MAÑANA");
  await expect(cabecera).not.toContainText("/");

  await page.goto("/configuracion?mes=2026-11");
  const opcion = page.getByLabel("Mostrar en cada turno los médicos asignados frente a los necesarios");
  await expect(opcion).not.toBeChecked();
  await opcion.check();
  await expect(page.getByText("Ajuste guardado")).toBeVisible();

  await page.goto("/?mes=2026-11");
  await expect(cabecera).toContainText(/\d+\/\d/);
  await page.goto("/configuracion?mes=2026-11");
  await page.getByLabel("Mostrar en cada turno los médicos asignados frente a los necesarios").uncheck();
  await expect(page.getByText("Ajuste guardado")).toBeVisible();
});
