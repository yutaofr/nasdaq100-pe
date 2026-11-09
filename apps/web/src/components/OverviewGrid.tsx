import type { MetricResult, Snapshot } from "../data/types";
import { fmtPct, fmtPe } from "../data/fmt";

function peText(m: MetricResult, known: boolean): string {
  if (m.eligibility === "complete") return m.pe_state === "non_positive" ? "N/M（盈利非正）" : (fmtPe(m.pe) ?? "—");
  if (!known) return "— 完整权重未知";
  return m.eligibility === "unavailable" ? "— 无有效盈利" : "— 盈利未完整";
}
function yieldText(m: MetricResult, known: boolean): string {
  if (m.eligibility === "complete") return fmtPct(m.portfolio_yield) ?? "—";
  if (!known) return "— 完整权重未知";
  return m.eligibility === "unavailable" ? "— 无有效盈利" : "— 盈利未完整";
}

export function OverviewGrid({ snap }: { snap: Snapshot }) {
  const known = snap.basket.universe_complete;
  const { ttm, fy1 } = snap.results.metrics;
  const cap = snap.results.total_market_cap;
  const Card = ({ id, title, children }: { id: string; title: string; children: React.ReactNode }) => (
    <div className="ocard" data-overview={id}><p className="otitle">{title}</p>{children}</div>
  );
  return (
    <div className="ogrid">
      <Card id="count" title="成分数量"><p className="oval">{snap.securities.length}</p></Card>
      <Card id="marketcap" title="总市值">
        {cap ? <p className="oval">{cap}</p> : <p className="oval small">— 总市值不可用（{snap.results.market_cap_flags.join("、") || "原因未知"}）</p>}
      </Card>
      <Card id="ttm-yield" title="TTM 盈利收益率"><p className="oval" data-testid="val-ttm-yield">{yieldText(ttm, known)}</p></Card>
      <Card id="fy1-yield" title="FY1 盈利收益率"><p className="oval" data-testid="val-fy1-yield">{yieldText(fy1, known)}</p></Card>
      <Card id="ttm-pe" title="TTM PE"><p className="oval" data-testid="val-ttm-pe">{peText(ttm, known)}</p></Card>
      <Card id="fy1-pe" title="FY1 PE"><p className="oval" data-testid="val-fy1-pe">{peText(fy1, known)}</p></Card>
    </div>
  );
}

export function EarningsExplanation({ snap }: { snap: Snapshot }) {
  const h = snap.results.derived.ttm?.hundred_yuan;
  const anyComplete = snap.completeness.ttm === "complete" || snap.completeness.fy1 === "complete";
  if (!anyComplete) return null;
  const amt = h ? Math.abs(Number(h.amount)).toFixed(2) : null;
  return (
    <section aria-label="盈利解释" className="explain">
      {h && (
        <p data-testid="hundred-yuan">
          {h.loss ? `投入100元，对应年化亏损 ${amt}元（TTM）。` : `投入100元，对应年化盈利 ${amt}元（TTM）。`}
        </p>
      )}
      <p className="note">注意：TTM 与 FY1 使用不同盈利口径，估值差异不代表投资回报。</p>
    </section>
  );
}
