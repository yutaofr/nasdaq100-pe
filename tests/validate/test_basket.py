from decimal import Decimal

import pytest

from nasdaq100_pe.dec import D
from nasdaq100_pe.method import MethodSpec
from nasdaq100_pe.normalize.holdings import normalize_holdings
from nasdaq100_pe.identity.models import SourceEvidence
from nasdaq100_pe.validate.input import validate_research_input
from tests.research_fixtures import base_input, dump, mod, sec

M = MethodSpec()
codes = lambda r: {d["code"] for d in r.diagnostics}


def test_complete_official_basket_accepted():
    r = validate_research_input(dump(base_input()), M)
    assert r.ok and r.exit_code == 0 and r.basket.qualified
    assert sum(r.basket.weights.final.values()) == Decimal(1)
    assert r.layers == {"raw_evidence": True, "normalized": True, "semantic_ok": True, "date_ok": None}


def test_not_hardcoded_to_100_or_101():
    for n in (1, 2, 3):
        r = validate_research_input(dump(base_input(weights=tuple(["1"] if n == 1 else ["0.5", "0.5"] if n == 2 else ["0.5", "0.3", "0.2"]))), M)
        assert r.ok


@pytest.mark.parametrize("scope", ["top_n", "partial", "unknown"])
def test_top_n_or_unknown_scope_not_qualified(scope):
    r = validate_research_input(dump(base_input(scope=scope)), M)
    assert not r.basket.qualified and "UNKNOWN_UNIVERSE" in codes(r)
    assert r.basket.coverage_ratio is None


def test_complete_true_flag_alone_insufficient():
    d = mod(base_input(scope="unknown"), lambda d: d["universe"].update(complete=True))
    r = validate_research_input(dump(d), M)
    assert not r.basket.qualified


def test_scope_full_needs_existing_source():
    d = mod(base_input(), lambda d: d["universe"].update(source_id="nope"))
    r = validate_research_input(dump(d), M)
    assert not r.basket.qualified and "UNKNOWN_UNIVERSE" in codes(r)


def test_duplicate_security_is_structural_exit4():
    d = mod(base_input(), lambda d: d["universe"]["securities"].append(sec("a")))
    r = validate_research_input(dump(d), M)
    assert r.exit_code == 4 and "DUPLICATE_SECURITY" in codes(r)


def test_missing_stock_weight_exit4_not_treated_as_cash():
    d = mod(base_input(), lambda d: d["weights"]["items"].pop())
    r = validate_research_input(dump(d), M)
    assert r.exit_code == 4 and "MISSING_WEIGHT" in codes(r)


def test_negative_weight_and_unknown_security_rejected():
    r = validate_research_input(dump(base_input(weights=("1.2", "-0.1", "-0.1"))), M)
    assert r.exit_code == 4 and "NEGATIVE_WEIGHT" in codes(r)
    d = mod(base_input(), lambda d: d["weights"]["items"].append({"security_id": "zz", "weight": "0"}))
    assert "UNKNOWN_SECURITY_IN_WEIGHTS" in codes(validate_research_input(dump(d), M))


def test_unknown_asset_class_rejects_proxy_set():
    d = base_input(mode="qqq_equity_proxy", weights=("0.5", "0.3", "0.19"), excluded=[{"label": "X", "asset_class": "mystery", "weight": "0.01"}])
    r = validate_research_input(dump(d), M)
    assert r.exit_code == 4 and "UNKNOWN_ASSET_CLASS" in codes(r)


def test_official_sum_tolerance_exact_boundary():
    ok = validate_research_input(dump(base_input(weights=("0.5001", "0.3", "0.2"))), M)   # 1.0001
    assert ok.ok
    ws = ok.basket.weights
    assert ws.official_rounding_factor == D("1") / D("1.0001") or abs(ws.official_rounding_factor - D("1") / D("1.0001")) < Decimal("1e-26")
    low = validate_research_input(dump(base_input(weights=("0.4999", "0.3", "0.2"))), M)   # 0.9999
    assert low.ok
    bad = validate_research_input(dump(base_input(weights=("0.50011", "0.3", "0.2"))), M)
    assert bad.exit_code == 4 and "WEIGHT_SUM_OUT_OF_TOLERANCE" in codes(bad)


def test_proxy_known_excluded_and_factors_stored_separately():
    d = base_input(mode="qqq_equity_proxy", weights=("0.45", "0.3", "0.2"), excluded=[{"label": "cash", "asset_class": "cash", "weight": "0.05"}])
    r = validate_research_input(dump(d), M)
    ws = r.basket.weights
    assert ws.known_excluded_weight == D("0.05") and ws.total_excluded_weight == D("0.05")
    assert ws.official_rounding_factor == D("1")           # 总和恰为1
    assert abs(ws.proxy_normalization_factor - D("1") / D("0.95")) < Decimal("1e-26")
    assert abs(sum(ws.final.values()) - 1) < Decimal("1e-26")


