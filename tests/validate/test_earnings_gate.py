"""Research input must prove the earnings behind a complete metric."""
from copy import deepcopy

from nasdaq100_pe.calendar import TradingCalendar
from nasdaq100_pe.pipeline import _compute
from nasdaq100_pe.identity.models import SecurityIdentity
from nasdaq100_pe.normalize.quarters import select_ttm
from nasdaq100_pe.validate.earnings import EarningsBatch, validate_earnings
from tests.integration.test_research_pipeline import ctx, full
from tests.research_fixtures import dump
from tests.sec_fixtures import facts, four_quarters


CAL = TradingCalendar.load()


def compute(d):
    _, core, _ = _compute(dump(d), ctx(), CAL)
    return core


def test_unproven_ttm_eps_cannot_make_complete_pe():
    d = full()
    for e in d["earnings"]:
        e["eps"] = "999"
    core = compute(d)
    assert core is not None and core["completeness"]["ttm"] == "unavailable"
    assert core["results"]["metrics"]["ttm"]["pe"] is None


def test_fy1_gaap_and_missing_period_evidence_cannot_make_complete_pe():
    d = full()
    for e in d["earnings"]:
        e.update(kind="fy1", accounting_basis="gaap", forecast_period="FY1")
    core = compute(d)
    assert core is not None and core["completeness"]["fy1"] == "unavailable"
    assert core["results"]["metrics"]["fy1"]["pe"] is None


def test_future_reported_quarter_cannot_make_complete_pe():
    d = full()
    for e in d["earnings"]:
        e["latest_quarter_end"] = "2026-12-31"
    core = compute(d)
    assert core is not None and core["completeness"]["ttm"] == "unavailable"
    assert core["results"]["metrics"]["ttm"]["pe"] is None


def test_real_mode_unproved_earnings_cannot_make_complete_pe():
    d = full()
    d["data_mode"] = "real"
    for p in d["prices"]:
        p.update(evidence_sha256="a" * 64, locator="close")
    for e in d["earnings"]:
        e.pop("evidence")
    core = _compute(dump(d), ctx(data_mode="real"), CAL)[1]
    assert core is not None and core["completeness"]["ttm"] == "unavailable"
    assert core["results"]["metrics"]["ttm"]["pe"] is None


def test_zero_reported_quarter_keeps_valid_coverage():
    d = full(eps=("0", "4", "2"))
    core = compute(d)
    assert core["completeness"]["ttm"] == "complete"
    assert core["results"]["metrics"]["ttm"]["securities"]["a"]["yield_"] == "0"


def test_filing_after_price_date_before_observation_is_allowed():
    d = full()
    for e in d["earnings"]:
        e["quarters"][-1]["filed"] = "2026-11-07"
    assert compute(d)["completeness"]["ttm"] == "complete"


def test_filing_after_observation_or_bad_date_is_excluded():
    for filed in ("2026-11-09", "not-a-date"):
        d = full()
        for e in d["earnings"]:
            e["quarters"][-1]["filed"] = filed
        core = compute(d)
        assert core["completeness"]["ttm"] == "unavailable"


def test_filing_before_quarter_end_is_excluded():
    d = full()
    for e in d["earnings"]:
        e["quarters"][-1]["filed"] = "2026-09-01"
    assert compute(d)["completeness"]["ttm"] == "unavailable"


def test_three_duplicate_earnings_rows_never_restore_complete():
    d = full()
    d["earnings"].extend([deepcopy(d["earnings"][0]), deepcopy(d["earnings"][0])])
    assert compute(d)["completeness"]["ttm"] == "partial"


def test_sec_numeric_quarters_pass_through_adapter_validator_and_pipeline():
    d = full()
    selection = select_ttm(facts(four_quarters()))
    batch = EarningsBatch("a", "0000001234", "USD", "2026-01-01", selection,
                          checked_at="2026-11-08T10:00:00+00:00", content_fetched_at="2026-11-08T10:00:00+00:00",
                          content_sha256="c" * 64)
    ident = SecurityIdentity("a", "a", "common", "A", "a Inc", "Tech", "provider")
    row = validate_earnings(batch, [ident]).to_input_rows()[0]
    row["source_id"] = "s1"
    d["earnings"][0] = row
    core = compute(d)
    assert core["completeness"]["ttm"] == "complete"


def fy1_input():
    d = full()
    for e in d["earnings"]:
        e.update(kind="fy1", accounting_basis="normalized", forecast_period="FY1",
                 fiscal_year_end="2027-09-30", statistic="mean", unit="per_share",
                 normalized_evidence="synthetic provider accounting note", source_updated_at="2026-11-07")
    return d


def test_fy1_requires_normalized_basis_unit_and_future_fiscal_year():
    assert compute(fy1_input())["completeness"]["fy1"] == "complete"
    for changes in ({"accounting_basis": "gaap"}, {"unit": "annual_total"},
                    {"fiscal_year_end": "2026-09-30"}, {"source_updated_at": "2026-11-09"}):
        d = fy1_input()
        for e in d["earnings"]:
            e.update(changes)
        core = compute(d)
        assert core["completeness"]["fy1"] == "unavailable"
        assert core["results"]["metrics"]["fy1"]["pe"] is None
