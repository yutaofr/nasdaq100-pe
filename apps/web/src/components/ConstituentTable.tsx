import { Fragment, useMemo, useState } from "react";
import type { Snapshot } from "../data/types";
import { cmpDecimal, fmtPct, fmtPe, fmtPoints, reasonText } from "../data/fmt";

type SortKey = "weight" | "ttm_pe" | "fy1_pe" | "ttm_c" | "fy1_c";

export function ConstituentTable({ snap, sector }: { snap: Snapshot; sector: string | null }) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "weight", dir: -1 });
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<"all" | "valid" | "missing">("all");
  const [open, setOpen] = useState<string | null>(null);
  const { ttm, fy1 } = snap.results.metrics;

  const rows = useMemo(() => snap.securities.map((s) => ({ s, t: ttm.securities[s.security_id], f: fy1.securities[s.security_id] })), [snap, ttm, fy1]);
  const val = (r: (typeof rows)[number], k: SortKey): string | null =>
    k === "weight" ? r.t.weight : k === "ttm_pe" ? r.t.pe : k === "fy1_pe" ? r.f.pe : k === "ttm_c" ? r.t.contribution_points : r.f.contribution_points;

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const list = rows.filter((r) =>
      (!needle || r.s.name.toLowerCase().includes(needle) || r.s.ticker.toLowerCase().includes(needle)) &&
      (!sector || (r.s.sector ?? "未分类") === sector) &&
      (status === "all" || (status === "valid" ? r.t.valid : !r.t.valid)));
    return [...list].sort((a, b) => {
      const x = val(a, sort.key), y = val(b, sort.key);
      if (x === null && y !== null) return 1;       // 空值始终置底
      if (y === null && x !== null) return -1;
      const c = x !== null && y !== null ? cmpDecimal(x, y) * sort.dir : 0;
      return c || a.s.security_id.localeCompare(b.s.security_id);
    });
  }, [rows, q, sector, status, sort]);

  const th = (label: string, key?: SortKey) => (
    <th scope="col" aria-sort={key && sort.key === key ? (sort.dir === 1 ? "ascending" : "descending") : undefined}>
      {key ? (
        <button type="button" aria-label={`按 ${label} 排序`} onClick={() => setSort((p) => p.key === key ? { key, dir: (p.dir * -1) as 1 | -1 } : { key, dir: key === "weight" ? -1 : 1 })}>{label}</button>
      ) : label}
    </th>
  );
  const pe = (r: { pe: string | null; valid: boolean; flags: string[] }) =>
    !r.valid ? `— ${reasonText(r.flags)}` : r.pe === null ? "— EPS 为 0" : Number(r.pe) < 0 ? "亏损" : fmtPe(r.pe);
  const ctr = (r: { valid: boolean; contribution_points: string | null }) => (r.valid ? fmtPoints(r.contribution_points) : "—");

  return (
    <section aria-label="成分明细" className="section">
      <h3>成分明细</h3>
      <div className="filters">
        <label>搜索名称或代码 <input type="search" aria-label="搜索名称或代码" value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <label>状态 <select value={status} onChange={(e) => setStatus(e.target.value as any)}>
          <option value="all">全部</option><option value="valid">TTM有效</option><option value="missing">TTM缺失</option></select></label>
        <span>显示 {shown.length} / {rows.length}</span>
      </div>
      <p className="hint">表格可横向滑动（手机上名称列固定）。</p>
      <div className="tablewrap tall">
        <table aria-label="成分明细">
          <thead><tr>{th("序号")}{th("名称/代码")}{th("权重", "weight")}{th("TTM PE", "ttm_pe")}{th("FY1 PE", "fy1_pe")}{th("TTM贡献", "ttm_c")}{th("FY1贡献", "fy1_c")}{th("状态")}</tr></thead>
          <tbody>
            {shown.map((r, i) => (
              <Fragment key={r.s.security_id}>
                <tr>
                  <td>{i + 1}</td>
                  <td className="sticky">{r.s.name} <span className="muted">{r.s.ticker}</span></td>
                  <td>{fmtPct(r.t.weight)}</td>
                  <td>{pe(r.t)}</td><td>{pe(r.f)}</td><td>{ctr(r.t)}</td><td>{ctr(r.f)}</td>
                  <td>TTM {r.t.valid ? "有效" : "缺失"} · FY1 {r.f.valid ? "有效" : "缺失"}{" "}
                    <button type="button" aria-expanded={open === r.s.security_id} onClick={() => setOpen(open === r.s.security_id ? null : r.s.security_id)}>详情</button></td>
                </tr>
                {open === r.s.security_id && (
                  <tr><td colSpan={8}>
                    <p>精确权重：{r.t.weight}；行业：{r.s.sector ?? "未分类"}；发行人：{r.s.issuer_id}；股类：{r.s.share_class}</p>
                    <p>TTM 收益率：{r.t.yield_ ?? "—"}；FY1 收益率：{r.f.yield_ ?? "—"}</p>
                    <p>诊断：{snap.diagnostics.filter((d) => d.security_id === r.s.security_id).map((d) => d.code).join("、") || "无"}</p>
                  </td></tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
