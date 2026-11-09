import { test, expect } from "@playwright/test";

const VIEWPORTS = [320, 390, 768, 1440];

for (const route of ["/", "/#/research"]) {
  for (const w of VIEWPORTS) {
    test(`验收：${route} @${w} 无横向溢出且无估值红绿/买卖信号`, async ({ page }) => {
      await page.setViewportSize({ width: w, height: 900 });
      await page.goto(route);
      await page.waitForLoadState("networkidle");
      expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
      const text = await page.locator("body").innerText();
      for (const bad of ["买入", "卖出", "百分位", "低估", "高估"]) expect(text).not.toContain(bad);
    });
  }
}

test("验收：仅键盘走通 引用→研究→排序→返回，焦点始终可见", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "自主计算研究" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: /观察时点研究/ })).toBeVisible();
  const sortBtn = page.getByRole("button", { name: "按 权重 排序" });
  await sortBtn.focus();
  const outline = await sortBtn.evaluate((e) => getComputedStyle(e).outlineStyle);
  expect(outline).not.toBe("none");
  await page.keyboard.press("Enter");
  await page.getByRole("link", { name: "整体估值参考" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: /滚动 PE/ })).toBeVisible();
});

test("验收：服务只读（写方法被拒）且无 CORS 放开", async ({ request }) => {
  for (const m of ["post", "put", "delete"] as const) {
    const r = await request[m]("/api/current");
    expect(r.status()).toBe(405);
  }
  const g = await request.get("/healthz");
  expect(g.headers()["access-control-allow-origin"]).toBeUndefined();
  const bad = await request.get("/healthz", { headers: { Host: "evil.example" } });
  expect(bad.status()).toBe(403);
});

test("验收：目录穿越与私有路径不可读", async ({ request }) => {
  for (const p of ["/..%2f..%2fetc/passwd", "/%2e%2e/%2e%2e/etc/passwd", "/raw/x", "/index.sqlite"]) {
    const r = await request.get(p);
    const body = await r.text();
    expect(body).not.toContain("root:");
    expect(body.toLowerCase()).not.toContain("sqlite format");
  }
});

test("验收：研究页首屏只取当前发布文件，无第三方请求", async ({ page }) => {
  const urls: string[] = [];
  page.on("request", (r) => urls.push(new URL(r.url()).pathname));
  await page.goto("/#/research");
  await page.waitForLoadState("networkidle");
  expect(urls.filter((u) => u.startsWith("/releases/")).every((u) => /^\/releases\/[0-9a-f]{16}\/(manifest|observations|method|status|checks|research)\.json$/.test(u))).toBe(true);
  expect(urls.some((u) => /analytics|gtag|fonts/.test(u))).toBe(false);
});
