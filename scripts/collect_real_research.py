"""Archive a QQQ holdings basket and screen primary-source research inputs.

This command never promotes candidate price or EPS values into qualified rows.
The output research input intentionally carries an empty price/earnings set until
the price feed, split basis and four-quarter EPS can be established separately.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from nasdaq100_pe.adapters.sec import SecClient, fetch_earnings
from nasdaq100_pe.archive.store import ArchiveStore
from nasdaq100_pe.validate.earnings import validate_earnings
from nasdaq100_pe.identity.models import SecurityIdentity


HOLDINGS_URL = ("https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/"
                "holdings/fund?idType=ticker&interval=monthly&productType=ETF")
EQUITY_TYPES = {"Common Stock", "American Depository Receipt", "American Depository Receipt - NY"}
NON_EQUITY = {"Currency": "cash", "Index Future": "derivative",
              "Currency Collateral": "cash", "Synthetic Cash": "other"}
NASDAQ_URL = "https://api.nasdaq.com/api/quote/{ticker}/historical?assetclass=stocks&limit=10&fromdate={date}&todate={end}"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def archive(path: Path, body: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != body:
        raise ValueError(f"Evidence is immutable: {path}")
    if not path.exists():
        path.write_bytes(body)
    return digest(body)


def sec_user_agent() -> str:
    email = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True, check=True).stdout.strip()
    if not email or "@" not in email:
        raise ValueError("Set git user.email to a reachable SEC Fair Access contact")
    return f"Nasdaq100PE personal research {email}"


def sec_ticker_map(client: SecClient, evidence: Path) -> tuple[dict[str, str], dict]:
    body = client.get(SEC_TICKERS_URL)
    h = archive(evidence / f"sec-company-tickers-{digest(body)}.json", body)
    mapping = {item["ticker"].upper(): str(item["cik_str"]).zfill(10)
               for item in json.loads(body).values()}
    return mapping, {"source_id": "sec-tickers", "content_sha256": h,
                     "fetched_at": stamp(), "locator": SEC_TICKERS_URL}


def nasdaq_close(ticker: str, target_date: str, evidence: Path) -> dict:
    from datetime import date, timedelta
    end = (date.fromisoformat(target_date) + timedelta(days=1)).isoformat()
    url = NASDAQ_URL.format(ticker=urllib.parse.quote(ticker, safe=""), date=target_date, end=end)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            body = response.read()
            http = response.status
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"price_status": "fetch_error", "price_error": type(exc).__name__, "price_url": url}
    h = archive(evidence / "nasdaq-historical" / f"{ticker}-{target_date}-{digest(body)}.json", body)
    result = {"price_http": http, "price_sha256": h, "price_url": url,
              "price_observed_at": stamp(), "price_status": "candidate_close_last_unverified"}
    try:
        obj = json.loads(body)
        rows = obj["data"]["tradesTable"]["rows"]
        wanted = datetime.fromisoformat(target_date).strftime("%m/%d/%Y")
        row = next(r for r in rows if r["date"] == wanted)
        close = re.sub(r"[^0-9.]", "", row["close"])
        Decimal(close)
        result["candidate_close_usd"] = close
    except (KeyError, TypeError, StopIteration, ValueError):
        result["price_status"] = "missing_or_unparseable"
    return result


def collect(holdings_file: Path, evidence: Path, output: Path, store: ArchiveStore,
            target_date: str, prices: bool, earnings: bool) -> dict:
    raw = holdings_file.read_bytes()
    holdings_hash = archive(evidence / f"invesco-qqq-holdings-{digest(raw)}.json", raw)
    obj = json.loads(raw)
    w = obj["effectiveDate"]
    if w != target_date or obj.get("totalNumberOfHoldings") != len(obj["holdings"]):
        raise ValueError("Target date or holdings row count differs from source")
    client = SecClient(user_agent=sec_user_agent(), min_interval=0.25)
    ciks, ticker_source = sec_ticker_map(client, evidence)
    fetched = datetime.fromtimestamp(holdings_file.stat().st_mtime, timezone.utc).isoformat()
    sources = [{"source_id": "invesco-qqq", "content_sha256": holdings_hash,
                "fetched_at": fetched, "locator": HOLDINGS_URL}, ticker_source]
    securities, weights, excluded, matrix = [], [], [], []
    sec_batches = {}
    for h in obj["holdings"]:
        ticker, typ = h.get("ticker"), h["securityTypeName"]
        weight = h.get("percentageOfTotalNetAssets")
        if typ not in EQUITY_TYPES:
            if typ not in NON_EQUITY:
                raise ValueError(f"Unclassified security type: {typ}")
            excluded.append({"label": h.get("issuerName") or ticker or typ,
                             "asset_class": NON_EQUITY[typ],
                             "weight": str(Decimal(str(weight)) / 100) if weight is not None else None})
            continue
        if not ticker or weight is None:
            raise ValueError("Equity requires symbol and weight")
        cik = ciks.get(ticker.upper())
        if not cik:
            raise ValueError(f"No current SEC CIK mapping for {ticker}")
        sid = f"QQQ:{ticker}"
        is_adr = typ != "Common Stock"
        securities.append({"security_id": sid, "issuer_id": cik, "share_class": "adr" if is_adr else "common",
                           "ticker": ticker, "name": h["issuerName"], "asset_class": "equity",
                           "cusip": h.get("cusip"), "is_adr": is_adr})
        weights.append({"security_id": sid, "weight": str(Decimal(str(weight)) / 100)})
        entry = {"ticker": ticker, "security_id": sid, "issuer_cik": cik, "security_type": typ,
                 "proxy_weight": str(Decimal(str(weight)) / 100),
                 "holdings_sha256": holdings_hash, "price_target_date": target_date,
                 "price_status": "not_requested", "ttm_status": "not_requested", "fy1_status": "no_qualified_source"}
        if prices:
            entry.update(nasdaq_close(ticker, target_date, evidence))
            time.sleep(0.2)
        if earnings:
            if cik not in sec_batches:
                try:
                    sec_batches[cik] = fetch_earnings(cik, store, client)
                except Exception as exc:
                    # One failed issuer must not erase the other 100 coverage rows.
                    sec_batches[cik] = exc
            batch = sec_batches[cik]
            if isinstance(batch, Exception):
                entry["ttm_status"] = "fetch_error"
                entry["ttm_reason"] = type(batch).__name__
            else:
                identity = SecurityIdentity(security_id=sid, issuer_id=cik,
                                            share_class="adr" if is_adr else "common",
                                            ticker=ticker, name=h["issuerName"],
                                            is_adr=is_adr, adr_ratio=None)
                check = validate_earnings(batch, [identity]).rows[0]
                entry.update({"sec_facts_sha256": batch.content_sha256,
                              "sec_checked_at": batch.checked_at,
                              "sec_content_fetched_at": batch.content_fetched_at,
                              "ttm_status": check["status"], "ttm_reason": check["reason"] or "",
                              "ttm_candidate_eps": check["eps"] or "",
                              "ttm_latest_quarter_end": check["latest_quarter_end"] or ""})
                if ticker == "HON" and check["status"] == "ok":
                    entry["ttm_status"] = "split_scope_unverified"
                    entry["ttm_reason"] = "2026-06-29 reverse split; 2025 Q4 fact predates split"
                    entry["split_evidence_url"] = "https://investor.honeywell.com/reverse-stock-split"
                # Eligible rows are intentionally not promoted here: SEC share/split scope,
                # target-date filing cutoff and a verified matching close remain outstanding.
        matrix.append(entry)
    output.mkdir(parents=True, exist_ok=True)
    basket = {"schema_version": "1", "method_version": "1", "data_mode": "real",
              "sources": sources, "universe": {"as_of": w, "source_id": "invesco-qqq",
                                              "listing_scope": "full", "securities": securities},
              "weights": {"mode": "qqq_equity_proxy", "date": w, "source_id": "invesco-qqq",
                          "items": weights, "excluded": excluded},
              "prices": [], "earnings": []}
    (output / "research-input.json").write_text(json.dumps(basket, indent=2, ensure_ascii=False) + "\n")
    with (output / "coverage-matrix.csv").open("w", newline="") as f:
        fields = list(dict.fromkeys(k for row in matrix for k in row))
        writer = csv.DictWriter(f, fields)
        writer.writeheader(); writer.writerows(matrix)
    summary = {"holdings_effective_date": w, "target_price_date": target_date,
               "holdings_sha256": holdings_hash, "holdings_count": len(obj["holdings"]),
               "equity_count": len(securities), "excluded_count": len(excluded),
               "equity_weight_raw": str(sum(Decimal(x["weight"]) for x in weights)),
               "known_excluded_weight_raw": str(sum(Decimal(x["weight"]) for x in excluded if x["weight"] is not None)),
               "unknown_excluded_count": sum(x["weight"] is None for x in excluded),
               "candidate_price_count": sum("candidate_close_usd" in row for row in matrix),
               "qualified_price_count": 0, "qualified_ttm_count": 0, "qualified_fy1_count": 0,
               "sec_facts_successful_issuers": sum(not isinstance(x, Exception) for x in sec_batches.values()),
               "sec_facts_requested_issuers": len(sec_batches),
               "reason": "Nasdaq daily Close/Last lacks verified split basis; SEC EPS share/split scope and filing cutoff unverified; FY1 source absent. HON has a documented 2026-06-29 reverse split affecting pre-split Q4 EPS.",
               "created_at": stamp()}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--holdings", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--store", type=Path, required=True)
    p.add_argument("--target-date", default="2026-11-05")
    p.add_argument("--prices", action="store_true")
    p.add_argument("--earnings", action="store_true")
    args = p.parse_args()
    print(json.dumps(collect(args.holdings, args.evidence, args.output, ArchiveStore(args.store),
                             args.target_date, args.prices, args.earnings), indent=2))


if __name__ == "__main__":
    main()
