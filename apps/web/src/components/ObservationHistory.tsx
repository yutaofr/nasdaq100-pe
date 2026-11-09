import type { Series } from "../data/types";
import { formatUtc, seriesCsv } from "../data/format";

function download(name: string, text: string) {
  try {
    const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url; a.download = name; a.click();
    URL.revokeObjectURL(url);
  } catch { /* 无下载能力的环境 */ }
}

export function ObservationHistory({ series }: { series: Series }) {
  const n = series.observations.length;
  const p = series.observations[0].provider;
  return (
    <details className="history">
      <summary>观察历史（{n}）</summary>
      {n === 0 && <p>暂无观察记录。</p>}
      {n === 1 && <p>仅有 1 个观察点，继续积累后才可比较；不回填历史。</p>}
      {n >= 2 && (
        <div className="tablewrap">
          <table aria-label={`${p} 历史`}>
            <thead><tr><th scope="col">观察时间</th><th scope="col">数值（倍）</th><th scope="col">数据日期</th><th scope="col">备注</th></tr></thead>
            <tbody>
              {series.observations.map((o) => (
                <tr key={o.observation_id}><td>{formatUtc(o.observed_at)}</td><td>{o.value}</td><td>{o.source_as_of ?? "来源未注明"}</td><td>{o.superseded_by ? "已更正（见后续观察）" : ""}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <button type="button" onClick={() => download(`${p}-history.csv`, seriesCsv(series))}>导出 CSV</button>
    </details>
  );
}
