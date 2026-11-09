from __future__ import annotations

from nasdaq100_pe.dec import D, ONE, div, dstr, mul, sub

PE_DIFF_LABEL = "不同盈利口径下的估值差异"


def derive(metrics, inputs) -> dict:
    out: dict = {}
    for k, m in metrics.items():
        d: dict = {}
        if m.eligibility == "complete" and m.portfolio_yield is not None:
            y = m.portfolio_yield
            d["hundred_yuan"] = {"amount": dstr(mul(D("100"), y)), "loss": y < 0}
            d["yield_percent"] = dstr(mul(D("100"), y))
        out[k] = d
    t, f = metrics["ttm"], metrics["fy1"]
    cmp: dict = {}
    if (t.eligibility == "complete" and f.eligibility == "complete" and t.portfolio_yield > 0 and f.portfolio_yield > 0):
        cmp["pe_change"] = sub(div(f.pe, t.pe), ONE)
        cmp["pe_change_label"] = PE_DIFF_LABEL
        if inputs.accounting_comparable:
            cmp["yield_change"] = sub(div(f.portfolio_yield, t.portfolio_yield), ONE)
    out["comparison"] = cmp
    return out
