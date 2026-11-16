from __future__ import annotations

import csv
import io
from decimal import Decimal

from nasdaq100_pe.dec import D, add, ZERO
from nasdaq100_pe.identity.models import SecurityIdentity, SourceEvidence, Universe, WeightSet

NON_EQUITY = {"cash", "other", "derivative", "bond"}


def normalize_holdings(raw: bytes, evidence: SourceEvidence) -> tuple[Universe, WeightSet]:
    """官方/基金持仓 CSV → 标准化名单与原权重。CSV 本身不证明完整，complete 恒为 False，须另附完整性证据。"""
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    secs, w, excluded = [], {}, []
    known = ZERO
    for r in rows:
        ac = (r.get("asset_class") or "").strip().lower()
        if ac == "equity":
            sid = r["security_id"]
            secs.append(SecurityIdentity(security_id=sid, issuer_id=r.get("issuer_id") or sid, share_class=r.get("share_class") or "common",
                                         ticker=r["ticker"], name=r.get("name", ""), sector=r.get("sector") or None,
                                         sector_source="holdings-file" if r.get("sector") else None))
            w[sid] = D(r["weight"])
        else:
            val = r.get("weight")
            excluded.append({"label": r.get("name") or r.get("ticker"), "asset_class": ac or "unknown", "weight": val if val != "" else None})
            if val not in (None, ""):
                known = add(known, D(val))
    uni = Universe(as_of="", source_id=evidence.source_id, listing_scope="unknown", securities=secs, complete=False)
    ws = WeightSet(mode="qqq_equity_proxy", date="", source_id=evidence.source_id, raw=w, excluded=excluded,
                   known_excluded_weight=known if excluded else None,
                   unknown_excluded_items=[e["label"] for e in excluded if e["weight"] is None])
    return uni, ws


class BasketDateError(ValueError):
    pass


def basket_date(holdings: dict, calendar) -> tuple[str, str]:
    """持仓文件对应的篮子日 W 及依据。

    effectiveDate 是交易日时直接采用。落在周末/休市日时（来源在非交易日也会给出当日日期），
    其后没有新的收盘价，权重对应的是此前最后一个交易日的收盘：文件自带的 effectiveBusinessDate
    与之一致时以它为依据；文件没有可用的营业日字段时采用此前最后一个交易日并注明是推定。
    营业日字段指向别的交易日则拒绝，不猜。
    """
    from datetime import date, timedelta
    eff = date.fromisoformat(holdings["effectiveDate"])
    if calendar.is_trading_day(eff):
        return eff.isoformat(), "effectiveDate"
    prev = eff - timedelta(days=1)
    while not calendar.is_trading_day(prev):
        prev -= timedelta(days=1)
    biz = holdings.get("effectiveBusinessDate")
    if biz:
        b = date.fromisoformat(biz)
        if b == prev:
            return prev.isoformat(), "effectiveBusinessDate"
        if calendar.is_trading_day(b):
            raise BasketDateError(f"effectiveDate {eff} 非交易日，而 effectiveBusinessDate {b} 不是其前一交易日 {prev}")
    return prev.isoformat(), "previous_trading_day_inferred"
