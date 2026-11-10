"""方法版本 2：净利润路径进入资格评估与内核；覆盖门槛控制已覆盖部分 PE 的展示。"""
import copy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from nasdaq100_pe.calendar import TradingCalendar
from nasdaq100_pe.dec import CTX
from nasdaq100_pe.engine.core import calculate
from nasdaq100_pe.engine.subset import calculate_subset
from nasdaq100_pe.method import MethodSpec
from nasdaq100_pe.normalize.net_income import PATH
from nasdaq100_pe.validate.eligibility import AnalysisContext, assess_eligibility
from nasdaq100_pe.validate.input import validate_research_input
from tests.research_fixtures import H, base_input, dump, sec, ttm_evidence

CAL, M = TradingCalendar.load(), MethodSpec.load()
D0 = date(2026, 11, 6)
T = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
FETCHED = (T - timedelta(hours=2)).isoformat()


def fact(start, end, val, filed, form="10-Q"):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form, "accn": f"x-{end}"}


def components():
    return {"net_income_tag": "NetIncomeLoss",
            "fy": fact("2025-01-01", "2025-12-31", 1000, "2026-02-10", "10-K"),
            "ytd_current": fact("2026-01-01", "2026-09-30", 900, "2026-10-25"),
            "ytd_prior": fact("2025-01-01", "2025-09-30", 700, "2025-10-25"),
            "shares": fact("2026-07-01", "2026-09-30", 100, "2026-10-25")}


def ni_row(sid="b", **over):
    r = {"security_id": sid, "kind": "ttm", "profit": "1200", "shares": "100", "accounting_basis": "gaap", "currency": "USD",
         "split_basis_date": "2026-01-01", "latest_quarter_end": "2026-09-30", "fetched_at": FETCHED, "calculation_path": PATH,
         "source_id": "s1", "evidence": {"cik": "synthetic", "content_sha256": H, "locator": "us-gaap/NetIncomeLoss/USD",
                                         "components": components()}}
    r.update(over)
    return r


def price(sid, close="100"):
    return {"security_id": sid, "date": D0.isoformat(), "close": close, "currency": "USD", "price_type": "regular_close",
            "split_basis_date": "2026-01-01", "source_id": "s1", "fetched_at": FETCHED}


def eps_row(sid, eps="5"):
    return {"security_id": sid, "kind": "ttm", "eps": eps, "accounting_basis": "gaap", "currency": "USD", "split_basis_date": "2026-01-01",
            "latest_quarter_end": "2026-09-30", "fetched_at": FETCHED, **ttm_evidence(eps)}


def assess(earnings, method_version="2", prices=None, securities=None, data_mode="synthetic"):
    d = base_input()
    d["universe"]["as_of"] = d["weights"]["date"] = D0.isoformat()
    if securities:
        d["universe"]["securities"] = securities
    d["prices"] = prices or [price(s) for s in "abc"]
    d["earnings"] = earnings
    iv = validate_research_input(dump(d), M)
    c = AnalysisContext(W=D0, D=D0, T=T, analysis_profile="research", basket_policy="current", coverage_policy="subset",
                        freshness_policy="weekly", method_version=method_version, data_mode=data_mode)
    return iv, assess_eligibility(iv, c, CAL)


def codes(v, sid="b"):
    return [d["code"] for d in v.diagnostics if d.get("security_id") == sid]


def test_net_income_over_shares_times_price_is_the_security_yield():
    _, v = assess([eps_row("a"), ni_row("b")], prices=[price("a"), price("b", "200"), price("c")])
    res = calculate(v, M)
    b = res.metrics["ttm"].securities["b"]
    assert b.valid and b.yield_ == Decimal("0.06")             # 1200 / (100 × 200)
    assert res.metrics["ttm"].securities["a"].yield_ == Decimal("0.05")
    assert "TTM_NET_INCOME_PATH" in codes(v)
    assert res.metrics["ttm"].eligibility == "partial" and res.metrics["ttm"].pe is None   # 缺 c：完整 PE 仍留空


def test_loss_stays_negative():
    comps = components(); comps["ytd_current"]["val"] = -500
    r = ni_row(profit="-200"); r["evidence"]["components"] = comps
    _, v = assess([r])
    assert calculate(v, M).metrics["ttm"].securities["b"].yield_ == Decimal("-0.02")


def test_method_version_1_rejects_the_path():
    _, v = assess([ni_row()], method_version="1")
    assert codes(v) == ["PATH_NOT_IN_METHOD"] and v.securities[1].ttm is None


