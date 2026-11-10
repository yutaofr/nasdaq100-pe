export type MetricKind = "trailing_pe" | "forward_pe";

export interface Observation {
  observation_id: string;
  provider: string;
  instrument: string;
  metric_label_original: string;
  metric_kind: MetricKind;
  value: string;
  unit: string;
  source_as_of: string | null;
  observed_at: string;
  source_url: string;
  evidence_sha256: string;
  evidence_locator: string;
  period_basis: string;
  accounting_basis: string;
  loss_treatment: string;
  methodology_status: string;
  entry_mode: string;
  data_mode: "real" | "synthetic";
  superseded_by?: string;
}

export interface Series {
  series_key: string;
  count: number;
  latest_observed_at: string;
  observations: Observation[];
}

export interface CheckEvent {
  check_id: string;
  series_key: string;
  checked_at: string;
  evidence_sha256: string;
  content_changed: boolean;
}

export interface LocalRelease {
  manifest: { release_id: string; deployment_mode: string; data_modes: string[]; built_at: string; files: Record<string, string> };
  observations: { series: Series[] };
  method: { title: string; notes: string[] };
  status: Record<string, unknown>;
  checks: { checks: CheckEvent[] };
  // 研究快照索引（T11）；缺省表示无研究数据
  research?: unknown;
}

// ---------- 研究快照（T10 输出，前端只格式化，不重算）----------
export interface SecResult {
  security_id: string; weight: string; valid: boolean; yield_: string | null; contribution: string | null;
  contribution_points: string | null; pe: string | null; flags: string[];
}
export interface SectorResult {
  name: string; weight: string; valid_weight: string; known_contribution: string; complete: boolean;
  sector_yield: string | null; pe: string | null; pe_state: string; note: string; member_ids: string[];
}
export interface MetricResult {
  eligibility: "complete" | "partial" | "unavailable"; quality_flags: string[]; valid_weight: string;
  coverage_ratio: string | null; known_contribution: string; portfolio_yield: string | null; pe: string | null;
  pe_state: "value" | "non_positive" | "incomplete"; missing_security_ids: string[];
  securities: Record<string, SecResult>; sectors: SectorResult[];
}
export interface SubsetResult {
  name: string; available: boolean; reason: string; covered_weight: string | null; covered_count: number;
  excluded_ids: string[]; subset_yield: string | null; pe: string | null; pe_state: string; note: string;
  coverage_ratio?: string | null; min_coverage?: string | null; display_qualified?: boolean;
}
export interface Snapshot {
  snapshot_id: string; series_key: string; data_mode: "real" | "synthetic"; revision_seq: number;
  context: { W: string; D: string; T: string; analysis_profile: string; basket_policy: string; coverage_policy: string; freshness_policy: string; method_version: string; data_mode: string };
  completeness: { ttm: string; fy1: string };
  basket: { mode: string; date: string; universe_complete: boolean; final_weights: Record<string, string>; known_excluded_weight: string | null; total_excluded_weight: string | null; unknown_excluded_items: string[]; index_comparability: string };
  securities: { security_id: string; issuer_id: string; share_class: string; ticker: string; name: string; sector: string | null }[];
  results: { metrics: { ttm: MetricResult; fy1: MetricResult }; derived: Record<string, any>; total_market_cap: string | null; market_cap_flags: string[] };
  subsets: Record<string, SubsetResult>;
  diagnostics: { code: string; security_id?: string; kind?: string }[];
  last_complete: Record<string, { snapshot_id: string; D: string }>;
}
export interface ResearchRelease {
  manifest: { release_id: string; kind: string; data_modes: string[]; built_at: string };
  research: { snapshots: Snapshot[] };
  method: { title: string; notes: string[] };
  status: Record<string, unknown>;
}
