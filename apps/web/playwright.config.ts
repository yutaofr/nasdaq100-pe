import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: { baseURL: "http://127.0.0.1:4173", channel: "chrome" },
  webServer: {
    command: "../../.venv/bin/python ../../scripts/e2e_server.py 4173",
    url: "http://127.0.0.1:4173/healthz",
    reuseExistingServer: false,
    timeout: 30_000,
    env: { PYTHONPATH: "../../src" },
  },
});
