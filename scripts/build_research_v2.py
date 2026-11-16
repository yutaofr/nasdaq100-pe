"""Assemble a method-version-2 research input from already archived evidence. No network.

Takes the archived basket (universe, weights, sources and any reported-quarter-EPS rows already
adjudicated), adds one official-close row per archived Nasdaq NOCP response, and one net-income-path
TTM row per issuer whose cached SEC companyfacts yield a consistent selection. With --fy1-index it also
adds one FY1 (next fiscal year) consensus row per security from the archived Nasdaq forecast responses.
Securities that fail any check get no row; the reason is written to the coverage report, never filled in.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime
from pathlib import Path

from nasdaq100_pe.dec import dstr
from nasdaq100_pe.normalize.fy1 import select_fy1
from nasdaq100_pe.normalize.net_income import PATH, SHARES_TAG, select_ttm_net_income

NOCP_PAGE = "https://www.nasdaq.com/market-activity/stocks/{t}/historical-nocp"
FY1_PROVIDER_NOTE = ("Nasdaq 个股 Earnings 页的一致预期 EPS（带星号口径）；口径依据为同一来源同一星号口径的"
                     "已报告 EPS 与 SEC GAAP 稀释 EPS 的逐季对照，见 comparison")


def _json(path: Path):
    return json.loads(path.read_bytes())


def fy1_row(sid: str, ticker: str, entry: dict, evidence: Path, cf: dict, price_date: str, D: date, T: datetime):
    """返回 (盈利行|None, 来源|None, 状态, 原因, 财年末, 标记)。只读已归档响应。"""
    fc, sp = entry.get("forecast") or {}, entry.get("surprise") or {}
    if not fc.get("sha256"):
        return None, None, "missing", fc.get("reason") or "NOT_FETCHED", "", ""
    d = evidence / "nasdaq-forecast"
    surprise = _json(d / sp["file"]) if sp.get("sha256") else None
    sel = select_fy1(_json(d / fc["file"]), surprise, cf, D, T.date())
    if sel.status != "ok":
        return None, None, sel.status, ",".join(sel.reasons), "", ""
    basis = sel.basis_evidence
    compared = basis["quarters_differing_from_gaap"] + basis["quarters_equal_to_gaap"]
    flags = ["FORECAST_FRESHNESS_UNVERIFIED"]
    if sel.estimates < 3:
        flags.append("FEW_ESTIMATES")
    if compared == 0:
        flags.append("BASIS_COMPARISON_UNAVAILABLE")
    elif basis["quarters_differing_from_gaap"] == 0:
        flags.append("BASIS_EQUALS_GAAP_IN_SAMPLE")
    src = f"nasdaq-forecast-{ticker.lower()}"
    source = {"source_id": src, "content_sha256": fc["sha256"], "fetched_at": fc["fetched_at"], "locator": fc["url"]}
    row = {"security_id": sid, "kind": "fy1", "eps": dstr(sel.eps), "accounting_basis": "normalized", "currency": "USD",
           "unit": "per_share", "statistic": "mean", "forecast_period": "FY1", "fiscal_year_end": sel.fiscal_year_end,
           "split_basis_date": price_date, "fetched_at": fc["fetched_at"], "checked_at": fc["fetched_at"],
           "source_id": src, "quality_flags": flags, "forecast_period_evidence": sel.period_evidence,
           "normalized_evidence": {"note": FY1_PROVIDER_NOTE, "surprise_content_sha256": sp["sha256"],
                                   "surprise_locator": sp["url"], "comparison": basis},
           "evidence": {"content_sha256": fc["sha256"],
                        "locator": f"{fc['url']}#yearlyForecast.rows[fiscalEnd={sel.period_evidence['source_label']}]"}}
    return row, source, "ok", "", sel.fiscal_year_end, ",".join(flags)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-input", type=Path, required=True)
    p.add_argument("--nocp-index", type=Path, required=True)
    p.add_argument("--store", type=Path, required=True)
    p.add_argument("--price-date", required=True)
    p.add_argument("--observed-at", required=True, help="T；晚于此日申报的事实不进入")
    p.add_argument("--exclude", action="append", default=[], metavar="TICKER=REASON",
                   help="人工裁定不纳入净利润路径的证券及原因")
    p.add_argument("--fy1-index", type=Path, help="collect_fy1.py 的索引；给出时生成 FY1 行")
    p.add_argument("--evidence", type=Path, help="证据目录（含 nasdaq-forecast/）；与 --fy1-index 同时给出")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if bool(a.fy1_index) != bool(a.evidence):
        p.error("--fy1-index 与 --evidence 须同时给出")
    fy1_idx = _json(a.fy1_index) if a.fy1_index else None

    base = json.loads(a.base_input.read_text())
    idx = json.loads(a.nocp_index.read_text())
    D, T = date.fromisoformat(a.price_date), datetime.fromisoformat(a.observed_at)
    manual = dict(x.split("=", 1) for x in a.exclude)
    sources = {s["source_id"]: s for s in base["sources"]}
    have_price = {r["security_id"] for r in base.get("prices", [])}
    have_ttm = {r["security_id"] for r in base.get("earnings", []) if r["kind"] == "ttm"}
    have_fy1 = {r["security_id"] for r in base.get("earnings", []) if r["kind"] == "fy1"}
    prices, earnings, report = list(base.get("prices", [])), list(base.get("earnings", [])), []
    cache: dict = {}

    def facts(cik: str):
        if cik not in cache:
            meta = _json(a.store / "sec_cache" / f"{cik}.json")["current"]
            cache[cik] = (meta, _json(a.store / "raw" / meta["content_sha256"]))
        return cache[cik]

    for s in base["universe"]["securities"]:
        sid, t, cik = s["security_id"], s["ticker"], s["issuer_id"]
        row = {"ticker": t, "security_id": sid, "price": "", "price_status": "", "ttm_path": "", "ttm_status": "",
               "ttm_reason": "", "latest_period_end": "", "net_income_tag": "", "flags": "",
               "fy1_status": "", "fy1_reason": "", "fy1_fiscal_year_end": "", "fy1_flags": ""}
        n = idx.get(t) or {}
        if sid in have_price:
            row["price_status"] = "kept_from_base"
            row["price"] = next(r["close"] for r in prices if r["security_id"] == sid)
        elif n.get("close"):
            src = f"nasdaq-nocp-{t.lower()}"
            sources[src] = {"source_id": src, "content_sha256": n["sha256"], "fetched_at": n["fetched_at"], "locator": n["url"]}
            prices.append({"security_id": sid, "date": a.price_date, "close": n["close"], "price_type": "regular_close",
                           "session": "regular", "adjustment": "raw", "feed": "exchange_official", "currency": "USD",
                           "split_basis_date": a.price_date, "fetched_at": n["fetched_at"], "checked_at": n["fetched_at"],
                           "source_id": src, "evidence_sha256": n["sha256"],
                           "locator": f"{n['url']}#nocp.nocpTable[date={D.strftime('%m/%d/%Y')}] ; page {NOCP_PAGE.format(t=t.lower())}",
                           "split_basis_evidence": {"locator": "未调整的当日官方收盘价；股数口径由盈利行的封面股数/稀释股数比值核对"}})
            row["price_status"], row["price"] = "nocp", n["close"]
        else:
            row["price_status"] = "missing:" + (n.get("reason") or "NOT_FETCHED")

        if sid in have_ttm:
            row["ttm_path"], row["ttm_status"] = "reported_quarter_eps_sum", "kept_from_base"
        elif t in manual:
            row["ttm_path"], row["ttm_status"], row["ttm_reason"] = PATH, "manual_exclusion", manual[t]
        else:
            meta, cf = facts(cik)
            sel = select_ttm_net_income(cf, D, T.date())
            row.update(ttm_path=PATH, ttm_status=sel.status, ttm_reason=",".join(sel.reasons),
                       latest_period_end=sel.latest_period_end or "", flags=",".join(sel.flags),
                       net_income_tag=sel.components.get("net_income_tag", ""))
            if sel.status == "ok":
                src = f"sec-{cik}"
                sources[src] = {"source_id": src, "content_sha256": meta["content_sha256"],
                                "fetched_at": meta["content_fetched_at"],
                                "locator": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"}
                earnings.append({"security_id": sid, "kind": "ttm", "profit": dstr(sel.profit), "shares": dstr(sel.shares),
                                 "accounting_basis": "gaap", "currency": "USD", "split_basis_date": a.price_date,
                                 "latest_quarter_end": sel.latest_period_end, "fetched_at": meta["content_fetched_at"],
                                 "checked_at": meta["checked_at"], "calculation_path": PATH, "source_id": src,
                                 "quality_flags": sel.flags,
                                 "evidence": {"cik": cik, "content_sha256": meta["content_sha256"],
                                              "locator": f"us-gaap/{sel.components['net_income_tag']}/USD ; us-gaap/{SHARES_TAG}/shares",
                                              "components": sel.components}})
        if fy1_idx is not None:
            if sid in have_fy1:
                row["fy1_status"] = "kept_from_base"
            else:
                frow, fsrc, row["fy1_status"], row["fy1_reason"], row["fy1_fiscal_year_end"], row["fy1_flags"] = \
                    fy1_row(sid, t, fy1_idx.get(t) or {}, a.evidence, facts(cik)[1], a.price_date, D, T)
                if frow:
                    sources[fsrc["source_id"]] = fsrc
                    earnings.append(frow)
        report.append(row)

    out = dict(base, method_version="2", sources=list(sources.values()), prices=prices, earnings=earnings)
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output / "research-input-v2.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    with (a.output / "coverage-report-v2.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, list(report[0])); w.writeheader(); w.writerows(report)
    print(json.dumps({"securities": len(report), "price_rows": len(prices),
                      "ttm_rows": sum(1 for e in earnings if e["kind"] == "ttm"),
                      "fy1_rows": sum(1 for e in earnings if e["kind"] == "fy1"),
                      "fy1_not_ok": {r["ticker"]: r["fy1_reason"] or r["fy1_status"] for r in report
                                     if r["fy1_status"] not in ("ok", "kept_from_base", "")},
                      "ttm_not_ok": {r["ticker"]: r["ttm_reason"] or r["ttm_status"] for r in report
                                     if r["ttm_status"] not in ("ok", "kept_from_base")},
                      "price_missing": [r["ticker"] for r in report if r["price_status"].startswith("missing")]},
                     indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
