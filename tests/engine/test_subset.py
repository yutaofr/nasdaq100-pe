from decimal import Decimal
from nasdaq100_pe.dec import D
from nasdaq100_pe.engine.core import calculate
from nasdaq100_pe.engine.subset import calculate_subset
from nasdaq100_pe.method import MethodSpec
from tests.engine.test_core import si, vi

M = MethodSpec()


def test_subset_k_over_c_and_pe_c_over_k():
    r = calculate(vi(si("a", "0.4", pe="20"), si("b", "0.3", pe="10"), si("c", "0.3")), M)
    s = calculate_subset(r, "ttm")
    assert s.available and s.covered_weight == D("0.7") and s.covered_count == 2 and s.excluded_ids == ["c"]
    K = D("0.4") / D("20") + D("0.3") / D("10")
    assert abs(s.subset_yield - K / D("0.7")) < Decimal("1e-12")
    assert abs(s.pe - D("0.7") / K) < Decimal("1e-9")
    assert s.name == "已覆盖证券子集TTM估值" and "并非全指数" in s.note
    assert calculate_subset(r, "fy1").available is False


def test_fy1_name():
    from nasdaq100_pe.engine.core import EarningsInput
    r = calculate(vi(si("a", "1", pe="20", fy1=EarningsInput(eps=D("5"), price=D("100")))), M)
    assert calculate_subset(r, "fy1").name == "已覆盖证券子集FY1估值"


def test_c_zero_unavailable():
    r = calculate(vi(si("a", "1")), M)
    s = calculate_subset(r, "ttm")
    assert not s.available and s.reason == "NO_COVERED_WEIGHT"


def test_k_zero_and_negative_keep_yield_pe_non_positive():
    r = calculate(vi(si("a", "0.5", eps="0", price="100"), si("b", "0.5")), M)
    s = calculate_subset(r, "ttm")
    assert s.available and s.subset_yield == 0 and s.pe is None and s.pe_state == "non_positive"
    r = calculate(vi(si("a", "0.5", eps="-5", price="100"), si("b", "0.5")), M)
    s = calculate_subset(r, "ttm")
    assert s.subset_yield == D("-0.05") and s.pe is None


def test_unknown_complete_weights_forbids_subset():
    r = calculate(vi(si("a", "0.5", pe="20"), complete=False), M)
    s = calculate_subset(r, "ttm")
    assert not s.available and s.reason == "UNKNOWN_FULL_WEIGHTS"


def test_95_percent_does_not_upgrade_to_complete():
    r = calculate(vi(si("a", "0.95", pe="20"), si("z", "0.05")), M)
    assert r.metrics["ttm"].eligibility == "partial"
    s = calculate_subset(r, "ttm")
    assert s.available and s.is_full_index is False
