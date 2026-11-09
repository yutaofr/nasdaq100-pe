from __future__ import annotations

import re

from nasdaq100_pe.dec import BadDecimal, D

EXPLICIT_STATUS = {"suspended", "identity_changed", "split_unclear"}
CONSOLIDATED_FEEDS = {"sip", "consolidated", "official_close", "exchange_official"}
DERIVED = {"holdings_implied", "derived", "nav_implied"}
_HASH = re.compile(r"^[0-9a-f]{64}$")


def check_price_row(row: dict, target_date: str) -> tuple[str, str]:
    """返回 (状态, 原因)。状态 ok 时原因为空。"""
    st = (row.get("status") or "ok").strip().lower()
    if st in EXPLICIT_STATUS:
        return st, st.upper()
    if st != "ok":
        return "invalid", "BAD_STATUS"
    try:
        v = D(row.get("close", ""))
    except BadDecimal:
        return "invalid", "BAD_NUMBER"
    if v <= 0:
        return "invalid", "NON_POSITIVE"
    pt = (row.get("price_type") or "").strip().lower()
    if pt in DERIVED:
        return "invalid", "DERIVED_PRICE"
    if pt in ("", "close"):
        return "invalid", "PRICE_TYPE_UNDEFINED"
    if pt != "regular_close" or (row.get("session") or "").strip().lower() != "regular":
        return "invalid", "NOT_REGULAR_CLOSE"
    if (row.get("currency") or "").upper() != "USD":
        return "invalid", "CURRENCY_NOT_USD"
    if row.get("date") != target_date:
        return "stale", "STALE_PRICE"
    if (row.get("adjustment") or "").lower() != "raw" or not row.get("split_basis_date"):
        return "invalid", "SPLIT_BASIS_UNKNOWN"
    if (row.get("feed") or "").lower() not in CONSOLIDATED_FEEDS:
        return "invalid", "FEED_NOT_CONSOLIDATED"
    if not _HASH.match(row.get("evidence_sha256") or "") or not row.get("locator"):
        return "invalid", "NO_EVIDENCE"
    return "ok", ""
