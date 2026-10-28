import { expect, test } from "@playwright/test";

/**
 * Un médico recién añadido se queda al final mientras se edita (aunque su nombre vaya
 * antes en el alfabeto); al volver a entrar en la pestaña, la lista se ordena.
 * Se ejecuta tras calendario.spec.ts, que deja el equipo de cuatro.
 */
test("un médico nuevo se queda al final hasta volver a entrar en la pestaña", async ({ page, request }) => {
  await page.goto("/medicos?mes=2026-11");
  const tarjetas = page.locator("[data-medico]");
  await expect(tarjetas.first()).toBeVisible();
  const antes = await tarjetas.count();

  await page.getByRole("button", { name: "Añadir médico" }).click();
  await expect(tarjetas).toHaveCount(antes + 1);
  const nueva = tarjetas.last();
  await expect(nueva.getByLabel("Nombre del médico")).toHaveValue("Nuevo médico");
  // Le pone un nombre que va el primero en el alfabeto: sigue al final.
  await nueva.getByLabel("Nombre del médico").fill("Aarón Abad");
  await nueva.getByLabel("Código").fill("AAB");
  await expect
    .poll(async () => (await (await request.get("/api/medicos")).json()).some((m: { nombre: string }) => m.nombre === "Aarón Abad"))
    .toBe(true);
  await page.waitForTimeout(500); // la lista ya se ha vuelto a pedir tras guardar
  await expect(tarjetas.last().getByLabel("Nombre del médico")).toHaveValue("Aarón Abad");

  // Al volver a entrar en la pestaña, en su sitio por orden alfabético.
  await page.getByRole("link", { name: "Cobertura" }).click();
  await page.getByRole("link", { name: /Médicos y reglas/ }).click();
  await expect(tarjetas.first().getByLabel("Nombre del médico")).toHaveValue("Aarón Abad");

  // Se borra, para no cambiar el equipo de las demás pruebas.
  const medicos = await (await request.get("/api/medicos")).json();
  const id = medicos.find((m: { nombre: string }) => m.nombre === "Aarón Abad").id;
  expect((await request.delete(`/api/medicos/${id}`)).status()).toBe(204);
});
