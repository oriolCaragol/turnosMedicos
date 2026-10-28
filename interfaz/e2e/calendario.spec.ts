import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";

const MES = "2026-11";

/** Equipo pequeño: 4 médicos, 1 médico por turno. */
test.beforeAll(async ({ request }) => {
  const medicos = await (await request.get("/api/medicos")).json();
  test.skip(medicos.length > 0, "La prueba necesita una base de datos vacía");
  for (const [nombre, codigo] of [
    ["Ana Ruiz", "ANA"],
    ["Bea Gil", "BEA"],
    ["Carlos Paz", "CAR"],
    ["Dani Sanz", "DAN"],
  ]) {
    const m = await (await request.post("/api/medicos", { data: { nombre, codigo } })).json();
    await request.put(`/api/medicos/${m.id}/reglas`, {
      data: { vigente_desde: `${MES}-01`, elegibilidad: [], carga: { minimo: 0, maximo: 40 } },
    });
  }
  const cobertura = [];
  for (let d = 0; d < 5; d++)
    for (const mitad of ["M1", "M2", "T1", "T2"]) cobertura.push({ dia_semana: d, mitad, minimo: 1, maximo: 1 });
  await request.put("/api/cobertura/semanal", { data: cobertura });
  // Las pruebas usan 4 médicos y 1 por turno: sin «todos trabajan cada día», que
  // chocaría con la cobertura máxima. Su prueba la activa y la vuelve a quitar.
  await request.put("/api/ajustes", { data: { todos_trabajan: false } });
  // Noviembre con un solo festivo entre semana (el lunes 2): sin el local de Madrid del
  // lunes 9 (la Almudena), que traen los precargados.
  const festivos = await (await request.get("/api/festivos?anio=2026")).json();
  const almudena = festivos.find((f: { fecha: string }) => f.fecha === "2026-11-09");
  if (almudena) await request.delete(`/api/festivos/${almudena.id}`);
});

const franja = (page: Page, fecha: string, turno: "MANANA" | "TARDE") =>
  page.locator(`[data-celda="${fecha}-${turno}"]`);

async function arrastrar(page: Page, origen: Locator, destino: Locator) {
  const a = (await origen.boundingBox())!;
  const b = (await destino.boundingBox())!;
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
  await page.mouse.down();
  await page.mouse.move(a.x + a.width / 2 + 10, a.y + a.height / 2, { steps: 3 });
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 12 });
  await page.mouse.up();
}

