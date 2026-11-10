import { render, screen } from "@testing-library/react";
import App from "./App";
import { loaderFor, ob, rel, researchLoaderFor, series } from "./testFixtures";

const published = loaderFor(rel("published", [series([ob({ value: "31.25" })])]));
const noResearch = researchLoaderFor(null);

describe("dashboard routes", () => {
  it.each(["", "#/", "#/research"])("%s shows the calculated dashboard without a published-value fallback", async (hash) => {
    window.location.hash = hash;
    render(<App loader={published} researchLoader={noResearch} />);
    expect(await screen.findByText(/暂无合格的真实研究输入/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /自主计算研究/ })).toBeInTheDocument();
    expect(screen.queryByText("31.25")).toBeNull();
    expect(screen.queryByRole("region", { name: /滚动 PE/ })).toBeNull();
    expect(screen.getByText(/收益率 = Σ.*权重.*每股盈利.*股价/)).toBeInTheDocument();
    expect(screen.getAllByText(/TTM.*GAAP.*FY1.*normalized/).length).toBeGreaterThan(0);
    expect(screen.getByText(/负盈利.*缺失.*零/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /外部估值对照/ })).toHaveAttribute("href", "#/reference");
  });

  it("keeps published observations on the external reference route", async () => {
    window.location.hash = "#/reference";
    render(<App loader={published} researchLoader={noResearch} />);
    expect(await screen.findByRole("heading", { name: /外部估值对照/ })).toBeInTheDocument();
    expect(screen.getByText("31.25")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /外部估值对照/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /自主计算估值/ })).toHaveAttribute("href", "#/");
  });
});
