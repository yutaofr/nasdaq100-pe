"""One command for a real-data refresh: holdings file → SEC facts → official closes → FY1 forecasts →
research input → import → local research release.

    python scripts/refresh_real.py --holdings ~/Downloads/qqq-holdings.json
    python scripts/refresh_real.py --base-input ~/ndx-pe-data/inputs/research-D/research-input.json   # 补跑

It only chains the existing steps; every gate stays where it was. The holdings file is the JSON the
Invesco "All QQQ holdings" page loads, saved by hand. Its effectiveDate becomes both W and D (a weekend or
holiday date maps to the last trading day before it, see normalize.holdings.basket_date), so run this
within five trading days of that date (the Nasdaq NOCP endpoint returns no older closes).
A step that fails stops the run; already archived evidence is reused on the next run.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(step: str, cmd: list[str], env: dict, ok_codes=(0,)) -> dict:
    print(f"== {step}", flush=True)
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if r.returncode not in ok_codes:
        sys.stderr.write(r.stdout[-4000:] + r.stderr[-4000:])
        raise SystemExit(f"步骤失败：{step}（退出码 {r.returncode}）")
    try:
        return json.loads(r.stdout)
    except ValueError:
        return {}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--holdings", type=Path, help="手工保存的 Invesco QQQ 持仓 JSON")
    g.add_argument("--base-input", type=Path, help="已归档的篮子输入（跳过持仓归档与 SEC 刷新，用于补跑）")
    p.add_argument("--data-dir", type=Path, default=Path.home() / "ndx-pe-data",
                   help="数据目录（其下 store/ 为 DATA_ROOT，inputs/ 放证据与输入）")
    p.add_argument("--exclude", action="append", default=[], metavar="TICKER=REASON",
                   help="人工裁定不纳入 TTM 净利润路径的证券，可重复")
    p.add_argument("--reason", help="同一 D 已有快照时的修订原因")
    p.add_argument("--nocp-response", action="append", default=[], metavar="TICKER=FILE",
                   help="保存的 Nasdaq NOCP 原始响应，证券与日期校验后补录；可重复")
    p.add_argument("--no-publish", action="store_true", help="只导入生成快照，不构建发布")
    a = p.parse_args()

    sys.path.insert(0, str(HERE.parent / "src"))
    from nasdaq100_pe.calendar import TradingCalendar
    from nasdaq100_pe.normalize.holdings import basket_date
    cal = TradingCalendar.load()
    if a.holdings:
        h = json.loads(a.holdings.read_bytes())
        target, basis = basket_date(h, cal)
        if basis != "effectiveDate":
            print(f"持仓 effectiveDate {h['effectiveDate']} 不是交易日；篮子日/价格日取 {target}（依据：{basis}）", flush=True)
    else:
        target = json.loads(a.base_input.read_bytes())["weights"]["date"]
    if not cal.is_trading_day(datetime.fromisoformat(target).date()):
        raise SystemExit(f"价格日 {target} 不是交易日，未发起任何请求")
    store = Path(os.environ.get("NDX_PE_DATA_ROOT") or a.data_dir / "store")
    evidence = a.data_dir / "inputs" / "evidence"
    out = a.data_dir / "inputs" / f"research-{target}"
    env = dict(os.environ, NDX_PE_DATA_ROOT=str(store),
               PYTHONPATH=os.pathsep.join(filter(None, [str(HERE.parent / "src"), os.environ.get("PYTHONPATH")])))
    py = [sys.executable]
    cli = py + ["-m", "nasdaq100_pe.cli"]

    out.mkdir(parents=True, exist_ok=True)
    base = a.base_input or out / "research-input.json"
    if a.holdings:
        run("归档持仓并刷新 SEC companyfacts", py + [str(HERE / "collect_real_research.py"), "--holdings", str(a.holdings),
            "--evidence", str(evidence), "--output", str(out), "--store", str(store), "--target-date", target, "--earnings"], env)
    nocp = run("采集 Nasdaq 官方收盘价", py + [str(HERE / "collect_nocp.py"), "--input", str(base), "--evidence", str(evidence),
               "--target-date", target, "--index", str(out / "nocp-index.json")]
               + [arg for value in a.nocp_response for arg in ("--response", value)], env)
    if nocp.get("latest_published"):
        raise SystemExit(f"Nasdaq 尚未发布 {target} 的官方收盘价（接口最新交易日为 {nocp['latest_published']}），"
                         "已在第一只证券后停止（未导入、未发布）。这不是访问被拒；等来源发布后原样重跑即可。")
    if not nocp.get("with_close"):
        raise SystemExit(f"没有取到任何官方收盘价，已停止（未导入、未发布）。接口答复：{nocp.get('problems')}\n"
                         "HTTP 403/429 表示 Nasdaq 拒绝了本机的请求；重跑不保证恢复。"
                         "可通过 --nocp-response TICKER=FILE 补录保存的 Nasdaq NOCP 原始 JSON。"
                         "文件必须含该证券、目标日期和 Nasdaq Closing Price；不接受手写价格。")
    fy1 = run("采集 FY1 一致预期", py + [str(HERE / "collect_fy1.py"), "--input", str(base), "--evidence", str(evidence),
              "--index", str(out / "fy1-index.json")], env)
    observed = datetime.now(timezone.utc).isoformat()
    build_cmd = py + [str(HERE / "build_research_v2.py"), "--base-input", str(base), "--nocp-index", str(out / "nocp-index.json"),
                      "--fy1-index", str(out / "fy1-index.json"), "--evidence", str(evidence), "--store", str(store),
                      "--price-date", target, "--observed-at", observed, "--output", str(out)]
    for x in a.exclude:
        build_cmd += ["--exclude", x]
    built = run("生成研究输入", build_cmd, env)
    final = out / "research-input-v2.json"
    run("校验", cli + ["validate", "--input", str(final)], env)
    imp_cmd = cli + ["import", "--file", str(final), "--basket-date", target, "--price-date", target, "--observed-at", observed]
    if a.reason:
        imp_cmd += ["--reason", a.reason]
    imp = run("导入并计算", imp_cmd, env)
    sid = imp.get("snapshot_id")
    summary = {"D": target, "snapshot_id": sid, "completeness": imp.get("completeness"),
               "price_missing": built.get("price_missing"), "ttm_rows": built.get("ttm_rows"),
               "ttm_not_ok": built.get("ttm_not_ok"), "fy1_rows": built.get("fy1_rows"), "fy1_not_ok": built.get("fy1_not_ok"),
               "nocp_problems": nocp.get("problems"), "fy1_fetch_problems": fy1.get("problems"),
               "input": str(final), "coverage_report": str(out / "coverage-report-v2.csv")}
    if sid:
        snap = json.loads((store / "snapshots" / f"{sid}.json").read_bytes()) if (store / "snapshots" / f"{sid}.json").exists() else None
        if snap:
            summary["displayed"] = {k: {"eligibility": snap["results"]["metrics"][k]["eligibility"],
                                        "full_pe": snap["results"]["metrics"][k]["pe"],
                                        "coverage_ratio": snap["results"]["metrics"][k]["coverage_ratio"],
                                        "covered_part_pe": (snap["subsets"].get(k) or {}).get("pe"),
                                        "covered_part_shown": (snap["subsets"].get(k) or {}).get("display_qualified")}
                                    for k in ("ttm", "fy1")}
        if not a.no_publish:
            summary["release"] = run("构建并发布研究页", cli + ["build-local", "--snapshot", sid, "--data-mode", "real"], env)
    print(json.dumps(summary, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
