"""Archive Nasdaq analyst earnings-forecast and earnings-surprise responses for every equity in a research input.

Two requests per ticker to the endpoints the Nasdaq "Earnings" page calls. Responses are stored
content-addressed; the index records hash and fetch time only. Selection of the FY1 row and the
accounting-basis comparison happen offline in build_research_v2.py. Nothing is retried on an HTTP refusal.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URLS = {"forecast": "https://api.nasdaq.com/api/analyst/{ticker}/earnings-forecast",
        "surprise": "https://api.nasdaq.com/api/company/{ticker}/earnings-surprise"}
REFUSED = (401, 403, 406, 429)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def collect(tickers: list[str], evidence: Path, index: dict, *, fetch=fetch, sleep=time.sleep, now=None) -> dict:
    out = evidence / "nasdaq-forecast"
    out.mkdir(parents=True, exist_ok=True)
    now = now or (lambda: datetime.now(timezone.utc).isoformat())
    for t in tickers:
        entry = index.setdefault(t, {})
        for kind, tpl in URLS.items():
            if entry.get(kind, {}).get("sha256"):
                continue
            url = tpl.format(ticker=urllib.parse.quote(t, safe=""))
            try:
                body = fetch(url)
            except urllib.error.HTTPError as e:
                entry[kind] = {"url": url, "reason": f"HTTP_{e.code}"}
                if e.code in REFUSED:
                    return index               # refused: stop, do not work around it
                continue
            except (urllib.error.URLError, TimeoutError) as e:
                entry[kind] = {"url": url, "reason": type(e).__name__}
                continue
            h = hashlib.sha256(body).hexdigest()
            f = out / f"{t}-{kind}-{h}.json"
            if not f.exists():
                f.write_bytes(body)
            entry[kind] = {"url": url, "sha256": h, "fetched_at": now(), "file": f.name}
            sleep(0.3)
    return index


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True, help="research input JSON (for the ticker list)")
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--index", type=Path, required=True)
    a = p.parse_args()
    tickers = [s["ticker"] for s in json.loads(a.input.read_text())["universe"]["securities"]]
    index = json.loads(a.index.read_text()) if a.index.exists() else {}
    try:
        collect(tickers, a.evidence, index)
    finally:
        a.index.write_text(json.dumps(index, indent=1, sort_keys=True) + "\n")
    bad = {t: {k: v.get("reason") for k, v in e.items() if not v.get("sha256")} for t, e in index.items()}
    print(json.dumps({"tickers": len(tickers),
                      "with_forecast": sum(1 for t in tickers if index.get(t, {}).get("forecast", {}).get("sha256")),
                      "problems": {t: b for t, b in bad.items() if b}}, indent=1))


if __name__ == "__main__":
    main()
