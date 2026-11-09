import type { CheckEvent, Series } from "../data/types";
import { checkStatus, formatUtc, label, safeHref } from "../data/format";
import { ObservationHistory } from "./ObservationHistory";

export function PublishedMetricCard({ series, checks, now }: { series: Series; checks: CheckEvent[]; now: Date }) {
  const live = series.observations.filter((x) => !x.superseded_by);   // 被更正的原值不当作最新
  const o = live[live.length - 1] ?? series.observations[series.observations.length - 1];
  const st = checkStatus(series, checks, now);
  const href = safeHref(o.source_url);
  return (
    <article className="card" data-testid="metric-card">
      <p className="provider">{o.provider}</p>
      <p className="orig">{o.metric_label_original}</p>
      <p className="value"><span>{o.value}</span> 倍</p>
      <dl className="meta">
        <dt>数据日期</dt>
        <dd>{o.source_as_of ? <span>{o.source_as_of}</span> : <span>来源未注明，观察于 {formatUtc(o.observed_at)}</span>}</dd>
        <dt>观察时间</dt><dd>{formatUtc(o.observed_at)}</dd>
        <dt>口径限制</dt>
        <dd>期间：{label("period", o.period_basis)}；会计：{label("accounting", o.accounting_basis)}；亏损处理：{label("loss", o.loss_treatment)}；方法披露：{label("method", o.methodology_status)}</dd>
        <dt>最近检查</dt>
        <dd>{st.lastCheck ? formatUtc(st.lastCheck) : "尚无带证据的检查记录"}</dd>
      </dl>
      {st.overdue && <p className="overdue" role="status">周度检查逾期</p>}
      <p>
        {href ? (
          <a href={href} target="_blank" rel="noopener noreferrer" aria-label={`来源链接：${o.provider}`}>来源链接</a>
        ) : (
          <span>来源链接不可用（非 HTTP(S) 协议已拦截）</span>
        )}
        {" · "}原件哈希 <code>{o.evidence_sha256.slice(0, 12)}…</code>，定位 {o.evidence_locator}
      </p>
      <ObservationHistory series={series} />
    </article>
  );
}
