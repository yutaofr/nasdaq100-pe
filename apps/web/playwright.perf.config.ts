import { defineConfig } from "@playwright/test";

// 性能验收：约110条合成证券；固定 Chrome（版本写入报告）；390×844；冷缓存；4×CPU 降速；10Mbps/1Mbps/100ms RTT
export default defineConfig({
  testDir: "./perf",
  timeout: 120_000,
  workers: 1,
  use: { baseURL: "http://127.0.0.1:4174", channel: "chrome" },
  webServer: {
    command: "../../.venv/bin/python ../../scripts/e2e_server.py 4174",
    url: "http://127.0.0.1:4174/healthz",
    reuseExistingServer: false,
    timeout: 60_000,
    env: { PYTHONPATH: "../../src", E2E_N: "110" },
  },
});