test("generar, editar arrastrando, deshacer, regenerar y publicar", async ({ page }) => {
  // Alto suficiente para ver a la vez el calendario y la tabla de carga.
  await page.setViewportSize({ width: 1400, height: 2400 });
  await page.goto(`/?mes=${MES}`);
  await expect(page.getByText("Sin generar", { exact: true })).toBeVisible();
  await expect(page.locator("header output")).toHaveText("Noviembre 2026");

  await page.getByRole("button", { name: "Generar calendario" }).click();
  await expect(page.getByText("Borrador", { exact: true })).toBeVisible();
  await expect(page.getByText("Todos los turnos cumplen su cobertura")).toBeVisible();
  const martes = franja(page, "2026-11-03", "MANANA");
  await expect(martes.locator("[data-ficha]")).toHaveCount(1);
  await expect(page.getByText("Traslado de Todos los Santos")).toBeVisible(); // festivo en la Comunidad de Madrid

  // Quitar: soltar la ficha fuera del calendario (sobre la cabecera).
  await arrastrar(page, martes.locator("[data-ficha]").first(), page.getByRole("heading", { name: /Turnos médicos/ }));
  await expect(martes.locator("[data-ficha]")).toHaveCount(0);
  await expect(page.getByText("El martes 3/11 por la mañana falta 1 médico.")).toBeVisible();
  await expect(page.getByRole("link", { name: /Calendario/ }).locator("span")).toHaveText("1");
  await expect(martes.getByText("BLOQ.")).toBeVisible();

  // Deshacer con el teclado, rehacer y deshacer con los botones.
  await page.locator("body").click({ position: { x: 5, y: 300 } });
  await page.keyboard.press("Control+z");
  await expect(martes.locator("[data-ficha]")).toHaveCount(1);
  await page.getByRole("button", { name: "Rehacer" }).click();
  await expect(martes.locator("[data-ficha]")).toHaveCount(0);
  await page.getByRole("button", { name: "Deshacer" }).click();
  await expect(martes.locator("[data-ficha]")).toHaveCount(1);
  await expect(page.getByText("Todos los turnos cumplen su cobertura")).toBeVisible();

  // Añadir desde la tabla de carga a un turno ya cubierto: sobra uno y queda bloqueado.
  const miercoles = franja(page, "2026-11-04", "TARDE");
  const delDia = (await page.locator('[data-celda^="2026-11-04"] [data-ficha]').allTextContents()).join(" ");
  const libre = ["Ana Ruiz", "Bea Gil", "Carlos Paz", "Dani Sanz"].find((n) => !delDia.includes(n.split(" ")[0]))!;
  await arrastrar(page, page.locator(`table [data-ficha="${libre}"]`), miercoles);
  await expect(miercoles.locator("[data-ficha]")).toHaveCount(2);
  await expect(page.getByText("El miércoles 4/11 por la tarde sobra 1 médico.")).toBeVisible();
  await expect(miercoles.getByText("BLOQ.")).toBeVisible();

  // Regenerar respeta lo bloqueado.
  await page.getByRole("button", { name: "Regenerar" }).click();
  await expect(miercoles.locator("[data-ficha]")).toHaveCount(2);

  // Publicar deja el calendario en solo lectura.
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Publicar" }).click();
  await expect(page.getByText("Publicado", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Regenerar" })).toHaveCount(0);
  await page.getByRole("button", { name: "Reabrir" }).click();
  await expect(page.getByText("Borrador", { exact: true })).toBeVisible();
});

test("panel de un turno: medio turno y volver a automático", async ({ page }) => {
  await page.goto(`/?mes=${MES}`);
  const tarde = franja(page, "2026-11-05", "TARDE");
  // Quien hace la mañana del jueves 5 puede añadir media tarde.
  const manana = await franja(page, "2026-11-05", "MANANA").locator("[data-ficha]").first().getAttribute("title");
  const nombre = manana!.split(" · ")[0];
  await tarde.getByRole("button").first().click();
  const panel = page.getByRole("dialog");
  await expect(panel.getByRole("heading", { name: "Jueves 5 nov" })).toBeVisible();

  const grupo = panel.getByRole("group", { name: nombre });
  await grupo.getByRole("button", { name: "½" }).click();
  await expect(grupo.getByRole("button", { name: "½" })).toHaveAttribute("aria-pressed", "true");
  await expect(tarde.locator(`[data-ficha$="½"]`)).toHaveCount(1);
  await expect(page.getByText("El jueves 5/11 en la primera mitad de la tarde sobra 1 médico.")).toBeVisible();

  await panel.getByRole("button", { name: "Volver a automático" }).click();
  await expect(page.getByText("Turno devuelto al generador")).toBeVisible();
  await expect(panel.getByText("Cualquier cambio bloquea este turno.")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(tarde.getByText("BLOQ.")).toHaveCount(0);
});

test("vista en lista: un botón cambia la vista y se recuerda", async ({ page }) => {
  await page.goto(`/?mes=${MES}`);
  await expect(page.locator('[data-vista="cuadricula"]')).toBeVisible();
  await page.getByRole("button", { name: "Lista" }).click();
  await expect(page.locator('[data-vista="lista"]')).toBeVisible();
  await expect(page.locator('[data-vista="cuadricula"]')).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Lista" })).toHaveAttribute("aria-pressed", "true");

  // Los días van uno tras otro, con el festivo incluido, y los turnos se editan igual.
  const filas = page.locator('[data-vista="lista"] > [id^="dia-"]');
  await expect(filas).toHaveCount(21);
  await expect(filas.first()).toContainText("Traslado de Todos los Santos");
  await franja(page, "2026-11-12", "MANANA").getByRole("button").first().click();
  await expect(page.getByRole("dialog").getByRole("heading", { name: "Jueves 12 nov" })).toBeVisible();
  await page.keyboard.press("Escape");

  // La elección se recuerda al volver a la página.
  await page.reload();
  await expect(page.locator('[data-vista="lista"]')).toBeVisible();
  await page.getByRole("button", { name: "Cuadrícula" }).click();
  await expect(page.locator('[data-vista="cuadricula"]')).toBeVisible();
});

test("médicos y reglas: tarjetas que se guardan solas y ausencias", async ({ page, request }) => {
  await page.goto(`/medicos?mes=${MES}`);
  const tarjeta = page.locator('[data-medico="ANA"]');
  await expect(tarjeta.getByText("Reglas guardadas.")).toBeVisible();

  await tarjeta.getByRole("button", { name: "Viernes, tarde: Disponible" }).click();
  await expect(tarjeta.getByRole("button", { name: "Viernes, tarde: Habitual" })).toBeVisible();
  await expect(tarjeta.getByText("Guardado.")).toBeVisible();
  const medicos = await (await request.get("/api/medicos")).json();
  const ana = medicos.find((m: { codigo: string }) => m.codigo === "ANA");
  await expect
    .poll(async () => {
      const reglas = await (await request.get(`/api/medicos/${ana.id}/reglas?fecha=${MES}-15`)).json();
      return reglas.elegibilidad.find((c: { dia_semana: number; turno: string }) => c.dia_semana === 4 && c.turno === "TARDE").valor;
    })
    .toBe("HABITUAL");

  await tarjeta.getByRole("button", { name: "Añadir ausencia" }).click();
  await expect(tarjeta.getByLabel("Desde")).toHaveValue(`${MES}-01`);
  await tarjeta.getByLabel("Turnos de la ausencia").selectOption({ label: "Solo tardes" });
  await expect
    .poll(async () => (await (await request.get(`/api/ausencias?medico_id=${ana.id}`)).json())[0]?.turno)
    .toBe("TARDE");

  await tarjeta.getByRole("button", { name: "Más reglas…" }).click();
  await page.getByLabel("Jornada del martes").selectOption({ label: "Mañana + ½ tarde" });
  await page.getByRole("dialog").getByRole("button", { name: "Hecho" }).click();
  await expect(tarjeta.getByText("Mar: Mañana + ½ tarde")).toBeVisible();
});

test("las reglas persisten aunque se cambie de pestaña enseguida", async ({ page }) => {
  await page.goto(`/medicos?mes=${MES}`);
  const ana = page.locator('[data-medico="ANA"]');
  await expect(ana.getByText("Reglas guardadas.")).toBeVisible();
  // Cambio y salida inmediata de la pestaña, sin esperar al autoguardado.
  await ana.getByRole("button", { name: "Lunes, tarde: Disponible" }).click();
  await page.getByRole("link", { name: "Cobertura" }).click();
  await expect(page.getByText("Médicos necesarios por turno")).toBeVisible();
  await page.getByRole("link", { name: "Médicos y reglas" }).click();
  await expect(page.locator('[data-medico="ANA"]').getByRole("button", { name: "Lunes, tarde: Habitual" })).toBeVisible();

  // También el nombre, escrito sin salir del campo antes de cambiar de pestaña.
  await page.locator('[data-medico="ANA"]').getByLabel("Nombre del médico").fill("Ana Ruiz Gil");
  await page.getByRole("link", { name: "Cobertura" }).click();
  await page.getByRole("link", { name: "Médicos y reglas" }).click();
  await expect(page.locator('[data-medico="ANA"]').getByLabel("Nombre del médico")).toHaveValue("Ana Ruiz Gil");
});

test("un médico nuevo conserva su disponibilidad aunque aún no tenga carga", async ({ page }) => {
  await page.goto(`/medicos?mes=${MES}`);
  await page.getByRole("button", { name: "Añadir médico" }).click();
  const nuevo = page.locator('[data-medico="NUEVO1"]');
  await expect(nuevo).toBeVisible();
  await nuevo.getByRole("button", { name: "Solo mañanas" }).click();
  await expect(nuevo.getByRole("button", { name: "Martes, tarde: No disponible" })).toBeVisible();
  await expect(nuevo.getByText(/Guardado/)).toBeVisible();
  await page.getByRole("link", { name: "Festivos" }).click();
  await page.getByRole("link", { name: "Médicos y reglas" }).click();
  const otraVez = page.locator('[data-medico="NUEVO1"]');
  await expect(otraVez.getByRole("button", { name: "Martes, tarde: No disponible" })).toBeVisible();
  // Después se le pone la carga y también se conserva.
  await otraVez.getByLabel("Turnos/mes mín.").fill("10");
  await otraVez.getByLabel("Turnos/mes máx.").fill("12");
  await page.getByRole("link", { name: "Cobertura" }).click();
  await page.getByRole("link", { name: "Médicos y reglas" }).click();
  await expect(page.locator('[data-medico="NUEVO1"]').getByLabel("Turnos/mes máx.")).toHaveValue("12");
  await expect(page.locator('[data-medico="NUEVO1"]').getByRole("button", { name: "Martes, tarde: No disponible" })).toBeVisible();
});

test("la cobertura persiste aunque se cambie de pestaña enseguida", async ({ page }) => {
  await page.goto(`/cobertura?mes=${MES}`);
  const viernes = page.getByLabel("Viernes, mañana, máximo");
  await expect(viernes).toHaveValue("1");
  await viernes.fill("3");
  await page.getByRole("link", { name: "Festivos" }).click();
  await expect(page.getByRole("heading", { name: /Festivos de/ })).toBeVisible();
  await page.getByRole("link", { name: "Cobertura" }).click();
  await expect(page.getByLabel("Viernes, mañana, máximo")).toHaveValue("3");
});

test("exportar, imprimir y copia de seguridad", async ({ page }) => {
  await page.goto(`/?mes=${MES}`);
  const [descarga] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "Exportar XLSX" }).click(),
  ]);
  expect(descarga.suggestedFilename()).toBe("turnos-2026-11.xlsx");

  await page.goto(`/imprimir?mes=${MES}`);
  await expect(page.getByRole("heading", { name: "Turnos — Noviembre de 2026" })).toBeVisible();
  await expect(page.getByText("BORRADOR — calendario no publicado")).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Mañana 08:00–15:00" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Turnos por médico — Noviembre de 2026" })).toBeVisible();

  // El calendario con el formato de la vista «Calendario», también para imprimir.
  await page.goto(`/?mes=${MES}`);
  await expect(page.getByRole("link", { name: "Imprimir calendario / PDF" })).toHaveAttribute(
    "href", `/imprimir/calendario?mes=${MES}&auto=1`);
  await expect(page.getByRole("link", { name: "Imprimir tabla / PDF" })).toHaveAttribute("href", `/imprimir?mes=${MES}&auto=1`);
  await page.goto(`/imprimir/calendario?mes=${MES}`);
  await expect(page.getByRole("heading", { name: "Turnos — Noviembre de 2026" })).toBeVisible();
  await expect(page.locator('[data-vista="cuadricula"] [data-ficha]').first()).toBeVisible();
  await expect(page.getByRole("group", { name: "Vista del calendario" })).toBeHidden();

  await page.goto(`/configuracion?mes=${MES}`);
  const [copia] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "Exportar copia de los datos" }).click(),
  ]);
  expect(copia.suggestedFilename()).toMatch(/^turnos-copia-\d{8}-\d{4}\.sqlite$/);
});

