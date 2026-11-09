import type { Snapshot } from "../data/types";
import { fmtPct } from "../data/fmt";

const STATE: Record<string, string> = { complete: "完整", partial: "部分覆盖", unavailable: "不可用" };

export function QualityBanner({ snap }: { snap: Snapshot }) {
  const known = snap.basket.universe_complete;
  return (
    <section aria-label="数据质量" className="quality">
      {(["ttm", "fy1"] as const).map((k) => {
        const m = snap.results.metrics[k];
        const cov = known && m.coverage_ratio !== null ? `覆盖权重 ${fmtPct(m.coverage_ratio)}` : "完整权重未知";
        return (
          <div key={k} className="qcol">
            <p data-testid={`status-${k}`}><strong>{k.toUpperCase()}</strong>：{STATE[m.eligibility]}</p>
            <p>{cov}</p>
            {m.missing_security_ids.length > 0 && <p>缺失证券：{m.missing_security_ids.join("、")}</p>}
          </div>
        );
      })}
      {snap.basket.unknown_excluded_items.length > 0 && (
        <p className="note">非股票资产权重部分未知（未知项：{snap.basket.unknown_excluded_items.join("、")}），总排除权重不可得。</p>
      )}
    </section>
  );
}
