import { render, screen, within, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../App";
import { completeSnap, loaderFor, rrel, researchLoaderFor, snap, ob, rel, series } from "../testFixtures";
import type { ResearchRelease } from "../data/types";
import type { ResearchLoader } from "../data/research";

function renderResearch(r: ResearchRelease | null, extra: Partial<{ researchLoader: ResearchLoader }> = {}) {
  window.location.hash = "#/research";
  return render(<App loader={loaderFor(rel("p1", [series([ob()])]))} researchLoader={extra.researchLoader ?? researchLoaderFor(r)} now={new Date("2026-11-09T00:00:00Z")} />);
}

describe("研究页：标识与模式", () => {
  it("名称含观察时点研究；代理标识；周度非同步；W/D/T 同屏", async () => {
    renderResearch(rrel("r1", [snap()]));
    expect(await screen.findByRole("heading", { name: /观察时点研究/ })).toBeInTheDocument();
    expect(screen.getByText("纳指100估值估算（QQQ股票持仓代理）")).toBeInTheDocument();
    expect(screen.getByText("非同步周度观察")).toBeInTheDocument();
    expect(screen.getByText(/篮子日 W：2026-11-06/)).toBeInTheDocument();
    expect(screen.getByText(/目标价格日 D：2026-11-06/)).toBeInTheDocument();
    expect(screen.getByText(/观察时点 T：2026-11-08 12:00 UTC/)).toBeInTheDocument();
    expect(screen.getByText("演示数据")).toBeInTheDocument();
  });

  it("固定篮子显示 QQQ历史权重固定篮子研究", async () => {
    const s = snap(); s.context.basket_policy = "fixed"; s.basket.index_comparability = "unverified";
    renderResearch(rrel("r1", [s]));
    expect(await screen.findByText("QQQ历史权重固定篮子研究")).toBeInTheDocument();
    expect(screen.getByText(/指数可比性：未验证/)).toBeInTheDocument();
  });

  it("无研究发布：显示具体缺口，不显示数值", async () => {
    renderResearch(null);
    expect(await screen.findByText(/暂无合格的真实研究输入/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\d+\.\d\d 倍/);
  });
});

describe("概览格子与状态", () => {
  it("顺序：数量/市值 → TTM/FY1 收益率 → TTM/FY1 PE", async () => {
    renderResearch(rrel("r1", [snap()]));
    await screen.findByRole("heading", { name: /观察时点研究/ });
    const ids = [...document.querySelectorAll("[data-overview]")].map((e) => e.getAttribute("data-overview"));
    expect(ids).toEqual(["count", "marketcap", "ttm-yield", "fy1-yield", "ttm-pe", "fy1-pe"]);
  });

  it("partial：覆盖率、缺失清单；PE/收益率为 —＋原因；无100元解释", async () => {
    renderResearch(rrel("r1", [snap()]));
    const pe = (await screen.findAllByText(/盈利未完整/))[0];
    expect(pe).toBeInTheDocument();
    expect(screen.getByText(/覆盖权重 80\.00%/)).toBeInTheDocument();
    expect(screen.getByText(/缺失证券：c/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/100元/);
    expect(within(document.querySelector("[data-overview='ttm-pe']") as HTMLElement).getByText(/^—/)).toBeInTheDocument();
  });

  it("FY1 与 TTM 状态独立显示", async () => {
    renderResearch(rrel("r1", [snap()]));
    await screen.findByRole("heading", { name: /观察时点研究/ });
    expect(screen.getByTestId("status-ttm")).toHaveTextContent("部分覆盖");
    expect(screen.getByTestId("status-fy1")).toHaveTextContent("不可用");
    expect(screen.getByTestId("status-ttm")).toHaveTextContent("未形成完整自算 PE");
    expect(screen.getByTestId("status-fy1")).toHaveTextContent("未形成完整自算 PE");
  });

  it("完整正收益：PE 两位小数+倍、收益率两位百分数、100元解释与限制", async () => {
    renderResearch(rrel("r1", [completeSnap("0.05")]));
    const pe = await screen.findByTestId("val-ttm-pe");
    expect(pe).toHaveTextContent("20.00 倍");
    expect(screen.getByTestId("val-ttm-yield")).toHaveTextContent("5.00%");
    expect(screen.getByText(/100元.*5\.00元/)).toBeInTheDocument();
    expect(screen.getByText(/不同盈利口径/)).toBeInTheDocument();
  });

  it("完整非正：N/M（盈利非正），收益率保留负号，亏损标注", async () => {
    renderResearch(rrel("r1", [completeSnap("-0.02")]));
    expect(await screen.findByTestId("val-ttm-pe")).toHaveTextContent("N/M（盈利非正）");
    expect(screen.getByTestId("val-ttm-yield")).toHaveTextContent("-2.00%");
    expect(screen.getByText(/亏损/, { selector: "[data-testid='hundred-yuan']" })).toBeInTheDocument();
  });

  it("权重未知：覆盖率显示完整权重未知而非 0%", async () => {
    const s = snap(); s.results.metrics.ttm.coverage_ratio = null; s.basket.universe_complete = false;
    renderResearch(rrel("r1", [s]));
    expect(await screen.findAllByText(/完整权重未知/)).not.toHaveLength(0);
    expect(screen.queryByText(/覆盖权重 0\.00%/)).toBeNull();
  });

  it("市值不可用时说明原因", async () => {
    renderResearch(rrel("r1", [snap()]));
    expect(await screen.findByText(/总市值不可用/)).toBeInTheDocument();
  });
});

describe("明细表", () => {
  const rows = () => within(screen.getByRole("table", { name: "成分明细" })).getAllByRole("row").slice(1);

  it("默认权重降序；列与ADD一致；个股负PE标亏损；缺失为 —＋原因", async () => {
    renderResearch(rrel("r1", [snap()]));
    await screen.findByRole("table", { name: "成分明细" });
    const heads = within(screen.getByRole("table", { name: "成分明细" })).getAllByRole("columnheader").map((h) => h.textContent);
    expect(heads.join("|")).toMatch(/序号.*名称\/代码.*权重.*TTM PE.*FY1 PE.*TTM贡献.*FY1贡献.*状态/);
    expect(rows().map((r) => within(r).getAllByRole("cell")[1].textContent)).toEqual([expect.stringContaining("Alpha"), expect.stringContaining("Beta"), expect.stringContaining("Gamma")]);
    expect(within(rows()[1]).getByText("亏损")).toBeInTheDocument();
    expect(within(rows()[2]).getAllByText(/^—/).length).toBeGreaterThan(0);
  });

  it("按 TTM PE 排序：空值始终置底；升降序都是；键盘可操作", async () => {
    const user = userEvent.setup();
    renderResearch(rrel("r1", [snap()]));
    const btn = await screen.findByRole("button", { name: /按 TTM PE 排序/ });
    btn.focus(); await user.keyboard("{Enter}");
    expect(rows().map((r) => within(r).getAllByRole("cell")[1].textContent!.includes("Gamma")).lastIndexOf(true)).toBe(2);
    await user.keyboard("{Enter}");
    expect(within(rows()[2]).getAllByRole("cell")[1].textContent).toContain("Gamma");
  });

  it("同值按证券ID稳定排序", async () => {
    const s = snap();
    s.basket.final_weights = { a: "0.4", b: "0.4", c: "0.2" };
    s.results.metrics.ttm.securities.a.weight = "0.4"; s.results.metrics.ttm.securities.b.weight = "0.4";
    renderResearch(rrel("r1", [s]));
    await screen.findByRole("table", { name: "成分明细" });
    expect(within(rows()[0]).getAllByRole("cell")[1].textContent).toContain("Alpha");
  });

  it("搜索只影响明细与计数，不改变概览", async () => {
    const user = userEvent.setup();
    renderResearch(rrel("r1", [snap()]));
    await user.type(await screen.findByRole("searchbox", { name: /搜索/ }), "gamma");
    expect(rows()).toHaveLength(1);
    expect(screen.getByText(/显示 1 \/ 3/)).toBeInTheDocument();
    expect(screen.getByText(/覆盖权重 80\.00%/)).toBeInTheDocument();
  });

  it("行业点击筛选明细并可清除", async () => {
    const user = userEvent.setup();
    renderResearch(rrel("r1", [snap()]));
    await user.click(await screen.findByRole("button", { name: /筛选行业 Health/ }));
    expect(rows()).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: /清除行业筛选/ }));
    expect(rows()).toHaveLength(3);
  });

  it("极小非零权重不显示为 0", async () => {
    const s = snap(); s.results.metrics.ttm.securities.c.weight = "0.00001";
    renderResearch(rrel("r1", [s]));
    await screen.findByRole("table", { name: "成分明细" });
    expect(screen.getAllByText("<0.01%").length).toBeGreaterThan(0);
  });

  it("展开详情可见精确值与诊断", async () => {
    const user = userEvent.setup();
    renderResearch(rrel("r1", [snap()]));
    await user.click((await screen.findAllByRole("button", { name: /详情/ }))[0]);
    expect(screen.getByText(/精确权重/)).toBeInTheDocument();
  });
});

