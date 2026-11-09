import type { Snapshot } from "../data/types";
import { fmtPct, fmtPe } from "../data/fmt";

export function SectorView({ snap, selected, onSelect }: { snap: Snapshot; selected: string | null; onSelect: (s: string | null) => void }) {
  const fy = Object.fromEntries(snap.results.metrics.fy1.sectors.map((s) => [s.name, s]));
  return (
    <section aria-label="行业" className="section">
      <h3>行业</h3>
      {selected && <button type="button" onClick={() => onSelect(null)}>清除行业筛选</button>}
      <div className="tablewrap">
        <table aria-label="行业汇总">
          <thead><tr><th scope="col">行业</th><th scope="col">权重</th><th scope="col">TTM PE</th><th scope="col">FY1 PE</th><th scope="col">说明</th></tr></thead>
          <tbody>
            {snap.results.metrics.ttm.sectors.map((s) => {
              const f = fy[s.name];
              const pe = (x: typeof s | undefined) => !x ? "—" : x.pe ? fmtPe(x.pe) : x.pe_state === "non_positive" ? "N/M（盈利非正）" : "—";
              return (
                <tr key={s.name} aria-selected={selected === s.name}>
                  <td><button type="button" aria-pressed={selected === s.name} aria-label={`筛选行业 ${s.name}`} onClick={() => onSelect(selected === s.name ? null : s.name)}>{s.name}</button></td>
                  <td><span className="bar" style={{ width: `${Math.min(100, Number(s.weight) * 100)}%` }} aria-hidden /> {fmtPct(s.weight)}</td>
                  <td>{pe(s)}</td><td>{pe(f)}</td><td>{s.note || "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
