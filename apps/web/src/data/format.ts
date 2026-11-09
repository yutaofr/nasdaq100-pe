import type { CheckEvent, Series } from "./types";

export const WEEK_MS = 7 * 24 * 3600 * 1000;

export function formatUtc(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())} UTC`;
}

const UNKNOWN = "来源未披露（未知）";
const MAP: Record<string, Record<string, string>> = {
  period: { ttm: "过去12个月", forward_12m: "未来12个月", fy1: "下一财年(FY1)" },
  accounting: { gaap: "GAAP", normalized: "调整后(normalized)" },
  loss: { excluded: "剔除亏损", included_zero: "亏损按零计", included_negative: "含负盈利" },
  method: { partial: "部分披露", disclosed: "已披露" },
};
export const label = (kind: keyof typeof MAP, v: string) => (v === "unknown" ? UNKNOWN : MAP[kind][v] ?? v);

/** 只允许 http(s)；其余协议不渲染为链接。 */
export function safeHref(u: string): string | null {
  try {
    const x = new URL(u);
    return x.protocol === "http:" || x.protocol === "https:" ? x.href : null;
  } catch { return null; }
}

export function checkStatus(s: Series, checks: CheckEvent[], now: Date) {
  const mine = checks.filter((c) => c.series_key === s.series_key);
  const lastCheck = mine.length ? mine.map((c) => c.checked_at).sort().at(-1)! : null;
  const base = lastCheck ?? s.latest_observed_at;
  const due = new Date(new Date(base).getTime() + WEEK_MS);
  return { lastCheck, due, overdue: now.getTime() > due.getTime() };
}

export function csvEscape(v: string): string {
  const t = /^[=+\-@\t\r]/.test(v) ? "'" + v : v;
  return /[",\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t;
}

export function seriesCsv(s: Series): string {
  const cols = ["observation_id", "provider", "metric_label_original", "metric_kind", "value", "source_as_of", "observed_at", "source_url", "evidence_sha256", "data_mode"] as const;
  const rows = s.observations.map((o) => cols.map((c) => (c === "value" ? o.value : csvEscape(String(o[c] ?? "")))).join(","));
  return [cols.join(","), ...rows].join("\n");
}
