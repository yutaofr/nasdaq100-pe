"""Archive Nasdaq Historical NOCP responses for every equity in a research input.

One request per ticker to the same endpoint the Nasdaq "Historical NOCP" page calls.
Responses are stored content-addressed; an index JSON records, per ticker, the hash,
the fetch time and the parsed "Nasdaq Closing Price" for the target date (or the reason
none was found). Nothing is retried on an HTTP refusal.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

NOCP_URL = "https://api.nasdaq.com/api/company/{ticker}/historical-nocp?timeframe=d5"


def parse_nocp(body: bytes, target: str) -> tuple[str | None, str]:
    """Return (close, reason). Duplicate rows for the date must agree."""
    try:
        obj = json.loads(body)
        data = obj["data"]
        if data["headers"]["price"] != "Nasdaq Closing Price":
            return None, "UNEXPECTED_PRICE_HEADER"
        wanted = date.fromisoformat(target).strftime("%m/%d/%Y")
        vals = {re.sub(r"[^0-9.]", "", r["price"]) for r in data["nocp"]["nocpTable"] if r["date"] == wanted}
    except (ValueError, KeyError, TypeError):
        return None, "UNPARSEABLE"
    if not vals:
        return None, "DATE_NOT_IN_RESPONSE"
    if len(vals) > 1:
        return None, "CONFLICTING_ROWS"
    close = vals.pop()
    try:
        if Decimal(close) <= 0:
            return None, "BAD_PRICE"
    except InvalidOperation:
        return None, "BAD_PRICE"
    return close, ""


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True, help="research input JSON (for the ticker list)")
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--target-date", required=True)
    p.add_argument("--index", type=Path, required=True)
    args = p.parse_args()
    tickers = [s["ticker"] for s in json.loads(args.input.read_text())["universe"]["securities"]]
    out = args.evidence / "nasdaq-nocp"
    out.mkdir(parents=True, exist_ok=True)
    index = json.loads(args.index.read_text()) if args.index.exists() else {}
    for t in tickers:
        if index.get(t, {}).get("close"):
            continue
        url = NOCP_URL.format(ticker=urllib.parse.quote(t, safe=""))
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read()
        except urllib.error.HTTPError as e:
            index[t] = {"url": url, "reason": f"HTTP_{e.code}"}
            if e.code in (401, 403, 406, 429):
                break                      # refused: stop, do not work around it
            continue
        except (urllib.error.URLError, TimeoutError) as e:
            index[t] = {"url": url, "reason": type(e).__name__}
            continue
        h = hashlib.sha256(body).hexdigest()
        f = out / f"{t}-d5-{h}.json"
        if not f.exists():
            f.write_bytes(body)
        close, reason = parse_nocp(body, args.target_date)
        index[t] = {"url": url, "sha256": h, "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "close": close, "reason": reason}
        time.sleep(0.3)
    args.index.write_text(json.dumps(index, indent=1, sort_keys=True) + "\n")
    ok = sum(1 for v in index.values() if v.get("close"))
    print(json.dumps({"tickers": len(tickers), "with_close": ok,
                      "problems": {k: v["reason"] for k, v in index.items() if not v.get("close")}}, indent=1))


if __name__ == "__main__":
    main()