test("turno habitual: el panel del turno lo indica", async ({ page }) => {
  // Ana tiene el viernes por la tarde como habitual (prueba de las tarjetas): el panel
  // de ese turno lo indica.
  await page.goto(`/?mes=${MES}`);
  await page.getByRole("button", { name: "Regenerar" }).click();
  await expect(page.getByText("Borrador", { exact: true })).toBeVisible();
  await franja(page, "2026-11-13", "TARDE").getByRole("button").first().click();
  await expect(page.getByRole("dialog")).toContainText("Turno habitual");
  await page.keyboard.press("Escape");
});

test("pestañas: el mes se conserva y las direcciones antiguas redirigen", async ({ page }) => {
  await page.goto(`/cobertura?mes=2026-12`);
  await expect(page.locator("header output")).toHaveText("Diciembre 2026");
  await page.getByRole("link", { name: "Festivos" }).click();
  await expect(page).toHaveURL(/festivos\?mes=2026-12/);
  await expect(page.getByRole("heading", { name: "Festivos de 2026" })).toBeVisible();
  await page.getByRole("button", { name: "Mes siguiente" }).click();
  await expect(page.getByRole("heading", { name: "Festivos de 2027" })).toBeVisible();
  await expect(page.getByText(/Faltan festivos de 2027/)).toBeVisible();
  await page.goto("/ausencias");
  await expect(page).toHaveURL(/\/medicos$/);
});

