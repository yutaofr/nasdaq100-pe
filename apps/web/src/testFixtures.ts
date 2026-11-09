import type { LocalRelease, Observation, Series } from "./data/types";
import type { Loader } from "./data/ReleaseProvider";

export function ob(over: Partial<Observation> = {}): Observation {
  return {
    observation_id: "o1", provider: "Invesco", instrument: "QQQ", metric_label_original: "P/E (TTM)",
    metric_kind: "trailing_pe", value: "31.25", unit: "x", source_as_of: "2026-09-30",
    observed_at: "2026-11-08T10:00:00+00:00", source_url: "https://www.invesco.com/qqq.pdf",
    evidence_sha256: "a".repeat(64), evidence_locator: "p1", period_basis: "unknown", accounting_basis: "unknown",
    loss_treatment: "unknown", methodology_status: "unknown", entry_mode: "manual", data_mode: "real", ...over,
  };
}

export function series(obs: Observation[]): Series {
  const sorted = [...obs].sort((a, b) => a.observed_at.localeCompare(b.observed_at));
  const o = sorted[0];
  return { series_key: [o.provider, o.metric_kind, o.metric_label_original, o.data_mode].join("|"), count: sorted.length,
           latest_observed_at: sorted[sorted.length - 1].observed_at, observations: sorted };
}

export function rel(id: string, ss: Series[], checks: LocalRelease["checks"]["checks"] = [], mode: "real" | "synthetic" = "real"): LocalRelease {
  return {
    manifest: { release_id: id, deployment_mode: "local_private", data_modes: [mode], built_at: "2026-11-08T10:00:00+00:00", files: {} },
    observations: { series: ss }, method: { title: "方法与限制", notes: ["页面展示的是来源公布的整体估值参考"] },
    status: {}, checks: { checks },
  };
}

export const loaderFor = (r: LocalRelease | null): Loader => ({
  currentId: async () => (r ? r.manifest.release_id : null),
  load: async () => r!,
});

// ---------- 研究快照夹具（演示数据，字段与后端 snapshot 对齐）----------
import type { MetricResult, ResearchRelease, SecResult, Snapshot } from "./data/types";
import type { ResearchLoader } from "./data/research";

export function secRes(id: string, weight: string, y: string | null, pe: string | null, flags: string[] = []): SecResult {
  const valid = y !== null;
  return { security_id: id, weight, valid, yield_: y, contribution: valid ? String(Number(weight) * Number(y)) : null,
           contribution_points: valid ? String(100 * Number(weight) * Number(y)) : null, pe, flags };
}

export function metric(over: Partial<MetricResult> & { securities: Record<string, SecResult> }): MetricResult {
  return { eligibility: "partial", quality_flags: [], valid_weight: "0.8", coverage_ratio: "0.8", known_contribution: "0.019",
           portfolio_yield: null, pe: null, pe_state: "incomplete", missing_security_ids: ["c"], sectors: [], ...over };
}

const EMPTY_M = (ids: string[]): MetricResult => metric({
  eligibility: "unavailable", valid_weight: "0", coverage_ratio: "0", known_contribution: "0", missing_security_ids: ids,
  securities: Object.fromEntries(ids.map((i) => [i, secRes(i, "0.1", null, null, ["MISSING_FIELD"])])),
});

