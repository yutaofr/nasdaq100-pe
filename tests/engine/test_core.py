import random
from decimal import Decimal

import pytest

from nasdaq100_pe.dec import D
from nasdaq100_pe.engine.core import EarningsInput, SecurityInputs, ValidatedInputs, calculate
from nasdaq100_pe.identity.models import SecurityIdentity
from nasdaq100_pe.method import MethodSpec

M = MethodSpec()
TOL = Decimal("1e-10")


def si(sid, w, pe=None, eps=None, price=None, sector="Tech", issuer=None, fy1=None, cap=None, **kw):
    ident = SecurityIdentity(sid, issuer or sid, "common", sid.upper(), sid, sector, "p")
    if pe is not None:  # 合成：价格100，EPS=100/PE
        price, eps = D("100"), (D("100") / D(pe) if D(pe) != 0 else D("0"))
        ttm = EarningsInput(eps=eps, price=price)
    elif eps is not None or price is not None:
        ttm = EarningsInput(eps=D(eps) if eps is not None else None, price=D(price) if price is not None else None)
    else:
        ttm = None
    return SecurityInputs(ident, D(w), ttm, fy1, company_market_cap=cap, **kw)


def vi(*rows, complete=True, **kw):
    return ValidatedInputs(list(rows), basket_complete=complete, synthetic=True, **kw)


def test_srd_example_five_securities():
    r = calculate(vi(si("a", "0.3", pe="30"), si("b", "0.3", pe="40"), si("c", "0.2", pe="400"), si("d", "0.1", pe="120"), si("e", "0.1", pe="-40")), M)
    t = r.metrics["ttm"]
    assert t.eligibility == "complete" and t.pe_state == "value"
    assert abs(t.portfolio_yield - Decimal("0.016333333333333333")) < TOL
    assert abs(t.pe - Decimal("61.2244897959183673")) < TOL
    assert t.coverage_ratio == Decimal("1")


def test_half_half_pe10_pe20():
    r = calculate(vi(si("a", "0.5", pe="10"), si("b", "0.5", pe="20")), M)
    t = r.metrics["ttm"]
    assert abs(t.portfolio_yield - Decimal("0.075")) < TOL
    assert abs(t.pe - Decimal("13.3333333333333333")) < TOL


def test_negative_earnings_negative_contribution_kept():
    r = calculate(vi(si("a", "0.5", eps="5", price="100"), si("b", "0.5", eps="-10", price="100")), M)
    t = r.metrics["ttm"]
    assert t.securities["b"].contribution == Decimal("-0.05")


def test_non_positive_total_keeps_yield_pe_null():
    r = calculate(vi(si("a", "0.5", eps="5", price="100"), si("b", "0.5", eps="-10", price="100")), M)
    t = r.metrics["ttm"]
    assert t.portfolio_yield == Decimal("-0.025")
    assert t.pe is None and t.pe_state == "non_positive"


def test_zero_eps_counts_coverage_zero_yield():
    r = calculate(vi(si("a", "0.5", eps="0", price="100"), si("b", "0.5", eps="10", price="100")), M)
    t = r.metrics["ttm"]
    assert t.eligibility == "complete" and t.securities["a"].yield_ == 0 and t.securities["a"].pe is None
    assert t.coverage_ratio == Decimal("1")


def test_pe_zero_cannot_imply_zero_earnings():
    row = SecurityInputs(SecurityIdentity("a", "a", "common", "A", "a", "Tech", "p"), D("1"),
                         EarningsInput(eps=None, price=None, pe=D("0")), None)
    t = calculate(vi(row), M).metrics["ttm"]
    assert t.eligibility != "complete" and "a" in t.missing_security_ids


def test_missing_member_blocks_complete_even_if_coverage_rounds_to_100():
    rows = [si("a", "0.99999", pe="20"), si("z", "0.00001")]
    t = calculate(vi(*rows), M).metrics["ttm"]
    assert t.eligibility == "partial" and t.portfolio_yield is None and t.pe is None
    assert t.known_contribution == D("0.99999") / D("20")
    assert t.missing_security_ids == ["z"] and t.valid_weight == D("0.99999")


def test_zero_weight_missing_also_blocks_complete():
    t = calculate(vi(si("a", "1", pe="20"), si("z", "0")), M).metrics["ttm"]
    assert t.eligibility == "partial" and t.missing_security_ids == ["z"]


def test_ttm_fy1_judged_independently():
    fy = EarningsInput(eps=D("5"), price=D("100"))
    r = calculate(vi(si("a", "1", pe="20", fy1=fy)), M)
    assert r.metrics["ttm"].eligibility == "complete" and r.metrics["fy1"].eligibility == "complete"
    r = calculate(vi(si("a", "1", pe="20")), M)
    assert r.metrics["fy1"].eligibility == "unavailable"


def test_unknown_denominator_coverage_none_and_no_complete():
    r = calculate(vi(si("a", "0.5", pe="20"), complete=False), M)
    t = r.metrics["ttm"]
    assert t.coverage_ratio is None and t.eligibility != "complete" and t.portfolio_yield is None


def test_profit_marketcap_path_needs_verification():
    row = SecurityInputs(SecurityIdentity("a", "a", "common", "A", "a", "Tech", "p"), D("1"),
                         EarningsInput(eps=None, price=None, profit=D("10"), market_cap=D("100"), profit_path_verified=False), None)
    assert calculate(vi(row), M).metrics["ttm"].eligibility == "unavailable"
    row2 = SecurityInputs(row.security, D("1"), EarningsInput(eps=None, price=None, profit=D("10"), market_cap=D("100"), profit_path_verified=True), None)
    t = calculate(vi(row2), M).metrics["ttm"]
    assert t.eligibility == "complete" and t.portfolio_yield == D("0.1")


def test_conflicting_paths_not_averaged_and_invalid():
    row = SecurityInputs(SecurityIdentity("a", "a", "common", "A", "a", "Tech", "p"), D("1"),
                         EarningsInput(eps=D("5"), price=D("100"), pe=D("10")), None)  # eps/price=0.05 vs 1/pe=0.1
    t = calculate(vi(row), M).metrics["ttm"]
    assert t.eligibility != "complete" and "a" in t.missing_security_ids
    assert "PATH_CONFLICT" in t.securities["a"].flags


def test_order_independent_and_precision():
    rows = [si(f"s{i}", "0.1", pe=str(10 + 3 * i)) for i in range(10)]
    a = calculate(vi(*rows), M).metrics["ttm"]
    random.Random(1).shuffle(rows)
    b = calculate(vi(*rows), M).metrics["ttm"]
    assert a.portfolio_yield == b.portfolio_yield and a.pe == b.pe
    assert len(str(a.pe).replace(".", "").lstrip("-")) <= 34


def test_deterministic_json_dump():
    r = calculate(vi(si("a", "1", pe="20")), M)
    d = r.to_dict()
    assert d["metrics"]["ttm"]["pe"] == "20" or d["metrics"]["ttm"]["pe"].startswith("20")
    assert isinstance(d["metrics"]["ttm"]["portfolio_yield"], str)
