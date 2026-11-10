import { useMemo, useState } from "react";
import { useResearch } from "../data/research";
import { formatUtc } from "../data/format";
import { QualityBanner } from "../components/QualityBanner";
import { EarningsExplanation, OverviewGrid } from "../components/OverviewGrid";
import { SectorView } from "../components/SectorView";
import { ConstituentTable } from "../components/ConstituentTable";
import { ResearchHistory } from "../components/ResearchHistory";
import type { Snapshot } from "../data/types";

function Labels({ snap }: { snap: Snapshot }) {
  const c = snap.context;
  return (
    <div className="labels">
      {snap.basket.mode.includes("proxy") && <p className="badge">纳指100估值估算（QQQ股票持仓代理）</p>}
      {c.basket_policy === "fixed" && <p className="badge">QQQ历史权重固定篮子研究</p>}
      {c.freshness_policy === "weekly" && <p className="badge">非同步周度观察</p>}
      <p className="dates"><span>篮子日 W：{c.W}</span> · <span>目标价格日 D：{c.D}</span> · <span>观察时点 T：{formatUtc(c.T)}</span></p>
      <p className="muted">模式：{c.analysis_profile} / {c.basket_policy} / {c.coverage_policy} / {c.freshness_policy}。
        {snap.basket.index_comparability === "unverified" ? "指数可比性：未验证。" : ""}代理结果不等同于官方指数估值。</p>
    </div>
  );
}

export function ResearchPage() {
  const { phase, release, error } = useResearch();
  const [pick, setPick] = useState<string | null>(null);
  const [sector, setSector] = useState<string | null>(null);
  const snaps = release?.research.snapshots ?? [];
  const current = useMemo(() => {
    if (!snaps.length) return null;
    return snaps.find((s) => s.snapshot_id === pick) ?? [...snaps].sort((a, b) => b.context.T.localeCompare(a.context.T) || b.revision_seq - a.revision_seq)[0];
  }, [snaps, pick]);

  const head = <>
    <h2>自主计算研究（观察时点研究）</h2>
    <p className="note">按成分权重计算盈利收益率：TTM / FY1 收益率 = Σ（权重 × 每股盈利 ÷ 同期股价），组合 PE = 1 ÷ 组合收益率。亏损证券的负盈利保留；缺失值不填零。</p>
    <p className="note">TTM 优先使用四个已报告单季 GAAP 稀释 EPS 之和；缺单季值时改用已报告归母净利润（全年 + 本年累计 − 上年同期）除以稀释股数与股价之积，不推算单季 EPS。FY1 使用下一财年 normalized 一致预期 EPS，不以 NTM 或来源公布的 Forward PE 代替。</p>
    <p className="note">完整篮子、有效价格和逐证券盈利全部齐备才显示完整组合 PE；未齐备但覆盖权重达到展示门槛时，显示“已覆盖部分”的 PE 并标明覆盖率，未达到则留空。两种口径分别判断。</p>
  </>;
  if (phase === "loading") return <section aria-label="自主计算研究">{head}<p>加载中…</p></section>;
  if (!release || !current) {
    return (
      <section aria-label="自主计算研究">{head}
        {phase === "error" && <p role="alert">无法读取研究数据：{error}</p>}
        <p>暂无合格的真实研究输入，未形成完整自算 PE。缺口：完整篮子权重、有效收盘价、逐证券 TTM GAAP 盈利与 FY1 normalized 预测尚未全部导入或验证；已设置目标价格日 D 不代表价格已取得。</p>
      </section>
    );
  }
  return (
    <section aria-label="自主计算研究">
      {head}
      {error && <p role="alert" className="alert">研究数据刷新失败，当前显示上一可核实版本：{error}</p>}
      <label>选择观察点{" "}
        <select value={current.snapshot_id} onChange={(e) => { setPick(e.target.value); setSector(null); }}>
          {snaps.map((s) => <option key={s.snapshot_id} value={s.snapshot_id}>{s.context.D} · T {formatUtc(s.context.T)} · 修订{s.revision_seq}</option>)}
        </select>
      </label>
      <Labels snap={current} />
      <QualityBanner snap={current} />
      <OverviewGrid snap={current} />
      <EarningsExplanation snap={current} />
      <SectorView snap={current} selected={sector} onSelect={setSector} />
      <ConstituentTable snap={current} sector={sector} />
      <ResearchHistory snaps={snaps} />
      <section aria-label="方法" className="section"><h3>{release.method.title}</h3><ul>{release.method.notes.map((n) => <li key={n}>{n}</li>)}</ul></section>
    </section>
  );
}
