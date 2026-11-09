from __future__ import annotations

from datetime import date

CATEGORY_ORDER = ["MISSING_Q4", "MISSING_LABEL", "CURRENCY_ADR", "SHARE_CLASS", "STALE", "MISSING_TTM"]
NEEDED = {
    "MISSING_Q4": "缺少明确已报告的单季稀释EPS：补 10-Q/10-K/8-K 业绩公告原文（含页/表定位），禁止用全年−九个月差分",
    "MISSING_LABEL": "来源无稀释EPS标签：补发行人原报表单季EPS及定位",
    "CURRENCY_ADR": "币种/ADR 口径不符：补 USD/存托凭证已报告EPS及换算比例证据",
    "SHARE_CLASS": "同发行人多股类：补各股类EPS口径与权利证据",
    "STALE": "最新季度距 D 超过 180 日：补充最新披露",
    "MISSING_TTM": "缺少合格TTM：补四个连续已报告季度EPS或人工复核结论",
}


def build_gap_queue(inputs, as_of: date | None = None) -> list[dict]:
    hints = {g["security_id"]: g["reason"] for g in inputs.raw.get("earnings_gaps", [])}
    ttm = {e["security_id"]: e for e in inputs.earnings if e["kind"] == "ttm"}
    weights = inputs.basket.weights.final if inputs.basket and inputs.basket.weights else {}
    out = []
    for s in inputs.universe.securities:
        row = ttm.get(s.security_id)
        if row is not None:
            q = row.get("latest_quarter_end")
            if as_of and q and (as_of - date.fromisoformat(q)).days > 180:
                cat = "STALE"
            else:
                continue
        else:
            cat = hints.get(s.security_id, "MISSING_TTM")
        w = weights.get(s.security_id)
        out.append({"security_id": s.security_id, "issuer_id": s.issuer_id, "category": cat, "weight": str(w) if w is not None else None,
                    "needed_evidence": NEEDED[cat], "source_hint": f"SEC companyfacts CIK={s.issuer_id}"})
    order = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    return sorted(out, key=lambda g: (order[g["category"]], -float(g["weight"] or 0), g["security_id"]))