export function snap(over: Partial<Snapshot> = {}, ttm?: MetricResult, fy1?: MetricResult): Snapshot {
  const ids = ["a", "b", "c"];
  const t = ttm ?? metric({
    securities: { a: secRes("a", "0.5", "0.05", "20"), b: secRes("b", "0.3", "-0.02", "-50"), c: secRes("c", "0.2", null, null, ["MISSING_FIELD"]) },
    sectors: [
      { name: "Tech", weight: "0.8", valid_weight: "0.8", known_contribution: "0.019", complete: true, sector_yield: "0.02375", pe: "42.1", pe_state: "value", note: "", member_ids: ["a", "b"] },
      { name: "Health", weight: "0.2", valid_weight: "0", known_contribution: "0", complete: false, sector_yield: null, pe: null, pe_state: "incomplete", note: "行业盈利未全部有效，仅显示已知贡献", member_ids: ["c"] },
    ],
  });
  return {
    snapshot_id: "s".repeat(20), series_key: "1|research|current|subset|weekly|synthetic", data_mode: "synthetic", revision_seq: 1,
    context: { W: "2026-11-06", D: "2026-11-06", T: "2026-11-08T12:00:00+00:00", analysis_profile: "research", basket_policy: "current", coverage_policy: "subset", freshness_policy: "weekly", method_version: "1", data_mode: "synthetic" },
    completeness: { ttm: t.eligibility, fy1: (fy1 ?? EMPTY_M(ids)).eligibility },
    basket: { mode: "qqq_equity_proxy", date: "2026-11-06", universe_complete: true, final_weights: { a: "0.5", b: "0.3", c: "0.2" }, known_excluded_weight: "0.0017", total_excluded_weight: null, unknown_excluded_items: ["x"], index_comparability: "n/a" },
    securities: [
      { security_id: "a", issuer_id: "a", share_class: "common", ticker: "AAA", name: "Alpha Inc", sector: "Tech" },
      { security_id: "b", issuer_id: "b", share_class: "common", ticker: "BBB", name: "Beta Inc", sector: "Tech" },
      { security_id: "c", issuer_id: "c", share_class: "common", ticker: "CCC", name: "Gamma Inc", sector: "Health" },
    ],
    results: { metrics: { ttm: t, fy1: fy1 ?? EMPTY_M(ids) }, derived: { ttm: {}, fy1: {}, comparison: {} }, total_market_cap: null, market_cap_flags: ["MARKET_CAP_MISSING"] },
    subsets: { ttm: { name: "已覆盖证券子集TTM估值", available: true, reason: "", covered_weight: "0.8", covered_count: 2, excluded_ids: ["c"], subset_yield: "0.02375", pe: "42.10", pe_state: "value", note: "并非全指数" }, fy1: { name: "已覆盖证券子集FY1估值", available: false, reason: "NO_COVERED_WEIGHT", covered_weight: "0", covered_count: 0, excluded_ids: ids, subset_yield: null, pe: null, pe_state: "incomplete", note: "并非全指数" } },
    diagnostics: [], last_complete: {}, ...over,
  };
}

export function completeSnap(y: string, extra: Partial<Snapshot> = {}): Snapshot {
  const pe = Number(y) > 0 ? String(1 / Number(y)) : null;
  const m = metric({
    eligibility: "complete", valid_weight: "1", coverage_ratio: "1", known_contribution: y, portfolio_yield: y, pe,
    pe_state: Number(y) > 0 ? "value" : "non_positive", missing_security_ids: [],
    securities: { a: secRes("a", "0.5", y, pe), b: secRes("b", "0.3", y, pe), c: secRes("c", "0.2", y, pe) }, sectors: [],
  });
  const s = snap(extra, m);
  s.results.derived = { ttm: { hundred_yuan: { amount: String(100 * Number(y)), loss: Number(y) < 0 }, yield_percent: String(100 * Number(y)) }, fy1: {}, comparison: {} };
  return s;
}

export function rrel(id: string, snaps: Snapshot[]): ResearchRelease {
  return { manifest: { release_id: id, kind: "research", data_modes: ["synthetic"], built_at: "2026-11-08T12:00:00+00:00" },
           research: { snapshots: snaps }, method: { title: "方法与限制", notes: ["代理方法说明"] }, status: {} };
}

export const researchLoaderFor = (r: ResearchRelease | null): ResearchLoader => ({
  currentId: async () => (r ? r.manifest.release_id : null), load: async () => r!,
});