describe("历史", () => {
  it("单点积累提示；N/M 与 partial 不计数值点；不同序列分表不连线", async () => {
    const a = snap(); const b = completeSnap("0.05", { snapshot_id: "t".repeat(20), series_key: "1|strict|current|full|daily|synthetic" });
    const c = completeSnap("-0.02", { snapshot_id: "u".repeat(20), series_key: "1|strict|current|full|daily|synthetic" });
    c.context.D = "2026-11-05"; c.context.T = "2026-11-06T22:00:00+00:00";
    renderResearch(rrel("r1", [a, b, c]));
    await screen.findByRole("heading", { name: /观察时点研究/ });
    const hist = screen.getByRole("region", { name: "研究观察历史" });
    expect(within(hist).getAllByRole("table")).toHaveLength(2);
    expect(within(hist).getByText(/仅有 0 个完整数值点/)).toBeInTheDocument();   // 研究/周度序列：partial 不算
    expect(within(hist).getByText(/仅有 1 个完整数值点/)).toBeInTheDocument();   // strict 序列：N/M 不算
    expect(hist.querySelectorAll("polyline")).toHaveLength(0);
  });
});

describe("请求乱序与失败（研究）", () => {
  it("慢请求A后到不覆盖B", async () => {
    let resolveA!: (r: ResearchRelease) => void;
    const A = rrel("A", [completeSnap("0.1")]); const B = rrel("B", [completeSnap("0.05")]);
    const ctl = { reload: () => {} };
    let n = 0;
    const loader: ResearchLoader = {
      currentId: async () => (++n === 1 ? "A" : "B"),
      load: (id) => (id === "A" ? new Promise((res) => { resolveA = res; }) : Promise.resolve(B)),
    };
    window.location.hash = "#/research";
    render(<App loader={loaderFor(rel("p1", [series([ob()])]))} researchLoader={loader} now={new Date()} exposeResearchReload={(f) => (ctl.reload = f)} />);
    await act(async () => {});
    act(() => ctl.reload());
    expect(await screen.findByTestId("val-ttm-pe")).toHaveTextContent("20.00 倍");
    await act(async () => resolveA(A));
    expect(screen.getByTestId("val-ttm-pe")).toHaveTextContent("20.00 倍");
  });

  it("刷新失败保留上一版本并显示失败", async () => {
    const ctl = { reload: () => {} };
    let n = 0;
    const loader: ResearchLoader = { currentId: async () => "A", load: async () => { if (++n > 1) throw new Error("boom"); return rrel("A", [snap()]); } };
    window.location.hash = "#/research";
    render(<App loader={loaderFor(rel("p1", [series([ob()])]))} researchLoader={loader} now={new Date()} exposeResearchReload={(f) => (ctl.reload = f)} />);
    await screen.findByRole("heading", { name: /观察时点研究/ });
    act(() => ctl.reload());
    expect(await screen.findByRole("alert")).toHaveTextContent(/研究数据刷新失败/);
    expect(screen.getByRole("table", { name: "成分明细" })).toBeInTheDocument();
  });
});

