from __future__ import annotations

import csv
from pathlib import Path

from nasdaq100_pe.adapters.base import REQUIRED_PRICE_FIELDS, PriceBatch
from nasdaq100_pe.dec import CTX, D, dstr
from nasdaq100_pe.validate.prices import check_price_row


def load_prices(path: Path, universe, context) -> PriceBatch:
    ids = sorted(s.security_id for s in universe.securities)
    path = Path(path)
    if not path.exists():
        return PriceBatch("awaiting_user_import", missing_fields=list(REQUIRED_PRICE_FIELDS), missing_security_ids=ids)
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    by_sid: dict[str, list[dict]] = {}
    for r in rows:
        by_sid.setdefault(r.get("security_id", ""), []).append(r)
    target = context.D.isoformat()
    matrix, prices = [], {}
    for sid in ids:
        rs = by_sid.get(sid, [])
        if not rs:
            matrix.append({"security_id": sid, "status": "missing", "reason": "NO_ROW", "evidence": None}); continue
        results = [(check_price_row(r, target), r) for r in rs]
        good = [r for (st, _), r in results if st == "ok"]
        if good:
            if len({D(r["close"]) for r in good}) > 1:
                matrix.append({"security_id": sid, "status": "invalid", "reason": "PRICE_CONFLICT", "evidence": None}); continue
            r = good[0]
            matrix.append({"security_id": sid, "status": "ok", "reason": "", "evidence": {"sha256": r["evidence_sha256"], "locator": r["locator"]}})
            prices[sid] = {"security_id": sid, "date": r["date"], "close": r["close"], "currency": r["currency"],
                           "price_type": "regular_close", "split_basis_date": r["split_basis_date"],
                           "source_id": r.get("source_id", "price-file"), "fetched_at": r["fetched_at"]}
        else:
            (st, reason), r = results[0]
            matrix.append({"security_id": sid, "status": st, "reason": reason, "evidence": None})
    ok = len(prices)
    status = "ok" if ok == len(ids) else ("partial" if ok else "no_valid_prices")
    coverage = dstr(CTX.divide(D(str(ok)), D(str(len(ids)))).normalize()) if universe.complete and ids else None
    return PriceBatch(status, prices, matrix, coverage, [], [m["security_id"] for m in matrix if m["status"] != "ok"])
