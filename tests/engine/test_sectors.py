from decimal import Decimal

from nasdaq100_pe.dec import D
from nasdaq100_pe.engine.core import calculate
from nasdaq100_pe.method import MethodSpec
from tests.engine.test_core import si, vi

M = MethodSpec()


def sectors(r, kind="ttm"):
    return {s.name: s for s in r.metrics[kind].sectors}


def test_sector_complete_gets_yield_and_pe_and_sums_match():
    r = calculate(vi(si("a", "0.3", pe="10", sector="Tech"), si("b", "0.2", pe="20", sector="Tech"), si("c", "0.5", pe="40", sector="Health")), M)
    s = sectors(r)
    assert s["Tech"].weight == D("0.5") and s["Tech"].complete
    assert abs(s["Tech"].sector_yield - (D("0.3") / D("10") + D("0.2") / D("20")) / D("0.5")) < Decimal("1e-12")
    t = r.metrics["ttm"]
    assert abs(sum(x.known_contribution for x in s.values()) - t.portfolio_yield) < Decimal("1e-12")
    assert sum(x.weight for x in s.values()) == D("1")
    assert abs(s["Health"].pe - D("40")) < Decimal("1e-12")


def test_partial_sector_has_no_yield_or_pe_but_shows_known():
    r = calculate(vi(si("a", "0.3", pe="10", sector="Tech"), si("b", "0.2", sector="Tech"), si("c", "0.5", pe="40", sector="Health")), M)
    s = sectors(r)["Tech"]
    assert not s.complete and s.sector_yield is None and s.pe is None
    assert s.known_contribution == D("0.3") / D("10") and s.valid_weight == D("0.3")
    assert r.metrics["ttm"].eligibility == "partial"
    assert abs(sum(x.known_contribution for x in sectors(r).values()) - r.metrics["ttm"].known_contribution) < Decimal("1e-12")


def test_zero_weight_sector_no_pe_explained():
    r = calculate(vi(si("a", "1", pe="10", sector="Tech"), si("z", "0", pe="10", sector="Energy")), M)
    e = sectors(r)["Energy"]
    assert e.weight == 0 and e.sector_yield is None and e.pe is None and e.note == "行业权重为零"


def test_unclassified_bucket():
    r = calculate(vi(si("a", "1", pe="10", sector=None)), M)
    assert "未分类" in sectors(r)


def test_nonpositive_sector_yield_pe_null():
    r = calculate(vi(si("a", "0.5", eps="-1", price="100", sector="Bad"), si("b", "0.5", pe="10", sector="Good")), M)
    b = sectors(r)["Bad"]
    assert b.sector_yield == D("-0.01") and b.pe is None and b.pe_state == "non_positive"


def test_contribution_points_are_100x_ci():
    r = calculate(vi(si("a", "0.4", pe="20")), M)
    sec = r.metrics["ttm"].securities["a"]
    assert sec.contribution_points == D("100") * sec.contribution