describe("已覆盖部分 PE 的展示门槛", () => {
  const withSubset = (over: Record<string, unknown>) => {
    const s = snap();
    s.subsets.ttm = { ...s.subsets.ttm, coverage_ratio: "0.8", min_coverage: "0.9", display_qualified: false, ...over };
    return s;
  };

  it("达到门槛：TTM 卡片显示已覆盖部分 PE、覆盖率与“非完整指数 PE”，状态仍为部分覆盖", async () => {
    const s = withSubset({ coverage_ratio: "0.915", display_qualified: true, pe: "27.71", subset_yield: "0.03609" });
    s.diagnostics = [{ code: "TTM_NET_INCOME_PATH", security_id: "b", kind: "ttm" }];
    renderResearch(rrel("r1", [s]));
    expect(await screen.findByTestId("val-ttm-pe")).toHaveTextContent("27.71 倍");
    const card = document.querySelector("[data-overview='ttm-pe']") as HTMLElement;
    expect(within(card).getByTestId("scope-ttm")).toHaveTextContent(/覆盖权重 91\.50%.*1 只未计入.*非完整指数 PE/);
    expect(screen.getByTestId("val-ttm-yield")).toHaveTextContent("3.61%");
    expect(screen.getByTestId("status-ttm")).toHaveTextContent("部分覆盖；显示已覆盖部分 PE，未形成完整自算 PE");
    expect(screen.getByTestId("ni-path-count")).toHaveTextContent("其中 1 只证券");
    expect(document.body.textContent).not.toMatch(/100元/);           // 不把部分覆盖当完整结果解释
  });

  it("未达门槛或旧快照没有门槛字段：PE 留空", async () => {
    renderResearch(rrel("r1", [withSubset({})]));
    expect(await screen.findByTestId("val-ttm-pe")).toHaveTextContent("— 盈利未完整");
    expect(screen.queryByTestId("scope-ttm")).toBeNull();
    expect(screen.getByText(/覆盖权重 80\.00%（展示门槛 90\.00%）/)).toBeInTheDocument();
  });

  it("FY1 不可用时不受 TTM 展示影响", async () => {
    renderResearch(rrel("r1", [withSubset({ coverage_ratio: "0.95", display_qualified: true })]));
    expect(await screen.findByTestId("val-fy1-pe")).toHaveTextContent("— 无有效盈利");
  });
});

describe("缺失清单", () => {
  it("超过 12 只时折叠，数量仍可见，不把 PE 卡片挤到屏幕之外", async () => {
    const s = snap();
    s.results.metrics.ttm.missing_security_ids = Array.from({ length: 13 }, (_, i) => `m${i}`);
    renderResearch(rrel("r1", [s]));
    const sum = await screen.findByText("缺失证券（13 只，点击展开）");
    expect((sum.closest("details") as HTMLDetailsElement).open).toBe(false);
    expect(sum.closest("details")).toHaveTextContent("m12");
  });
});
