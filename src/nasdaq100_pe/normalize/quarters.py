"""SEC companyfacts → 四个连续已报告单季稀释 EPS 之和。不做差分补季；不确定转人工复核。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from nasdaq100_pe.dec import dsum

QUARTER_DAYS = (70, 125)     # 探测筛选参数：含 16 周(112天)特殊季；不是排除条件，连续性才是
ANNUAL_DAYS = (350, 380)
TAG = "EarningsPerShareDiluted"


@dataclass
class TtmSelection:
    status: str                       # ok | missing_quarter | needs_manual_review | missing_label
    ttm_eps: Decimal | None = None
    calculation_path: str = "reported_quarter_eps_sum"
    quarters: list[dict] = field(default_factory=list)
    versions: list[dict] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    annual_difference: Decimal | None = None
    latest_quarter_end: str | None = None
    currency: str = "USD"


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _days(e: dict) -> int:
    return (_d(e["end"]) - _d(e["start"])).days + 1


def select_ttm(cf: dict, supplements: list[dict] | None = None) -> TtmSelection:
    node = (cf.get("facts", {}).get("us-gaap", {}) or {}).get(TAG)
    if not node or not node.get("units"):
        return TtmSelection("missing_label", reasons=["MISSING_LABEL"])
    per_share = {u: es for u, es in node["units"].items() if u.endswith("/shares")}   # 'pure' 等非每股单位不可用
    if not per_share:
        return TtmSelection("missing_label", reasons=["MISSING_LABEL"])
    unit = "USD/shares" if "USD/shares" in per_share else sorted(per_share)[0]
    entries = per_share[unit]
    cur = unit.split("/")[0]
    entries = [e for e in entries if e.get("start") and e.get("end")]
    qs = [e for e in entries if QUARTER_DAYS[0] <= _days(e) <= QUARTER_DAYS[1]]
    annual = [e for e in entries if ANNUAL_DAYS[0] <= _days(e) <= ANNUAL_DAYS[1]]
    extra: list[str] = []
    for sp in supplements or []:
        if sp["currency"] != cur:
            extra.append("SUPPLEMENT_CURRENCY_MISMATCH")
            continue
        for e in qs:
            if (e["start"], e["end"]) == (sp["start"], sp["end"]) and Decimal(str(e["val"])) != Decimal(str(sp["eps"])):
                return TtmSelection("needs_manual_review", versions=[dict(x) for x in qs], reasons=["MANUAL_CONFLICT"], currency=cur)
        qs.append({"start": sp["start"], "end": sp["end"], "val": sp["eps"], "accn": "manual-" + sp["evidence_sha256"][:12],
                   "form": sp["form"], "filed": sp["filed"], "fp": "Q4", "manual": True,
                   "evidence_sha256": sp["evidence_sha256"], "locator": sp["locator"]})
    versions = [dict(e) for e in qs]
    groups: dict[tuple, list[dict]] = {}
    for e in qs:
        groups.setdefault((e["start"], e["end"]), []).append(e)
    resolved = []
    for key, g in groups.items():
        latest_filed = max(x["filed"] for x in g)
        top = [x for x in g if x["filed"] == latest_filed]
        if len({str(x["val"]) for x in top}) > 1:
            return TtmSelection("needs_manual_review", versions=versions, reasons=["AMBIGUOUS_VALUE"], currency=cur)
        resolved.append(top[0])
    resolved.sort(key=lambda x: x["end"])
    if len(resolved) < 4:
        return TtmSelection("missing_quarter", versions=versions, reasons=_missing_reasons(annual) + extra, currency=cur)
    last4 = resolved[-4:]
    for a, b in zip(last4, last4[1:]):
        if _d(a["end"]) + timedelta(days=1) != _d(b["start"]):
            return TtmSelection("missing_quarter", versions=versions, reasons=_missing_reasons(annual) + extra, currency=cur)
    ttm = dsum(Decimal(str(x["val"])) for x in last4)
    ann = next((a for a in annual if a["end"] == last4[-1]["end"]), None)
    diff = (Decimal(str(ann["val"])) - ttm) if ann else None
    return TtmSelection("ok", ttm, quarters=[{k: x.get(k) for k in ("start", "end", "val", "accn", "form", "filed", "fp", "manual", "evidence_sha256", "locator") if k in x} | ({} if x.get("manual") else {"manual": False}) for x in last4],
                        versions=versions, annual_difference=diff, latest_quarter_end=last4[-1]["end"], currency=cur)


def _missing_reasons(annual: list[dict]) -> list[str]:
    r = ["MISSING_QUARTER"]
    if annual:
        r.append("MISSING_Q4")     # 有全年值但缺单季：禁止“全年−九个月”补 Q4
    return r
