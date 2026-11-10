import { render, screen, within, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../App";
import { loaderFor, ob, rel, series } from "../testFixtures";
import type { Loader } from "../data/ReleaseProvider";

const NOW = new Date("2026-11-09T00:00:00Z");
const both = () => rel("r1", [
  series([ob()]),
  series([ob({ observation_id: "f1", provider: "StockAnalysis", metric_kind: "forward_pe", metric_label_original: "Forward PE", value: "27.10", source_as_of: null })]),
]);

beforeEach(() => { window.location.hash = "#/reference"; });

function renderApp(loader: Loader, now = NOW) { return render(<App loader={loader} now={now} />); }

describe("整体估值参考", () => {
  it("滚动与Forward各自独立卡片并显示来源/原名/日期/口径", async () => {
    renderApp(loaderFor(both()));
    const t = await screen.findByRole("region", { name: /滚动 PE/ });
    expect(within(t).getByText("Invesco")).toBeInTheDocument();
    expect(within(t).getByText("P/E (TTM)")).toBeInTheDocument();
    expect(within(t).getByText(/31\.25/)).toBeInTheDocument();
    expect(within(t).getByText(/2026-09-30/)).toBeInTheDocument();
    const f = screen.getByRole("region", { name: /Forward PE/ });
    expect(within(f).getByText(/27\.10/)).toBeInTheDocument();
    expect(within(f).getByText(/来源未注明，观察于/)).toBeInTheDocument();
  });

  it("口径未披露显示未知说明，不出现100元解释或增长率", async () => {
    renderApp(loaderFor(both()));
    await screen.findByRole("region", { name: /滚动 PE/ });
    expect(screen.getAllByText(/来源未披露/).length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toMatch(/100元|增长率|PEG/);
  });

  it("缺一类时不替代：显示该类暂无数据", async () => {
    renderApp(loaderFor(rel("r1", [series([ob()])])));
    const f = await screen.findByRole("region", { name: /Forward PE/ });
    expect(within(f).getByText(/暂无/)).toBeInTheDocument();
    expect(within(f).queryByText(/31\.25/)).toBeNull();
  });

  it("页头常驻本机与真实/演示标识", async () => {
    renderApp(loaderFor(both()));
    expect(await screen.findByText("本机个人使用")).toBeInTheDocument();
    expect(screen.getByText("真实数据")).toBeInTheDocument();
  });

  it("演示数据显示演示标识", async () => {
    renderApp(loaderFor(rel("r1", [series([ob({ data_mode: "synthetic" })])], [], "synthetic")));
    expect(await screen.findByText("演示数据")).toBeInTheDocument();
  });

  it("无release显示空状态，自算首页入口仍在", async () => {
    renderApp(loaderFor(null));
    expect(await screen.findByText(/尚无已发布数据/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /自主计算估值/ })).toBeInTheDocument();
  });

  it("危险协议链接不渲染为链接；来源文本转义", async () => {
    const r = rel("r1", [series([ob({ source_url: "javascript:alert(1)", provider: "<img src=x onerror=alert(1)>" })])]);
    renderApp(loaderFor(r));
    await screen.findByRole("region", { name: /滚动 PE/ });
    expect(document.querySelector("a[href^='javascript']")).toBeNull();
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
  });

  it("安全 https 链接渲染并带 rel", async () => {
    renderApp(loaderFor(both()));
    const a = await screen.findByRole("link", { name: /来源链接.*Invesco/ });
    expect(a).toHaveAttribute("href", "https://www.invesco.com/qqq.pdf");
    expect(a).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });
});

describe("周度检查状态", () => {
  const key = series([ob()]).series_key;
  it("无检查记录：以最近观察时间+7天，刚好7天不逾期，超过则逾期", async () => {
    const r = both();
    const { unmount } = renderApp(loaderFor(r), new Date("2026-11-15T10:00:00Z"));
    await screen.findByRole("region", { name: /滚动 PE/ });
    expect(screen.queryAllByText("周度检查逾期")).toHaveLength(0);
    unmount();
    renderApp(loaderFor(r), new Date("2026-11-15T10:00:01Z"));
    await screen.findByRole("region", { name: /滚动 PE/ });
    expect(screen.getAllByText("周度检查逾期").length).toBe(2);
  });

  it("有证据检查后逾期基准为检查时间", async () => {
    const r = rel("r1", [series([ob()])], [{ check_id: "c", series_key: key, checked_at: "2026-11-12T00:00:00+00:00", evidence_sha256: "b".repeat(64), content_changed: false }]);
    renderApp(loaderFor(r), new Date("2026-11-18T00:00:00Z"));
    const t = await screen.findByRole("region", { name: /滚动 PE/ });
    expect(within(t).queryByText("周度检查逾期")).toBeNull();
    expect(within(t).getByText(/最近检查/)).toBeInTheDocument();
  });

  it("过期原件保留原日期，不因页面刷新而改变", async () => {
    renderApp(loaderFor(both()), new Date("2027-05-01T00:00:00Z"));
    const t = await screen.findByRole("region", { name: /滚动 PE/ });
    expect(within(t).getByText(/2026-09-30/)).toBeInTheDocument();
  });
});

describe("观察历史", () => {
  it("单点显示积累提示，多点显示同序列表格", async () => {
    const r = rel("r1", [
      series([ob()]),
      series([ob({ observation_id: "f1", provider: "SA", metric_kind: "forward_pe", metric_label_original: "FPE", value: "20" }),
              ob({ observation_id: "f2", provider: "SA", metric_kind: "forward_pe", metric_label_original: "FPE", value: "21", observed_at: "2026-11-01T00:00:00+00:00" })]),
    ]);
    renderApp(loaderFor(r));
    await screen.findByRole("region", { name: /滚动 PE/ });
    expect(screen.getByText(/仅有 1 个观察点/)).toBeInTheDocument();
    const tbl = screen.getByRole("table", { name: /SA.*历史/ });
    expect(within(tbl).getAllByRole("row")).toHaveLength(3);
    const rows = within(tbl).getAllByRole("row").slice(1).map((x) => x.textContent);
    expect(rows[0]).toContain("21");  // 较早观察在前
  });

  it("键盘可展开历史与触发导出", async () => {
    const user = userEvent.setup();
    renderApp(loaderFor(both()));
    await screen.findByRole("region", { name: /滚动 PE/ });
    const exp = screen.getAllByRole("button", { name: /导出 CSV/ })[0];
    exp.focus();
    expect(exp).toHaveFocus();
    await user.keyboard("{Enter}");
  });
});

describe("请求乱序与失败", () => {
  it("慢请求A在快请求B后返回，整屏仍是B", async () => {
    let resolveA!: (r: any) => void;
    const A = rel("A", [series([ob({ value: "11.11" })])]);
    const B = rel("B", [series([ob({ value: "22.22" })])]);
    let call = 0;
    const loader: Loader = {
      currentId: async () => (++call === 1 ? "A" : "B"),
      load: (id) => (id === "A" ? new Promise((res) => { resolveA = res; }) : Promise.resolve(B)),
    };
    const ctl = { reload: () => {} };
    render(<App loader={loader} now={NOW} exposeReload={(f) => (ctl.reload = f)} />);
    await waitFor(() => expect(resolveA).toBeDefined());
    act(() => ctl.reload());
    await screen.findByText(/22\.22/);
    await act(async () => resolveA(A));
    expect(screen.getByText(/22\.22/)).toBeInTheDocument();
    expect(screen.queryByText(/11\.11/)).toBeNull();
  });

  it("刷新失败保留上一可核实版本及日期，并显示失败", async () => {
    const A = both();
    let n = 0;
    const loader: Loader = {
      currentId: async () => "A",
      load: async () => { if (++n > 1) throw new Error("boom"); return A; },
    };
    const ctl = { reload: () => {} };
    render(<App loader={loader} now={NOW} exposeReload={(f) => (ctl.reload = f)} />);
    await screen.findByText(/31\.25/);
    act(() => ctl.reload());
    await screen.findByRole("alert");
    expect(screen.getByRole("alert")).toHaveTextContent(/刷新失败/);
    expect(screen.getByText(/31\.25/)).toBeInTheDocument();
    expect(screen.getAllByText(/2026-09-30/).length).toBeGreaterThan(0);
  });

  it("首次加载失败显示错误而非空白", async () => {
    const loader: Loader = { currentId: async () => { throw new Error("down"); }, load: async () => { throw new Error("x"); } };
    renderApp(loader);
    expect(await screen.findByRole("alert")).toHaveTextContent(/无法读取/);
  });
});

describe("更正", () => {
  it("卡片显示更正后的值；历史标注已更正", async () => {
    const orig = ob({ observation_id: "z-orig", value: "258.5", superseded_by: "a-fix" });
    const fix = ob({ observation_id: "a-fix", value: "25.85" });
    renderApp(loaderFor(rel("r1", [series([orig, fix])])));
    const t = await screen.findByRole("region", { name: /滚动 PE/ });
    expect(within(t).getByText("25.85", { selector: ".value span" })).toBeInTheDocument();
    expect(within(t).queryByText("258.5", { selector: ".value span" })).toBeNull();
    const tbl = within(t).getByRole("table", { name: /历史/ });
    expect(within(tbl).getByText(/已更正/)).toBeInTheDocument();
  });
});
