import { test, expect } from "@playwright/test";

test("引用首页：卡片、演示标识、历史", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("本机个人使用")).toBeVisible();
  await expect(page.getByText("演示数据")).toBeVisible();
  await expect(page.getByRole("region", { name: /滚动 PE/ })).toContainText("30.55");
  await expect(page.getByRole("region", { name: /Forward PE/ })).toContainText("来源未注明，观察于");
  await page.getByText("观察历史（2）").click();
  await expect(page.getByRole("table", { name: /历史/ })).toBeVisible();
});

for (const w of [320, 390, 768, 1440]) {
  test(`无横向溢出 @${w}`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: 800 });
    await page.goto("/");
    await page.getByText("观察历史（2）").click();
    const over = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    expect(over).toBe(false);
  });
}

test("键盘可达导航且焦点可见", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  const outline = await page.evaluate(() => getComputedStyle(document.activeElement!).outlineStyle);
  expect(outline).not.toBe("none");
  await page.getByRole("link", { name: "自主计算研究" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: /观察时点研究/ })).toBeVisible();
});

test("无第三方请求", async ({ page }) => {
  const hosts = new Set<string>();
  page.on("request", (r) => hosts.add(new URL(r.url()).host));
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  expect([...hosts]).toEqual(["127.0.0.1:4173"]);
});

test("研究入口不影响引用首页", async ({ page }) => {
  await page.goto("/#/research");
  await page.getByRole("link", { name: "整体估值参考" }).click();
  await expect(page.getByRole("region", { name: /滚动 PE/ })).toBeVisible();
});
