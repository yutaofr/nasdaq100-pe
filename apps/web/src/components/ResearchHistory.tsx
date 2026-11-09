import type { Snapshot } from "../data/types";
import { formatUtc } from "../data/format";
import { fmtPe } from "../data/fmt";

const isPoint = (s: Snapshot, k: "ttm" | "fy1") => s.results.metrics[k].eligibility === "complete" && s.results.metrics[k].pe_state === "value";

function weekdayGap(a: string, b: string): boolean {
  let d = new Date(a + "T00:00:00Z"); const end = new Date(b + "T00:00:00Z"); let n = 0;
  while (d < end) { d = new Date(d.getTime() + 86400000); if (d.getUTCDay() % 6 !== 0) n++; }
  return n > 1;
}

function polyPoints(v: number[]): string {
  const min = Math.min(...v), span = Math.max(...v) - min || 1;
  return v.map((x, i) => `${(i / (v.length - 1)) * 100},${28 - ((x - min) / span) * 26}`).join(" ");
}

export function ResearchHistory({ snaps }: { snaps: Snapshot[] }) {
  const groups = new Map<string, Snapshot[]>();
  for (const s of snaps) groups.set(s.series_key, [...(groups.get(s.series_key) ?? []), s]);
  return (
    <section aria-label="研究观察历史" className="section">
      <h3>研究观察历史</h3>
      {[...groups.entries()].map(([key, list]) => {
        const sorted = [...list].sort((a, b) => a.context.T.localeCompare(b.context.T));
        const pts = sorted.filter((s) => isPoint(s, "ttm"));
        const weekly = sorted[0].context.freshness_policy === "weekly";
        return (
          <div key={key} className="hgroup">
            <h4>{key.split("|").slice(1).join(" / ")}（{sorted[0].data_mode === "real" ? "真实" : "演示"}）</h4>
            <p className="hint">{weekly ? "按观察时点 T 排列；周度观察间隔不是缺失交易日。" : "按目标日 D 排列；周末休市不是缺失。"}</p>
            {pts.length < 2 ? <p>仅有 {pts.length} 个完整数值点，积累后才绘制趋势；N/M 与不完整结果不计入。</p> : (
              <svg viewBox="0 0 100 30" role="img" aria-label="TTM PE 趋势（等价表格见下）">
                <polyline fill="none" stroke="currentColor" points={polyPoints(pts.map((s) => Number(s.results.metrics.ttm.pe)))} />
              </svg>
            )}
            <div className="tablewrap">
              <table aria-label={`历史 ${key}`}>
                <thead><tr><th scope="col">观察时点 T</th><th scope="col">价格日 D</th><th scope="col">TTM PE</th><th scope="col">FY1 PE</th><th scope="col">备注</th></tr></thead>
                <tbody>
                  {sorted.map((s, i) => (
                    <tr key={s.snapshot_id}>
                      <td>{formatUtc(s.context.T)}</td><td>{s.context.D}</td>
                      <td>{isPoint(s, "ttm") ? fmtPe(s.results.metrics.ttm.pe) : s.results.metrics.ttm.pe_state === "non_positive" ? "N/M" : "—"}</td>
                      <td>{isPoint(s, "fy1") ? fmtPe(s.results.metrics.fy1.pe) : s.results.metrics.fy1.pe_state === "non_positive" ? "N/M" : "—"}</td>
                      <td>{!weekly && i > 0 && weekdayGap(sorted[i - 1].context.D, s.context.D) ? "交易日缺口（断线）" : ""}{s.revision_seq > 1 ? ` 修订${s.revision_seq}` : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </section>
  );
}
