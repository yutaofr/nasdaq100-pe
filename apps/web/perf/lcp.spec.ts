import { test, expect, chromium } from "@playwright/test";
import { writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";

const RUNS = 5;
const LCP_LIMIT_MS = 3000;
const TRANSFER_LIMIT = 500 * 1024;

test("约110条证券 · 研究页 LCP 与压缩传输", async () => {
  const browser = await chromium.launch({ channel: "chrome" });
  const version = browser.version();
  const results: { lcp: number; transferBytes: number }[] = [];
  for (let i = 0; i < RUNS; i++) {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, baseURL: "http://127.0.0.1:4174", serviceWorkers: "block" });
    const page = await ctx.newPage();
    const cdp = await ctx.newCDPSession(page);
    await cdp.send("Network.enable");
    await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
    await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 100, downloadThroughput: (10 * 1e6) / 8, uploadThroughput: (1 * 1e6) / 8 });
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
    let bytes = 0;
    cdp.on("Network.loadingFinished", (e: any) => { bytes += e.encodedDataLength; });
    await page.addInitScript(() => {
      (window as any).__lcp = 0;
      new PerformanceObserver((l) => { for (const e of l.getEntries()) (window as any).__lcp = e.startTime; }).observe({ type: "largest-contentful-paint", buffered: true });
    });
    await page.goto("/#/research");
    await page.getByRole("table", { name: "成分明细" }).waitFor();
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(800);
    await page.keyboard.press("Tab");   // 触发 LCP 定稿
    const lcp = await page.evaluate(() => (window as any).__lcp as number);
    const rows = await page.getByRole("table", { name: "成分明细" }).locator("tbody tr").count();
    expect(rows).toBeGreaterThanOrEqual(100);
    results.push({ lcp, transferBytes: bytes });
    await ctx.close();
  }
  await browser.close();
  const sorted = [...results].map((r) => r.lcp).sort((a, b) => a - b);
  const report = {
    generated_at: new Date().toISOString(), browser: version, viewport: "390x844", cpu_throttle: 4,
    network: "10Mbps down / 1Mbps up / 100ms RTT", securities: "约110（合成演示数据）", runs: results,
    lcp_median_ms: sorted[Math.floor(sorted.length / 2)], lcp_worst_ms: sorted[sorted.length - 1],
    transfer_worst_kib: Math.max(...results.map((r) => r.transferBytes)) / 1024,
    limits: { lcp_ms: LCP_LIMIT_MS, transfer_kib: TRANSFER_LIMIT / 1024 },
  };
  mkdirSync(path.resolve(process.cwd(), "../../docs/acceptance"), { recursive: true });
  writeFileSync(path.resolve(process.cwd(), "../../docs/acceptance/perf-results.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
  expect(report.lcp_worst_ms).toBeLessThanOrEqual(LCP_LIMIT_MS);
  expect(report.transfer_worst_kib * 1024).toBeLessThanOrEqual(TRANSFER_LIMIT);
});