@pytest.mark.parametrize("change,code", [
    (lambda r: r.update(profit="1300"), "TTM_PROFIT_MISMATCH"),
    (lambda r: r.update(shares="50"), "TTM_PROFIT_MISMATCH"),
    (lambda r: r.update(latest_quarter_end="2026-06-30"), "TTM_PROFIT_MISMATCH"),
    (lambda r: r["evidence"]["components"]["ytd_prior"].update(start="2025-02-01"), "TTM_PERIOD_MISALIGNED"),
    (lambda r: r["evidence"]["components"]["ytd_current"].update(filed="2026-11-09"), "SOURCE_AFTER_CUTOFF"),
    (lambda r: r["evidence"]["components"].update(cover_shares={"end": "2026-10-20", "val": 400, "filed": "2026-10-25", "form": "10-Q", "accn": "c"}), "SHARE_COUNT_INCONSISTENT"),
    (lambda r: r.update(currency="EUR"), "CURRENCY_MISMATCH"),
    (lambda r: r.update(split_basis_date="2025-01-01"), "SPLIT_BASIS_MISMATCH"),
    (lambda r: r.update(accounting_basis="normalized"), "WRONG_ACCOUNTING_BASIS"),
])
def test_tampered_or_inconsistent_rows_do_not_reach_the_engine(change, code):
    r = ni_row(); change(r)
    _, v = assess([r])
    assert codes(v) == [code] and v.securities[1].ttm is None


def test_period_ending_after_price_date_rejected():
    comps = components()
    comps["ytd_current"] = fact("2026-01-01", "2026-11-07", 900, "2026-11-08")
    comps["ytd_prior"] = fact("2025-01-01", "2025-11-07", 700, "2025-11-20")
    comps["shares"] = fact("2026-08-08", "2026-11-07", 100, "2026-11-08")
    r = ni_row(latest_quarter_end="2026-11-07"); r["evidence"]["components"] = comps
    _, v = assess([r])
    assert codes(v) == ["SOURCE_AFTER_PRICE_DATE"]


def test_row_with_both_eps_and_net_income_path_or_without_shares_is_a_bad_row():
    for r in (ni_row(eps="12"), {k: v for k, v in ni_row().items() if k != "shares"}, ni_row(shares="0"), ni_row(kind="fy1")):
        iv, _ = assess([r])
        assert not iv.earnings and [d["code"] for d in iv.diagnostics] == ["BAD_EARNINGS_ROW"]


def test_real_mode_requires_components_evidence():
    r = ni_row(); r["evidence"].pop("components")
    px = [dict(price(s), evidence_sha256=H, locator="x") for s in "abc"]
    _, v = assess([r], prices=px, data_mode="real")
    assert codes(v) == ["EARNINGS_NO_EVIDENCE"]


def test_adr_and_multi_class_rules_apply():
    secs = [sec("a"), sec("b", issuer="i", cls="A"), sec("c", issuer="i", cls="C")]
    _, v = assess([ni_row("b"), ni_row("c")], securities=secs)
    assert codes(v, "b") == ["AMBIGUOUS_SHARE_SCOPE"] and codes(v, "c") == ["AMBIGUOUS_SHARE_SCOPE"]
    ev = {"A": "同权", "C": "同权"}
    _, v = assess([ni_row("b", class_evidence=ev), ni_row("c", class_evidence=ev)], securities=secs)
    assert codes(v, "b") == ["TTM_NET_INCOME_PATH"]
    _, v = assess([ni_row("b")], securities=[sec("a"), sec("b", is_adr=True), sec("c")])
    assert codes(v) == ["ADR_RATIO_UNKNOWN"]


def test_covered_subset_pe_is_displayable_only_at_or_above_the_coverage_threshold():
    # 权重 a=0.5 b=0.3 c=0.2；a+b 覆盖 0.8 → K=0.5×0.05+0.3×0.12=0.061
    _, v = assess([eps_row("a"), ni_row("b")])
    res = calculate(v, M)
    s = calculate_subset(res, "ttm", Decimal("0.9"))
    assert s.available and s.coverage_ratio == Decimal("0.8") and not s.display_qualified
    assert calculate_subset(res, "ttm", Decimal("0.8")).display_qualified
    assert calculate_subset(res, "ttm", Decimal("0.8")).pe == CTX.divide(Decimal("0.8"), Decimal("0.061"))
    assert not calculate_subset(res, "ttm").display_qualified                  # 无门槛（方法版本1）不展示
    assert res.metrics["ttm"].pe is None


def test_non_positive_subset_is_never_display_qualified():
    comps = components(); comps["ytd_current"]["val"] = -5000
    r = ni_row(profit="-4700"); r["evidence"]["components"] = comps
    _, v = assess([r])
    s = calculate_subset(calculate(v, M), "ttm", Decimal("0.1"))
    assert s.pe_state == "non_positive" and not s.display_qualified
