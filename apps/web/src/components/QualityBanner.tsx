import type { Snapshot } from "../data/types";
import { fmtPct } from "../data/fmt";
import { shownSubset } from "./OverviewGrid";

const STATE: Record<string, string> = { complete: "完整", partial: "部分覆盖", unavailable: "不可用" };

export function QualityBanner({ snap }: { snap: Snapshot }) {
  const known = snap.basket.universe_complete;
  return (
    <section aria-label="数据质量" className="quality">
      {(["ttm", "fy1"] as const).map((k) => {
        const m = snap.results.metrics[k];
        const sub = shownSubset(snap, k);
        const gate = snap.subsets?.[k]?.min_coverage;
        const niPath = k === "ttm" ? snap.diagnostics.filter((d) => d.code === "TTM_NET_INCOME_PATH").length : 0;
        const cov = known && m.coverage_ratio !== null ? `覆盖权重 ${fmtPct(m.coverage_ratio)}` : "完整权重未知";
        return (
          <div key={k} className="qcol">
            <p data-testid={`status-${k}`}><strong>{k.toUpperCase()}</strong>：{STATE[m.eligibility]}{m.eligibility !== "complete" && (sub ? "；显示已覆盖部分 PE，未形成完整自算 PE" : "；未形成完整自算 PE")}</p>
            <p>{cov}{m.eligibility === "partial" && gate ? `（展示门槛 ${fmtPct(gate)}）` : ""}</p>
            {niPath > 0 && <p data-testid="ni-path-count">其中 {niPath} 只证券按“TTM 净利润 ÷（稀释股数 × 股价）”计算，其余按四个已报告单季 EPS 之和。</p>}
            {m.missing_security_ids.length > 0 && (m.missing_security_ids.length <= 12
              ? <p>缺失证券：{m.missing_security_ids.join("、")}</p>
              : <details><summary>缺失证券（{m.missing_security_ids.length} 只，点击展开）</summary><p>{m.missing_security_ids.join("、")}</p></details>)}
          </div>
        );
      })}
      {snap.basket.unknown_excluded_items.length > 0 && (
        <p className="note">非股票资产权重部分未知（未知项：{snap.basket.unknown_excluded_items.join("、")}），总排除权重不可得。</p>
      )}
    </section>
  );
}
