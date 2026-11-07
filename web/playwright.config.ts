import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run against the real backend: `commanderai serve` (FastAPI)
// serving the built UI (web/dist) and the bundled offline catalog.
const PORT = Number(process.env.E2E_PORT ?? 8765);
const ROOT = new URL("..", import.meta.url).pathname;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1, // tests share one server and database
  reporter: [["list"]],
  timeout: 45_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "tablet",
      use: { ...devices["Desktop Chrome"], viewport: { width: 834, height: 1112 }, hasTouch: true },
    },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    // Fresh database and decks folder on every run → deterministic tests.
    command: `rm -rf ${ROOT}web/test-results/e2e-data && mkdir -p ${ROOT}web/test-results/e2e-data && ${ROOT}.venv/bin/commanderai serve --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/api/status`,
    reuseExistingServer: false,
    timeout: 60_000,
    env: {
      COMMANDERAI_CACHE: `${ROOT}offline-data`,
      COMMANDERAI_COLLECTION: `${ROOT}commanderai-sample/expanded-collection.txt`,
      COMMANDERAI_DECKS_DIR: `${ROOT}web/test-results/e2e-data/decks`,
      COMMANDERAI_DB: `${ROOT}web/test-results/e2e-data/e2e.db`,
      COMMANDERAI_OFFLINE: "1",
      ANTHROPIC_API_KEY: "",
    },
  },
});