test("avisa junto al botón de generar si hay médicos sin carga mensual", async ({ page, request }) => {
  const m = await (await request.post("/api/medicos", { data: { nombre: "Eva Sin Carga", codigo: "EVA" } })).json();
  await page.goto(`/?mes=${MES}`);
  const aviso = page.getByRole("alert").filter({ hasText: "no tiene carga mensual" });
  await expect(aviso).toContainText("1 médico no tiene carga mensual en noviembre de 2026");
  await expect(aviso).toContainText("Eva Sin Carga");
  await aviso.getByRole("link", { name: "Médicos y reglas" }).click();
  // En su tarjeta, los campos de carga aparecen resaltados.
  const tarjeta = page.locator('[data-medico="EVA"]');
  await expect(tarjeta.getByLabel("Turnos/mes mín.")).toHaveAttribute("data-resaltado", "");
  await request.put(`/api/medicos/${m.id}`, { data: { nombre: "Eva Sin Carga", codigo: "EVA", activo: false } });
});

test("color de cada médico: se elige en la tarjeta y se ve en el calendario", async ({ page }) => {
  await page.goto(`/medicos?mes=${MES}`);
  const tarjeta = page.locator('[data-medico="BEA"]');
  await tarjeta.getByRole("button", { name: /^Color de Bea Gil/ }).click();
  await page.getByRole("dialog", { name: "Elegir el color de Bea Gil" }).getByRole("button", { name: "Menta" }).click();
  await expect(tarjeta.getByRole("button", { name: "Color de Bea Gil: Menta" })).toBeVisible();
  await expect(tarjeta.getByLabel("Nombre del médico")).toHaveCSS("background-color", "rgb(143, 214, 181)");

  await page.getByRole("link", { name: /Calendario/ }).click();
  const fichas = page.locator('[data-celda] [title^="Bea Gil"]');
  await expect(fichas.first()).toHaveCSS("background-color", "rgb(143, 214, 181)");
  await expect(page.locator('table [data-ficha="Bea Gil"]')).toHaveCSS("background-color", "rgb(143, 214, 181)");
});

