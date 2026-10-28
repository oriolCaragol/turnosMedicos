import { defineConfig } from "@playwright/test";

/**
 * Pruebas de flujo completo. Necesitan la aplicación arrancada con una base de
 * datos vacía (ver scripts/e2e.sh); la URL se indica con E2E_URL.
 * Usa el Chromium del sistema (CHROMIUM para otra ruta).
 */
export default defineConfig({
  testDir: "e2e",
  projects: [
    { name: "personal", testIgnore: /servidor\.spec/ },
    {
      // Modo servidor con HTTPS y su autoridad propia (el navegador de pruebas no la tiene instalada).
      name: "servidor",
      testMatch: /servidor\.spec/,
      use: { baseURL: process.env.E2E_URL_SERVIDOR ?? "https://localhost:8791", ignoreHTTPSErrors: true },
    },
  ],
  workers: 1,
  timeout: 30_000,
  reporter: "list",
  use: {
    baseURL: process.env.E2E_URL ?? "http://127.0.0.1:8790",
    locale: "es-ES",
    viewport: { width: 1400, height: 1000 },
    launchOptions: { executablePath: process.env.CHROMIUM ?? "/usr/bin/chromium-browser" },
    trace: "retain-on-failure",
  },
});
