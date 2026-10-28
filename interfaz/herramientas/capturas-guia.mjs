// Capturas de la guía de uso con un equipo ficticio (lo lanza scripts/capturas-guia.sh).
import { chromium } from "@playwright/test";

const [base, salida] = process.argv.slice(2);
const MES = "2026-11";

async function api(metodo, ruta, cuerpo) {
  const r = await fetch(base + "/api" + ruta, {
    method: metodo,
    headers: { "Content-Type": "application/json", "X-Cliente": "capturas" },
    body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
  });
  if (!r.ok) throw new Error(`${metodo} ${ruta}: ${r.status} ${await r.text()}`);
  return r.status === 204 ? null : r.json();
}

// --- Equipo ficticio -----------------------------------------------------------------
const EQUIPO = [
  ["Dr. Díaz", "DIA"], ["Dr. Gómez", "GOM"], ["Dr. López", "LOP"], ["Dr. Muñoz", "MUN"],
  ["Dr. Romero", "ROM"], ["Dr. Sánchez", "SAN"], ["Dra. García", "GAR"], ["Dra. Martín", "MAR"],
  ["Dra. Moreno", "MOR"], ["Dra. Pérez", "PER"], ["Dra. Ruiz", "RUI"], ["Dra. Álvarez", "ALV"],
];
const no = (turno) => [0, 1, 2, 3, 4].map((d) => ({ dia_semana: d, turno, valor: "NO_DISPONIBLE" }));
const ids = {};
for (const [nombre, codigo] of EQUIPO) ids[codigo] = (await api("POST", "/medicos", { nombre, codigo })).id;
const reglas = (codigo, extra = {}) =>
  api("PUT", `/medicos/${ids[codigo]}/reglas`, {
    vigente_desde: `${MES}-01`, elegibilidad: [], carga: { minimo: 24, maximo: 32 }, ...extra,
  });
for (const [, codigo] of EQUIPO) await reglas(codigo);
await reglas("GOM", { elegibilidad: no("MANANA") });
await reglas("SAN", { elegibilidad: no("TARDE") });
await reglas("MAR", { elegibilidad: no("TARDE") });
await reglas("PER", { elegibilidad: no("MANANA") });
await reglas("DIA", { jornadas: [{ dia_semana: 1, tipo: "MANANA_MAS_MEDIA" }] });
await reglas("GAR", { elegibilidad: [{ dia_semana: 0, turno: "MANANA", valor: "FIJO" }] });
await api("POST", "/ausencias", { medico_id: ids.LOP, desde: "2026-11-10", hasta: "2026-11-13" });
await api("POST", "/ausencias", { medico_id: ids.RUI, desde: "2026-11-23", hasta: "2026-11-30" });
const cobertura = [];
for (let d = 0; d < 5; d++)
  for (const mitad of ["M1", "M2", "T1", "T2"])
    cobertura.push({ dia_semana: d, mitad, minimo: mitad[0] === "M" ? 4 : 3, maximo: mitad[0] === "M" ? 4 : 4 });
await api("PUT", "/cobertura/semanal", cobertura);
await api("PUT", "/ajustes", { todos_trabajan: false });