test("urgencias y domicilios: cada tarde, uno de cada, y se pueden cambiar a mano", async ({ page, request }) => {
  const cobertura = (tarde: number) =>
    request.put("/api/cobertura/semanal", {
      data: [0, 1, 2, 3, 4].flatMap((d) =>
        ["M1", "M2", "T1", "T2"].map((mitad) => {
          const n = mitad.startsWith("T") ? tarde : 1;
          return { dia_semana: d, mitad, minimo: n, maximo: n };
        }),
      ),
    });
  await cobertura(2);
  await page.goto(`/?mes=${MES}`);
  await page.getByRole("button", { name: "Volver a automático todo el mes" }).click();
  await page.getByRole("button", { name: "Regenerar" }).click();
  // (Las pruebas anteriores dejan a Ana con media tarde fija los martes: se usa un jueves.)
  const tarde = franja(page, "2026-11-12", "TARDE");
  await expect(tarde.getByRole("img", { name: "Urgencias" })).toHaveCount(1);
  await expect(tarde.getByRole("img", { name: "Domicilios" })).toHaveCount(1);

  // En el panel de la tarde, quien hace domicilios pasa a urgencias: se intercambian.
  const deDomicilios = (
    await tarde.locator("[data-ficha]").filter({ has: page.getByRole("img", { name: "Domicilios" }) }).getAttribute("title")
  )!.split(" · ")[0];
  await tarde.getByRole("button").first().click();
  const panel = page.getByRole("dialog");
  await expect(panel).toContainText("Urgencias:");
  const papel = panel.getByRole("group", { name: `Papel de ${deDomicilios}` });
  await papel.getByRole("button", { name: "Urgencias" }).click();
  await expect(papel.getByRole("button", { name: "Urgencias" })).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("Escape");
  await expect(
    tarde.locator("[data-ficha]").filter({ has: page.getByRole("img", { name: "Urgencias" }) }),
  ).toHaveAttribute("title", new RegExp(`^${deDomicilios}`));
  await expect(tarde.getByText("BLOQ.")).toBeVisible();

  // La tabla de carga cuenta las urgencias y los domicilios de cada médico.
  const filas = page.locator("table tbody tr");
  let total = 0;
  for (const fila of await filas.all()) total += Number(await fila.locator("td").nth(7).textContent());
  expect(total).toBe(20);

  // Informe de urgencias y domicilios: para imprimir y en XLSX.
  await page.goto(`/imprimir/urgencias-domicilios?mes=${MES}`);
  await expect(page.getByRole("heading", { name: "Urgencias y domicilios — Noviembre de 2026" })).toBeVisible();
  const jueves = page.getByRole("row", { name: /^Jueves 12 / });
  await expect(jueves.locator("td").first()).toHaveText(deDomicilios); // el cambio a mano
  await expect(page.getByRole("row", { name: /^Lunes 2 / })).toContainText("Festivo");
  let veces = 0;
  for (const fila of await page.locator("section tbody tr").all()) veces += Number(await fila.locator("td").last().textContent());
  expect(veces).toBe(40);
  const xlsx = await request.get("/api/periodos/2026/11/urgencias-domicilios.xlsx");
  expect(xlsx.ok()).toBe(true);
  expect(xlsx.headers()["content-disposition"]).toContain("urgencias-domicilios-2026-11.xlsx");
  await page.goto(`/?mes=${MES}`);
  await expect(page.getByRole("link", { name: "Imprimir urgencias y domicilios" })).toHaveAttribute(
    "href",
    `/imprimir/urgencias-domicilios?mes=${MES}&auto=1`,
  );

  await page.getByRole("button", { name: "Volver a automático todo el mes" }).click();
  await cobertura(1);
});

