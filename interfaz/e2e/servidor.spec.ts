import { expect, test, type Browser, type Page } from "@playwright/test";

/**
 * Modo servidor con HTTPS (diseño del modo servidor, 6 y 10): entrar, cuentas con
 * contraseña temporal, un médico desde el móvil, dispositivos conectados y copias.
 * scripts/e2e.sh arranca el servidor con el administrador «admin».
 */

const MOVIL = {
  viewport: { width: 390, height: 844 },
  isMobile: true,
  hasTouch: true,
  userAgent:
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
};

async function entrar(page: Page, usuario: string, contrasena: string) {
  await page.goto("/");
  await page.getByLabel("Usuario").fill(usuario);
  await page.getByLabel("Contraseña").fill(contrasena);
  await page.getByRole("button", { name: "Entrar" }).click();
}

async function nuevoContexto(browser: Browser, opciones = {}) {
  const contexto = await browser.newContext({ ignoreHTTPSErrors: true, ...opciones });
  return { contexto, page: await contexto.newPage() };
}

/** Crea una cuenta desde Administración y devuelve su contraseña temporal. */
async function crearCuenta(page: Page, rol: "Médico" | "Planificador", nombre: string, usuario: string, ficha?: string) {
  await page.getByRole("link", { name: "Administración" }).click();
  const formulario = page.locator("form", { has: page.getByRole("button", { name: "Crear cuenta" }) });
  await formulario.getByLabel("Rol").selectOption({ label: rol });
  if (ficha) await formulario.getByLabel("Ficha del médico").selectOption({ label: ficha });
  await formulario.getByLabel("Nombre visible").fill(nombre);
  await formulario.getByLabel("Usuario").fill(usuario);
  await formulario.getByRole("button", { name: "Crear cuenta" }).click();
  const temporal = (await page.locator("[data-temporal]").textContent())!.trim();
  await page.getByRole("button", { name: "Hecho" }).click();
  return temporal;
}

test("entrar, cuentas, un médico en el móvil y dispositivos conectados", async ({ page, browser }) => {
  // Sin sesión: la página de entrada, con las instrucciones del certificado.
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Entrar" })).toBeVisible();
  await expect(page.getByText("¿El navegador avisa de que la conexión no es segura?")).toBeVisible();
  await entrar(page, "admin", "mala-contrasena");
  await expect(page.getByText("Usuario o contraseña incorrectos.")).toBeVisible();
  await entrar(page, "admin", "contrasena-admin");
  await expect(page.locator("header output")).toBeVisible();
  await expect(page.getByRole("link", { name: "Administración" })).toBeVisible();

  // Una ficha de médico para vincularle la cuenta (por la API, con la sesión de la página).
  const r = await page.request.post("/api/medicos", {
    data: { nombre: "Ana Ruiz", codigo: "ANA" },
    headers: { "X-Cliente": "e2e" },
  });
  expect(r.status()).toBe(201);
  // Sin la cabecera de la aplicación, se rechaza (CSRF).
  expect((await page.request.post("/api/medicos", { data: { nombre: "X", codigo: "X" } })).status()).toBe(403);

  const temporal = await crearCuenta(page, "Médico", "Ana Ruiz", "ana", "Ana Ruiz");
  await expect(page.locator('[data-usuario="ana"]')).toContainText("Contraseña temporal");

  // Ana entra desde el móvil con la temporal y elige la suya.
  const movil = await nuevoContexto(browser, MOVIL);
  await entrar(movil.page, "ana", temporal);
  await expect(movil.page.getByRole("heading", { name: "Hola, Ana Ruiz: elige tu contraseña" })).toBeVisible();
  await movil.page.getByLabel("Contraseña temporal").fill(temporal);
  await movil.page.getByLabel("Contraseña nueva (8 caracteres o más)").fill("la-de-ana-1");
  await movil.page.getByLabel("Repite la contraseña nueva").fill("la-de-ana-1");
  await movil.page.getByRole("button", { name: "Guardar contraseña" }).click();
  await expect(movil.page.getByRole("heading", { name: "Aún no hay calendarios publicados" })).toBeVisible();
  // La página cabe en el móvil sin desplazarse a lo ancho.
  expect(await movil.page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);

  // El administrador ve el iPhone entre los dispositivos y cierra su sesión.
  await page.reload();
  const fila = page.locator("tr", { hasText: "Safari en iPhone" });
  await expect(fila).toBeVisible();
  await fila.getByRole("button", { name: "Cerrar sesión" }).click();
  await expect(fila).toHaveCount(0);
  await movil.page.reload();
  await expect(movil.page.getByRole("heading", { name: "Entrar" })).toBeVisible();
  await entrar(movil.page, "ana", "la-de-ana-1");
  await expect(movil.page.getByRole("heading", { name: "Aún no hay calendarios publicados" })).toBeVisible();
  await movil.contexto.close();

  // Un planificador: trabaja, pero sin Administración.
  const temporalPlani = await crearCuenta(page, "Planificador", "Pablo Planificador", "pablo");
  const pc = await nuevoContexto(browser);
  await entrar(pc.page, "pablo", temporalPlani);
  await pc.page.getByLabel("Contraseña temporal").fill(temporalPlani);
  await pc.page.getByLabel("Contraseña nueva (8 caracteres o más)").fill("la-de-pablo");
  await pc.page.getByLabel("Repite la contraseña nueva").fill("la-de-pablo");
  await pc.page.getByRole("button", { name: "Guardar contraseña" }).click();
  await expect(pc.page.getByRole("navigation").getByRole("link", { name: "Médicos y reglas" })).toBeVisible();
  await expect(pc.page.getByRole("link", { name: "Administración" })).toHaveCount(0);
  await expect(pc.page.getByText("Pablo Planificador")).toBeVisible();
  await pc.page.getByRole("button", { name: "Salir" }).click();
  await expect(pc.page.getByRole("heading", { name: "Entrar" })).toBeVisible();
  await pc.contexto.close();
});

