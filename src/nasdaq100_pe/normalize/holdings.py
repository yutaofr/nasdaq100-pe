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