test("configuración: todos trabajan cada día", async ({ page, request }) => {
  await page.goto(`/configuracion?mes=${MES}`);
  const opcion = page.getByLabel("Todos los médicos trabajan cada día laborable");
  await expect(opcion).not.toBeChecked();
  await opcion.check();
  await expect(page.getByText("Ajuste guardado")).toBeVisible();
  expect((await (await request.get("/api/ajustes")).json()).todos_trabajan).toBe(true);

  // Con 1 médico por turno, que trabajen todos cada día choca con la cobertura máxima: se avisa.
  await page.getByRole("link", { name: /Calendario/ }).click();
  await page.getByRole("button", { name: "Regenerar" }).click();
  await expect(page.getByText(/Todos trabajan cada día: el lunes 9\/11 trabajan/)).toBeVisible();

  await page.getByRole("link", { name: "Configuración" }).click();
  await page.getByLabel("Todos los médicos trabajan cada día laborable").uncheck();
  await expect(page.getByText("Ajuste guardado")).toBeVisible();
  await page.getByRole("link", { name: /Calendario/ }).click();
  await page.getByRole("button", { name: "Regenerar" }).click();
  await expect(page.getByText(/Todos trabajan cada día/)).toHaveCount(0);
});

test("turnos rotativos: se definen en su subpestaña y alternan por semanas", async ({ page, request }) => {
  await page.goto(`/medicos?mes=${MES}`);
  await page.getByRole("link", { name: "Turnos rotativos" }).click();
  await expect(page.getByRole("link", { name: "Médicos y reglas" })).toHaveClass(/active/);
  await page.getByRole("button", { name: "Añadir turno rotativo" }).click();
  const tarjeta = page.locator("[data-rotacion]").last();
  await expect(tarjeta.getByLabel("Empieza la semana del")).toHaveValue("2026-11-02");
  await tarjeta.getByLabel("Nombre del turno rotativo").fill("Miércoles de mañana");
  await tarjeta.getByLabel("Añadir médico al turno rotativo").selectOption({ label: "Bea Gil" });
  await expect(tarjeta.getByText(/Incompleto/)).toBeVisible();
  await tarjeta.getByLabel("Añadir médico al turno rotativo").selectOption({ label: "Carlos Paz" });
  await tarjeta.getByRole("button", { name: "Miércoles, mañana" }).click();
  await expect(tarjeta.getByText("Guardado.")).toBeVisible();
  // Vista previa: semana del 2/11 → Bea; del 9/11 → Carlos.
  await expect(tarjeta.locator("li", { hasText: "Semana del 02/11" })).toContainText("Bea Gil");
  await expect(tarjeta.locator("li", { hasText: "Semana del 09/11" })).toContainText("Carlos Paz");

  // Persiste al cambiar de pestaña y se aplica al generar.
  await page.getByRole("link", { name: /Calendario/ }).click();
  await page.getByRole("button", { name: "Volver a automático todo el mes" }).click();
  // Esperar a que termine la regeneración (el estado «Borrador» ya se veía antes).
  await Promise.all([
    page.waitForResponse((r) => r.url().includes("/generar") && r.ok()),
    page.getByRole("button", { name: "Regenerar" }).click(),
  ]);
  const cal = await (await request.get("/api/periodos/2026/11")).json();
  const nombres = Object.fromEntries(cal.medicos.map((m: { id: number; nombre: string }) => [m.id, m.nombre]));
  const manana = (fecha: string) =>
    cal.asignaciones
      .filter((a: { fecha: string; mitad: string }) => a.fecha === fecha && a.mitad === "M1")
      .map((a: { medico_id: number }) => nombres[a.medico_id]);
  expect(manana("2026-11-04")).toContain("Bea Gil");
  expect(manana("2026-11-04")).not.toContain("Carlos Paz");
  expect(manana("2026-11-11")).toContain("Carlos Paz");
  expect(manana("2026-11-11")).not.toContain("Bea Gil");

  // Se quita para no afectar a otras pruebas.
  page.once("dialog", (d) => d.accept());
  await page.getByRole("link", { name: "Médicos y reglas" }).click();
  await page.getByRole("link", { name: "Turnos rotativos" }).click();
  await page.locator("[data-rotacion]").last().getByRole("button", { name: /^Borrar/ }).click();
  await expect(page.locator("[data-rotacion]")).toHaveCount(0);
});