test("servidor: direcciones con QR, certificado y copia inmediata", async ({ page }) => {
  await entrar(page, "admin", "contrasena-admin");
  await page.getByRole("link", { name: "Administración" }).click();
  const qr = page.getByRole("img", { name: /Código QR de https:\/\/turnos\.local:/ });
  await expect(qr).toBeVisible();
  await expect.poll(() => qr.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
  await expect(page.getByText(/Huella \(SHA-256\)/)).toBeHidden(); // dentro del desplegable
  await page.getByText("¿El navegador avisa de que la conexión no es segura?").click();
  await expect(page.getByText(/Huella \(SHA-256\)/)).toBeVisible();
  // El perfil para iPhone se descarga sin sesión.
  const perfil = await page.request.get("/certificado/turnos.mobileconfig");
  expect(perfil.headers()["content-type"]).toContain("application/x-apple-aspen-config");

  await page.getByRole("button", { name: "Hacer una copia ahora" }).click();
  await expect(page.getByRole("status").filter({ hasText: /Copia hecha: turnos-\d{8}-\d{6}\.sqlite/ })).toBeVisible();
});

test("cambiar la propia contraseña desde la cabecera", async ({ page, browser }) => {
  await entrar(page, "admin", "contrasena-admin");
  await page.getByRole("link", { name: "Contraseña" }).click();
  await page.getByLabel("Contraseña actual").fill("contrasena-admin");
  await page.getByLabel("Contraseña nueva (8 caracteres o más)").fill("nueva-del-admin");
  await page.getByLabel("Repite la contraseña nueva").fill("otra-cosa");
  await expect(page.getByText("Las dos contraseñas nuevas no coinciden.")).toBeVisible();
  await page.getByLabel("Repite la contraseña nueva").fill("nueva-del-admin");
  await page.getByRole("button", { name: "Guardar contraseña" }).click();
  await expect(page.getByText("Contraseña cambiada")).toBeVisible();
  // Con la nueva se entra; se deja como estaba para las demás pruebas.
  const otro = await nuevoContexto(browser);
  await entrar(otro.page, "admin", "nueva-del-admin");
  await expect(otro.page.getByRole("link", { name: "Administración" })).toBeVisible();
  const r = await otro.page.request.post("/api/yo/contrasena", {
    data: { actual: "nueva-del-admin", nueva: "contrasena-admin" },
    headers: { "X-Cliente": "e2e" },
  });
  expect(r.status()).toBe(204);
  await otro.contexto.close();
});

test("un médico ve en el móvil sus turnos, el calendario del equipo y su ficha", async ({ page, browser }) => {
  // El administrador prepara noviembre con dos médicos (Ana ya existe y tiene cuenta).
  await entrar(page, "admin", "contrasena-admin");
  await expect(page.getByRole("link", { name: "Administración" })).toBeVisible();
  const api = async (metodo: "post" | "put", ruta: string, data?: unknown) => {
    const r = await page.request[metodo](ruta, { data, headers: { "X-Cliente": "e2e" } });
    expect(r.ok(), `${metodo} ${ruta}: ${await r.text()}`).toBeTruthy();
    return r.json().catch(() => null);
  };
  const medicos = await (await page.request.get("/api/medicos")).json();
  const ana = medicos.find((m: { nombre: string }) => m.nombre === "Ana Ruiz");
  const bea = await api("post", "/api/medicos", { nombre: "Bea Gil", codigo: "BEA" });
  for (const m of [ana, bea])
    await api("put", `/api/medicos/${m.id}/reglas`, {
      vigente_desde: "2026-11-01",
      elegibilidad: m === ana ? [{ dia_semana: 0, turno: "TARDE", valor: "NO_DISPONIBLE" }] : [],
      carga: { minimo: 0, maximo: 40 },
    });
  const cobertura = [];
  for (let d = 0; d < 5; d++) for (const mitad of ["M1", "M2", "T1", "T2"]) cobertura.push({ dia_semana: d, mitad, minimo: 1, maximo: 1 });
  await api("put", "/api/cobertura/semanal", cobertura);
  await api("put", "/api/ajustes", { todos_trabajan: false });
  await api("post", "/api/periodos/2026/11/generar", {});

  // Ana entra en el móvil: aún no hay nada publicado.
  const movil = await nuevoContexto(browser, MOVIL);
  const m = movil.page;
  await entrar(m, "ana", "la-de-ana-1");
  await expect(m.getByRole("heading", { name: "Aún no hay calendarios publicados" })).toBeVisible();
  // Su ficha no depende de que haya meses publicados: ve sus reglas (desde noviembre),
  // no las de hoy, que aún no existen (fallo encontrado probando con un médico real).
  await m.getByRole("link", { name: "Mi ficha" }).click();
  await expect(m.getByRole("button", { name: "Lunes, tarde: No disponible" })).toBeVisible();
  await expect(m.getByText("Entre 0 y 20 turnos al mes")).toBeVisible();
  await m.getByRole("link", { name: "Mis turnos" }).click();
  // El planificador ve que, en borrador, los médicos aún no lo ven.
  await page.goto("/?mes=2026-11");
  await expect(page.locator("[data-aviso-borrador]")).toHaveText("Los médicos no lo ven hasta que se publique");

  // Se publica y lo ve sin recargar.
  await api("post", "/api/periodos/2026/11/publicar");
  await expect(m.getByRole("heading", { name: "Mis turnos" })).toBeVisible();
  await expect(m.getByLabel("Mes")).toHaveValue("2026-11");
  const dias = m.locator("[data-dia]");
  expect(await dias.count()).toBeGreaterThan(5);
  await expect(dias.first()).toContainText(/Mañana|Tarde/);
  expect(await m.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);

  // Calendario del equipo, con el mismo formato que el del planificador: su nombre
  // resaltado, el festivo autonómico del 2, y solo para consultar (sin panel del turno).
  await m.getByRole("link", { name: "Calendario", exact: true }).click();
  await expect(m.getByRole("heading", { name: "Calendario del equipo" })).toBeVisible();
  await expect(m.locator('[data-vista="cuadricula"]')).toBeVisible();
  await expect(m.getByText("Traslado de Todos los Santos")).toBeVisible();
  const suyas = m.locator('[data-ficha^="Ana Ruiz"]');
  await expect(suyas.first()).toBeVisible();
  expect(await suyas.first().evaluate((e) => getComputedStyle(e).fontWeight)).toBe("700");
  expect(await m.locator('[data-ficha^="Bea Gil"]').first().evaluate((e) => getComputedStyle(e).fontWeight)).not.toBe("700");
  await m.locator("[data-celda]").first().click();
  await expect(m.getByRole("button", { name: "Hecho" })).toHaveCount(0);
  await expect(m.getByText("BLOQ.")).toHaveCount(0);
  // Para imprimir, el mismo calendario.
  await m.goto("/imprimir/calendario?mes=2026-11");
  await expect(m.getByRole("heading", { name: "Turnos — Noviembre de 2026" })).toBeVisible();
  await expect(m.locator('[data-vista="cuadricula"] [data-ficha^="Ana Ruiz"]').first()).toBeVisible();
  await m.goto("/equipo?mes=2026-11");

  // Su ficha: el lunes por la tarde no está disponible; no se puede cambiar.
  await m.getByRole("link", { name: "Mi ficha" }).click();
  const celda = m.getByRole("button", { name: "Lunes, tarde: No disponible" });
  await expect(celda).toBeVisible();
  await celda.click({ force: true }); // está deshabilitada: no cambia
  await expect(m.getByRole("button", { name: "Lunes, tarde: No disponible" })).toBeVisible();
  await expect(m.getByText("Entre 0 y 20 turnos al mes")).toBeVisible();

  // Sin pestañas de planificador, y la API le niega cambiar nada.
  await expect(m.getByRole("link", { name: "Médicos y reglas" })).toHaveCount(0);
  const r = await m.request.post("/api/periodos/2026/11/reabrir", { headers: { "X-Cliente": "e2e" } });
  expect(r.status()).toBe(403);
  await movil.contexto.close();
});

test("aplicación instalable: manifiesto e iconos", async ({ page }) => {
  const r = await page.request.get("/manifest.webmanifest");
  expect(r.headers()["content-type"]).toContain("application/manifest+json");
  const manifiesto = await r.json();
  expect(manifiesto.display).toBe("standalone");
  for (const icono of manifiesto.icons) expect((await page.request.get(icono.src)).ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveAttribute("href", "/icono-apple-180.png");
});

test("solicitudes: el médico pide desde el móvil y el planificador decide desde el PC", async ({ page, browser }) => {
  const movil = await nuevoContexto(browser, MOVIL);
  const m = movil.page;
  await entrar(m, "ana", "la-de-ana-1");
  await expect(m.getByRole("heading", { name: "Mis turnos" })).toBeVisible();

  // Pide una ausencia desde «Mi ficha».
  await m.getByRole("link", { name: "Mi ficha" }).click();
  await m.getByRole("button", { name: "Pedir una ausencia" }).click();
  await m.getByLabel("Desde").fill("2026-12-02");
  await m.getByLabel("Hasta").fill("2026-12-03");
  await m.getByLabel("Comentario (opcional)").fill("Curso de formación");
  await m.getByRole("button", { name: "Pedir la ausencia" }).click();
  await expect(m.getByText("Ausencia pedida")).toBeVisible();
  await m.getByRole("link", { name: "Solicitudes" }).click();
  const suya = m.locator("[data-solicitud]").first();
  await expect(suya).toContainText("Ausencia del mié 2/12 al jue 3/12 (día completo)");
  await expect(suya).toContainText("Pendiente");

  // El planificador (aquí, el administrador) la ve con el contador y la aprueba.
  await entrar(page, "admin", "contrasena-admin");
  const pestana = page.getByRole("navigation").getByRole("link", { name: /Solicitudes/ });
  await expect(pestana).toContainText("1");
  await pestana.click();
  const tarjeta = page.locator('[data-estado="PENDIENTE"]').first();
  await expect(tarjeta).toContainText("Ana Ruiz");
  await expect(tarjeta).toContainText("«Curso de formación»");
  await expect(tarjeta.locator("[data-efectos]")).toBeVisible();
  await tarjeta.getByLabel("Comentario para el médico").fill("De acuerdo");
  await tarjeta.getByRole("button", { name: "Aprobar" }).click();
  await expect(page.getByText("No hay solicitudes pendientes.")).toBeVisible();

  // Ana lo ve en vivo, y la ausencia ya está en su ficha.
  await expect(suya).toContainText("Aprobada");
  await expect(suya).toContainText("«De acuerdo»");
  await m.getByRole("link", { name: "Mi ficha" }).click();
  await expect(m.getByText(/hasta el jue,? 3 dic · día completo/)).toBeVisible();

  // Propone no hacer un turno de noviembre (publicado); el planificador lo rechaza con un motivo.
  await m.getByRole("link", { name: "Mis turnos" }).click();
  await m.locator("[data-dia]").first().getByRole("button", { name: "Proponer un cambio" }).click();
  await m.getByRole("button", { name: "Enviar la propuesta" }).click();
  await expect(m.getByText("Solicitud enviada")).toBeVisible();
  await pestana.click();
  const otra = page.locator('[data-estado="PENDIENTE"]').first();
  await expect(otra).toContainText("No puede hacer la");
  await expect(otra.locator("[data-efectos]")).toContainText("falta 1 médico");
  await otra.getByLabel("Comentario para el médico").fill("No hay quien te cubra ese día");
  await otra.getByRole("button", { name: "Rechazar" }).click();
  await m.getByRole("link", { name: "Solicitudes" }).click();
  await expect(m.locator('[data-estado="RECHAZADA"]')).toContainText("No hay quien te cubra ese día");
  await movil.contexto.close();
});
