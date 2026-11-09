import { test, expect } from "@playwright/test";

test("研究页：标识、概览顺序、明细与筛选", async ({ page }) => {
  await page.goto("/#/research");
  await expect(page.getByRole("heading", { name: /观察时点研究/ })).toBeVisible();
  await expect(page.getByText("演示数据")).toBeVisible();
  await expect(page.getByText("非同步周度观察")).toBeVisible();
  const order = await page.locator("[data-overview]").evaluateAll((els) => els.map((e) => e.getAttribute("data-overview")));
  expect(order).toEqual(["count", "marketcap", "ttm-yield", "fy1-yield", "ttm-pe", "fy1-pe"]);
  await expect(page.getByTestId("status-ttm")).toContainText("部分覆盖");
  const total = await page.getByRole("table", { name: "成分明细" }).locator("tbody tr").count();
  await page.getByRole("button", { name: /筛选行业 医疗/ }).click();
  expect(await page.getByRole("table", { name: "成分明细" }).locator("tbody tr").count()).toBeLessThan(total);
  await page.getByRole("button", { name: "清除行业筛选" }).click();
  expect(await page.getByRole("table", { name: "成分明细" }).locator("tbody tr").count()).toBe(total);
});

for (const w of [320, 390, 768, 1440]) {
  test(`研究页无横向溢出 @${w}`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: 800 });
    await page.goto("/#/research");
    await expect(page.getByRole("heading", { name: /观察时点研究/ })).toBeVisible();
    const over = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    expect(over).toBe(false);
  });
}

test("概览列数：≥360 两列，<360 单列", async ({ page }) => {
  const cols = async () => page.locator(".ogrid").evaluate((e) => getComputedStyle(e).gridTemplateColumns.split(" ").length);
  await page.setViewportSize({ width: 390, height: 800 }); await page.goto("/#/research");
  await expect(page.locator(".ogrid")).toBeVisible(); expect(await cols()).toBe(2);
  await page.setViewportSize({ width: 320, height: 800 }); expect(await cols()).toBe(1);
});

test("键盘排序明细并保持焦点", async ({ page }) => {
  await page.goto("/#/research");
  const btn = page.getByRole("button", { name: "按 TTM PE 排序" });
  await btn.focus(); await page.keyboard.press("Enter");
  await expect(btn).toBeFocused();
  await expect(page.locator("th[aria-sort]")).toHaveAttribute("aria-sort", "ascending");
});

test("研究与引用同站共存", async ({ page }) => {
  await page.goto("/#/research");
  await page.getByRole("link", { name: "整体估值参考" }).click();
  await expect(page.getByRole("region", { name: /滚动 PE/ })).toBeVisible();
});