test("configuración: urgencias y domicilios según la presencia (activada por defecto)", async ({ page, request }) => {
  await page.goto(`/configuracion?mes=${MES}`);
  const opcion = page.getByLabel("Urgencias y domicilios según la presencia de cada médico en el mes");
  await expect(opcion).toBeChecked();
  await opcion.uncheck();
  await expect(page.getByText("Ajuste guardado")).toBeVisible();
  const ajustes = await (await request.get("/api/ajustes")).json();
  expect(ajustes.roles_segun_presencia).toBe(false);
  expect(ajustes.todos_trabajan).toBe(false); // no cambia los demás ajustes
  await opcion.check();
  await expect(opcion).toBeChecked();
  await expect.poll(async () => (await (await request.get("/api/ajustes")).json()).roles_segun_presencia).toBe(true);
});

test("configuración: cuánto trabaja cada médico, según la presencia y sin rangos", async ({ page, request }) => {
  // Pase lo que pase, se deja como estaba (las demás pruebas usan rangos).
  try {
    await probarSegunLaPresencia(page, request);
  } finally {
    const ajustes = await (await request.get("/api/ajustes")).json(); // PUT sustituye todos: se cambia solo uno
    await request.put("/api/ajustes", { data: { ...ajustes, modo_carga: "RANGOS" } });
  }
});