// --- Capturas --------------------------------------------------------------------------
const navegador = await chromium.launch({ executablePath: process.env.CHROMIUM ?? "/usr/bin/chromium-browser" });
const contexto = await navegador.newContext({ viewport: { width: 1280, height: 900 }, locale: "es-ES" });
const page = await contexto.newPage();
const foto = async (nombre, opciones = {}) => {
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${salida}/${nombre}.png`, ...opciones });
  console.log(nombre);
};
const recorte = (caja, ancho = 1280, alto) => ({ clip: { x: caja.x, y: caja.y, width: ancho, height: alto } });

await page.goto(`${base}/?mes=${MES}`);
await page.getByText("Sin generar", { exact: true }).waitFor();
await page.setViewportSize({ width: 1280, height: 560 });
await foto("calendario-sin-generar");
await page.setViewportSize({ width: 1280, height: 900 });

await page.getByRole("button", { name: "Generar calendario" }).click();
await page.getByText("Borrador", { exact: true }).waitFor();
// Un cambio a mano: quitar a alguien de la tarde del miércoles 4 (queda bloqueado y falta uno).
const tarde4 = page.locator('[data-celda="2026-11-04-TARDE"]');
const ficha = tarde4.locator("[data-ficha]").first();
const a = await ficha.boundingBox();
await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
await page.mouse.down();
await page.mouse.move(a.x + 20, a.y, { steps: 3 });
await page.mouse.move(640, 20, { steps: 10 });
await page.mouse.up();
await page.getByText("BLOQ.").first().waitFor();
await page.mouse.move(0, 0);
await foto("calendario");

// Arrastrar: a mitad de un arrastre, con los turnos donde encaja resaltados.
const semana = page.locator('[data-celda="2026-11-10-MANANA"]');
await semana.scrollIntoViewIfNeeded();
const origen = semana.locator("[data-ficha]").nth(1);
const o = await origen.boundingBox();
await page.mouse.move(o.x + o.width / 2, o.y + o.height / 2);
await page.mouse.down();
await page.mouse.move(o.x + 30, o.y - 10, { steps: 5 });
await page.mouse.move(o.x + 10, o.y - 12, { steps: 5 });
const fila = await page.locator('[id="dia-2026-11-09"]').boundingBox();
await foto("arrastrar", { clip: { x: fila.x - 6, y: fila.y - 4, width: 1160, height: 420 } });
await page.keyboard.press("Escape");
await page.mouse.up();

// Problemas a resolver y carga por médico.
const columnas = page.locator(".dos-columnas").first();
await columnas.scrollIntoViewIfNeeded();
const c = await columnas.boundingBox();
await foto("problemas-carga", { clip: { x: 0, y: c.y - 4, width: 1280, height: 481 } });

// Panel de un turno.
await page.evaluate(() => window.scrollTo(0, 0));
await page.locator('[data-celda="2026-11-05-MANANA"] button').first().click();
await page.getByRole("button", { name: "Hecho" }).waitFor();
await foto("panel-turno");
await page.getByRole("button", { name: "Hecho" }).click();

// Vista en lista.
await page.getByRole("button", { name: "Lista" }).click();
const lista = await page.locator('[data-vista="lista"]').boundingBox();
await page.evaluate((y) => window.scrollTo(0, y - 60), lista.y);
await page.setViewportSize({ width: 1280, height: 520 });
await foto("vista-lista");
await page.setViewportSize({ width: 1280, height: 900 });
await page.getByRole("button", { name: "Cuadrícula" }).click();

// Médicos y reglas; color; más reglas.
await page.goto(`${base}/medicos?mes=${MES}`);
await page.locator("[data-medico]").first().waitFor();
await foto("medicos");
for (const [codigo, n] of [["DIA", 0], ["GOM", 1]]) {
  await page.locator(`[data-medico="${codigo}"]`).getByRole("button", { name: /^Color de/ }).click();
  await page.getByRole("dialog", { name: /Elegir el color/ }).locator("button").nth(n).click();
}
await page.locator('[data-medico="LOP"]').getByRole("button", { name: /^Color de/ }).click();
await page.getByRole("dialog", { name: /Elegir el color/ }).locator("button").nth(2).click();
await page.locator('[data-medico="LOP"]').getByRole("button", { name: /^Color de/ }).click();
const tarjetas = await page.locator("[data-medico]").first().boundingBox();
await foto("color-medico", { clip: { x: 0, y: tarjetas.y - 40, width: 1280, height: 420 } });
await page.keyboard.press("Escape");
await page.goto(`${base}/medicos?mes=${MES}`);
await page.locator('[data-medico="DIA"]').getByRole("button", { name: "Más reglas…" }).click();
await page.waitForTimeout(300);
await foto("mas-reglas");

// Turnos rotativos.
await api("POST", "/rotaciones", {
  nombre: "Lunes de tarde", desde: `${MES}-02`, medicos: [ids.MUN, ids.ROM, ids.MOR],
  huecos: [{ dia_semana: 0, turno: "TARDE" }],
});
await page.goto(`${base}/medicos/rotaciones?mes=${MES}`);
await page.getByLabel("Nombre del turno rotativo").first().waitFor();
await foto("turnos-rotativos");

// Cobertura y festivos.
await page.goto(`${base}/cobertura?mes=${MES}`);
await page.waitForTimeout(500);
await page.setViewportSize({ width: 1280, height: 700 });
await foto("cobertura");
await page.goto(`${base}/festivos?mes=${MES}`);
await page.setViewportSize({ width: 1280, height: 600 });
await page.waitForTimeout(500);
await foto("festivos");

// Para imprimir.
await page.goto(`${base}/imprimir?mes=${MES}`);
await page.setViewportSize({ width: 1280, height: 560 });
await page.waitForTimeout(500);
await foto("imprimir");

await navegador.close();
