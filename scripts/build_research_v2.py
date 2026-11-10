"""Assemble a method-version-2 research input from already archived evidence. No network.

Takes the archived basket (universe, weights, sources and any reported-quarter-EPS rows already
adjudicated), adds one official-close row per archived Nasdaq NOCP response, and one net-income-path
TTM row per issuer whose cached SEC companyfacts yield a consistent selection. Securities that fail
any check get no row; the reason is written to the coverage report, never filled in.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime
from pathlib import Path

from nasdaq100_pe.dec import dstr
from nasdaq100_pe.normalize.net_income import PATH, SHARES_TAG, select_ttm_net_income

NOCP_PAGE = "https://www.nasdaq.com/market-activity/stocks/{t}/historical-nocp"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-input", type=Path, required=True)
    p.add_argument("--nocp-index", type=Path, required=True)
    p.add_argument("--store", type=Path, required=True)
    p.add_argument("--price-date", required=True)
    p.add_argument("--observed-at", required=True, help="T；晚于此日申报的事实不进入")
    p.add_argument("--exclude", action="append", default=[], metavar="TICKER=REASON",
                   help="人工裁定不纳入净利润路径的证券及原因")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()

    base = json.loads(a.base_input.read_text())
    idx = json.loads(a.nocp_index.read_text())
    D, T = date.fromisoformat(a.price_date), datetime.fromisoformat(a.observed_at)
    manual = dict(x.split("=", 1) for x in a.exclude)
    sources = {s["source_id"]: s for s in base["sources"]}
    have_price = {r["security_id"] for r in base.get("prices", [])}
    have_ttm = {r["security_id"] for r in base.get("earnings", []) if r["kind"] == "ttm"}
    prices, earnings, report = list(base.get("prices", [])), list(base.get("earnings", [])), []

    for s in base["universe"]["securities"]:
        sid, t, cik = s["security_id"], s["ticker"], s["issuer_id"]
        row = {"ticker": t, "security_id": sid, "price": "", "price_status": "", "ttm_path": "", "ttm_status": "",
               "ttm_reason": "", "latest_period_end": "", "net_income_tag": "", "flags": ""}
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
            meta = json.loads((a.store / "sec_cache" / f"{cik}.json").read_text())["current"]
            cf = json.loads((a.store / "raw" / meta["content_sha256"]).read_bytes())
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
        report.append(row)

    out = dict(base, method_version="2", sources=list(sources.values()), prices=prices, earnings=earnings)
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output / "research-input-v2.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    with (a.output / "coverage-report-v2.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, list(report[0])); w.writeheader(); w.writerows(report)
    print(json.dumps({"securities": len(report), "price_rows": len(prices), "ttm_rows": len(earnings),
                      "ttm_not_ok": {r["ticker"]: r["ttm_reason"] or r["ttm_status"] for r in report
                                     if r["ttm_status"] not in ("ok", "kept_from_base")},
                      "price_missing": [r["ticker"] for r in report if r["price_status"].startswith("missing")]},
                     indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