async function probarSegunLaPresencia(page: Page, request: APIRequestContext) {
  await page.goto(`/configuracion?mes=${MES}`);
  const modo = page.getByLabel("Cuánto trabaja cada médico");
  await expect(modo).toHaveValue("RANGOS");
  await modo.selectOption("PRESENCIA");
  await expect.poll(async () => (await (await request.get("/api/ajustes")).json()).modo_carga).toBe("PRESENCIA");
  await expect(page.getByLabel("Todos los médicos trabajan cada día laborable")).toBeChecked();
  await expect(page.getByLabel("Todos los médicos trabajan cada día laborable")).toBeDisabled();

  // Las fichas ya no piden el rango de turnos al mes.
  await page.goto(`/medicos?mes=${MES}`);
  await expect(page.locator("[data-medico]").first()).toBeVisible();
  await expect(page.getByText("Turnos/mes mín.")).toHaveCount(0);

  // Al generar, todos trabajan cada día laborable; la carga, sin columna de rango.
  await page.goto(`/?mes=${MES}`);
  await Promise.all([
    page.waitForResponse((r) => r.url().includes("/generar") && r.ok()),
    page.getByRole("button", { name: /Regenerar|Generar calendario/ }).click(),
  ]);
  await expect(page.getByRole("columnheader", { name: "Total" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Rango" })).toHaveCount(0);
  await expect(page.getByText("Trabaja todos los días salvo ausencia", { exact: false })).toBeVisible();
  const cal = await (await request.get("/api/periodos/2026/11")).json();
  const laborables = cal.dias.filter((d: { festivo: string | null }) => !d.festivo).length;
  for (const m of cal.medicos.filter((m: { activo: boolean }) => m.activo)) {
    const dias = new Set(cal.asignaciones.filter((a: { medico_id: number }) => a.medico_id === m.id).map((a: { fecha: string }) => a.fecha));
    const ausentes = new Set(m.no_elegibles.filter((n: { motivo: string }) => n.motivo === "AUSENTE").map((n: { fecha: string }) => n.fecha));
    expect(dias.size).toBe(laborables - ausentes.size);
  }

  // Volver a los rangos desde la pantalla.
  await page.goto(`/configuracion?mes=${MES}`);
  await modo.selectOption("RANGOS");
  await expect.poll(async () => (await (await request.get("/api/ajustes")).json()).modo_carga).toBe("RANGOS");
  await expect(page.getByLabel("Todos los médicos trabajan cada día laborable")).toBeEnabled();
}

test("configuración: si no se pueden igualar las dos cosas, urgencias iguales (por defecto)", async ({ page, request }) => {
  await page.goto(`/configuracion?mes=${MES}`);
  const prioridad = page.getByLabel("Si no se pueden repartir las dos cosas por igual");
  await expect(prioridad).toHaveValue("URGENCIAS");
  await prioridad.selectOption("DOMICILIOS");
  await expect.poll(async () => (await (await request.get("/api/ajustes")).json()).prioridad_roles).toBe("DOMICILIOS");
  await page.reload();
  await expect(prioridad).toHaveValue("DOMICILIOS");
  await prioridad.selectOption("URGENCIAS"); // como estaba, para las demás pruebas
  await expect.poll(async () => (await (await request.get("/api/ajustes")).json()).prioridad_roles).toBe("URGENCIAS");
});