def test_proxy_partial_unknown_excluded_keeps_null_total():
    d = base_input(mode="qqq_equity_proxy", weights=("0.45", "0.3", "0.2"),
                   excluded=[{"label": "cash", "asset_class": "cash", "weight": "0.0017"}, {"label": "fx fwd", "asset_class": "other", "weight": None}])
    r = validate_research_input(dump(d), M)
    ws = r.basket.weights
    assert r.ok and ws.known_excluded_weight == D("0.0017") and ws.total_excluded_weight is None
    assert ws.unknown_excluded_items == ["fx fwd"]
    assert ws.official_rounding_factor == D("1")
    assert abs(sum(ws.final.values()) - 1) < Decimal("1e-26")


def test_zero_weight_member_kept_in_universe():
    r = validate_research_input(dump(base_input(weights=("0.5", "0.5", "0"))), M)
    assert r.ok and "c" in r.basket.weights.final and r.basket.weights.final["c"] == 0


def test_goog_googl_distinct_ids_shared_issuer_and_ticker_rename():
    d = base_input(weights=("0.5", "0.3", "0.2"))
    d["universe"]["securities"] = [
        sec("sec-goog", issuer="cik-1652044", cls="C", ticker="GOOG"),
        sec("sec-googl", issuer="cik-1652044", cls="A", ticker="GOOGL",
            ticker_history=[{"ticker": "GOOGL", "from": "2014-04-03", "to": None}]),
        sec("sec-meta", issuer="cik-meta", ticker="META", ticker_history=[{"ticker": "FB", "from": "2012-05-18", "to": "2022-06-08"}, {"ticker": "META", "from": "2022-06-09", "to": None}]),
    ]
    d["weights"]["items"] = [{"security_id": "sec-goog", "weight": "0.5"}, {"security_id": "sec-googl", "weight": "0.3"}, {"security_id": "sec-meta", "weight": "0.2"}]
    r = validate_research_input(dump(d), M)
    sc = {s.security_id: s for s in r.universe.securities}
    assert r.ok and sc["sec-goog"].issuer_id == sc["sec-googl"].issuer_id and sc["sec-goog"].share_class != sc["sec-googl"].share_class
    assert len(sc["sec-meta"].ticker_history) == 2


def test_cusip_cannot_be_permanent_id():
    d = mod(base_input(), lambda d: d["universe"]["securities"][0].update(cusip="a"))
    assert "CUSIP_AS_ID" in codes(validate_research_input(dump(d), M))


def test_adr_without_ratio_flagged_not_guessed():
    d = mod(base_input(), lambda d: d["universe"]["securities"][0].update(is_adr=True))
    r = validate_research_input(dump(d), M)
    assert "ADR_RATIO_UNKNOWN" in codes(r)
    assert r.universe.securities[0].adr_ratio is None


def test_coverage_none_when_weights_unknown_not_zero_percent():
    from nasdaq100_pe.validate.basket import coverage_ratio
    r = validate_research_input(dump(base_input(scope="top_n")), M)
    assert coverage_ratio(D("0.4"), r.basket) is None


def test_coverage_value_when_basket_known():
    from nasdaq100_pe.validate.basket import coverage_ratio
    r = validate_research_input(dump(base_input()), M)
    assert coverage_ratio(D("0.8"), r.basket) == "0.8"


def test_invalid_single_earnings_row_is_diagnostic_not_batch_failure():
    d = base_input()
    d["earnings"] = [{"security_id": "a", "kind": "ttm", "eps": "NaN"}, {"security_id": "b", "kind": "ttm", "eps": "5", "accounting_basis": "gaap", "currency": "USD"}]
    r = validate_research_input(dump(d), M)
    assert r.ok and r.exit_code == 0
    assert any(x["code"] == "BAD_EARNINGS_ROW" for x in r.diagnostics)
    assert len(r.earnings) == 1


def test_bad_json_and_nan_rejected():
    assert validate_research_input(b"{x", M).exit_code == 2
    assert validate_research_input(b'{"a": NaN}', M).exit_code == 2


def test_missing_required_sections_exit2():
    assert validate_research_input(dump({"schema_version": "1"}), M).exit_code == 2


def test_normalize_holdings_csv():
    raw = ("ticker,name,security_id,issuer_id,share_class,asset_class,weight,sector\n"
           "AAPL,Apple,sec-aapl,cik-aapl,common,equity,0.6,Tech\n"
           "GOOGL,Alphabet A,sec-googl,cik-g,A,equity,0.3,Comm\n"
           "USD,Cash,,,,cash,0.1,\n").encode()
    uni, ws = normalize_holdings(raw, SourceEvidence("s1", "d" * 64, "2026-11-09T00:00:00+00:00", "csv"))
    assert [s.security_id for s in uni.securities] == ["sec-aapl", "sec-googl"]
    assert ws.raw["sec-aapl"] == D("0.6") and ws.known_excluded_weight == D("0.1")
    assert uni.complete is False  # CSV 本身不证明完整，须另附完整性证据
