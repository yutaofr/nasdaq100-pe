from decimal import Decimal
from nasdaq100_pe.dec import D
from nasdaq100_pe.engine.core import EarningsInput, calculate
from nasdaq100_pe.method import MethodSpec
from tests.engine.test_core import si, vi

M = MethodSpec()


def two(ttm_pe="20", fy_pe="16", comparable=False, complete=True):
    fy = EarningsInput(eps=D("100") / D(fy_pe), price=D("100")) if fy_pe else None
    return calculate(vi(si("a", "1", pe=ttm_pe, fy1=fy), accounting_comparable=comparable, complete=complete), M)


def test_hundred_yuan_only_when_complete():
    r = two()
    assert r.derived["ttm"]["hundred_yuan"]["amount"].startswith("5")
    r2 = calculate(vi(si("a", "0.5", pe="20"), si("b", "0.5")), M)
    assert "hundred_yuan" not in r2.derived["ttm"]


def test_negative_yield_hundred_yuan_marked_loss():
    r = calculate(vi(si("a", "1", eps="-5", price="100")), M)
    h = r.derived["ttm"]["hundred_yuan"]
    assert h["loss"] is True and h["amount"].startswith("-5")


def test_growth_hidden_when_basis_not_comparable():
    r = two(comparable=False)
    assert "yield_change" not in r.derived["comparison"]
    # PE 差异若展示须附口径限制
    assert r.derived["comparison"]["pe_change_label"] == "不同盈利口径下的估值差异"
    assert abs(r.derived["comparison"]["pe_change"] - (D("16") / D("20") - 1)) < Decimal("1e-12")


def test_growth_shown_when_comparable_and_both_positive():
    r = two(comparable=True)
    assert abs(r.derived["comparison"]["yield_change"] - (D("1") / D("16") / (D("1") / D("20")) - 1)) < Decimal("1e-12")


def test_no_comparison_if_either_non_positive_or_incomplete():
    assert "pe_change" not in two(ttm_pe="-20").derived["comparison"]
    assert "pe_change" not in two(fy_pe=None).derived["comparison"]


def test_market_cap_dedup_by_issuer_and_conflict():
    a = si("goog", "0.5", pe="20", issuer="G", cap=D("100"))
    b = si("googl", "0.5", pe="20", issuer="G", cap=D("100"))
    r = calculate(vi(a, b), M)
    assert r.total_market_cap == D("100")
    c = si("googl", "0.5", pe="20", issuer="G", cap=D("101"))
    r = calculate(vi(a, c), M)
    assert r.total_market_cap is None and "MARKET_CAP_CONFLICT" in r.market_cap_flags
    assert r.metrics["ttm"].eligibility == "complete"   # EPS 路径不受影响


def test_market_cap_missing_unavailable():
    r = calculate(vi(si("a", "1", pe="20")), M)
    assert r.total_market_cap is None and "MARKET_CAP_MISSING" in r.market_cap_flags
