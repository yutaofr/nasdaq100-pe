import { useRelease } from "../data/ReleaseProvider";
import { PublishedMetricCard } from "../components/PublishedMetricCard";
import type { MetricKind } from "../data/types";

const SECTIONS: { kind: MetricKind; title: string }[] = [
  { kind: "trailing_pe", title: "滚动 PE（来源公布）" },
  { kind: "forward_pe", title: "Forward PE（来源公布）" },
];

export function PublishedPage({ now }: { now: Date }) {
  const { phase, release, error } = useRelease();
  const intro = <><h2>外部估值对照（来源公布，非本站自算）</h2><p className="note">此页仅供对照；来源公布的 PE 不进入首页自算结果，也不填补自算数据缺口。</p></>;
  if (phase === "loading") return <>{intro}<p>加载中…</p></>;
  if (!release) {
    if (phase === "error") return <>{intro}<p role="alert">无法读取已发布数据：{error}</p></>;
    return <>{intro}<p>尚无已发布数据。请先用命令行导入并构建引用指标；自算首页不受影响。</p></>;
  }
  return (
    <>
      {intro}
      {error && <p role="alert" className="alert">刷新失败，当前显示上一可核实版本：{error}</p>}
      {SECTIONS.map(({ kind, title }) => {
        const list = release.observations.series.filter((s) => s.observations[0]?.metric_kind === kind);
        return (
          <section key={kind} aria-label={title} className="section">
            <h2>{title}</h2>
            {list.length === 0 ? (
              <p className="empty">暂无该类来源数据（不以另一类或研究结果替代）。</p>
            ) : (
              <div className="grid">
                {list.map((s) => <PublishedMetricCard key={s.series_key} series={s} checks={release.checks.checks} now={now} />)}
              </div>
            )}
          </section>
        );
      })}
      <section aria-label="方法与限制" className="section">
        <h2>{release.method.title}</h2>
        <ul>{release.method.notes.map((n) => <li key={n}>{n}</li>)}</ul>
      </section>
    </>
  );
}
