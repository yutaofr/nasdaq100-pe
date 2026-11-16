from datetime import date
from decimal import Decimal

from nasdaq100_pe.normalize.fy1 import basis_evidence, fiscal_year_reference, select_fy1

AS_OF, CUTOFF = date(2026, 11, 13), date(2026, 11, 16)


def fact(start, end, val, filed, form):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form, "accn": f"a-{end}"}


def facts(fy_end="2026-09-26", fy_start="2025-09-28", currency="USD", quarters=()):
    return {"facts": {"us-gaap": {
        "NetIncomeLoss": {"units": {currency: [fact(fy_start, fy_end, 100, "2026-10-30", "10-K")]}},
        "EarningsPerShareDiluted": {"units": {"USD/shares": list(quarters)}}}}}


def forecast(*rows):
    return {"data": {"yearlyForecast": {
        "headers": {"fiscalEnd": "Fiscal Year End", "consensusEPSForecast": "Consensus EPS* Forecast"},
        "rows": [{"fiscalEnd": lab, "consensusEPSForecast": eps, "noOfEstimates": n} for lab, eps, n in rows]}}}


def surprise(*rows):
    return {"data": {"earningsSurpriseTable": {
        "headers": {"fiscalQtrEnd": "Fiscal Quarter End", "eps": "Earnings Per Share*", "consensusForecast": "Consensus EPS* Forecast"},
        "rows": [{"fiscalQtrEnd": lab, "eps": eps} for lab, eps in rows]}}}


Q = [fact("2026-03-29", "2026-06-27", 2.02, "2026-07-31", "10-Q")]
SUR = surprise(("Jun 2026", 2.10))
ROWS = (("Sep 2027", 9.45, 13), ("Sep 2028", 10.39, 9), ("Sep 2029", 12.04, 3))


def test_fy1_is_the_fiscal_year_after_the_one_containing_d():
    s = select_fy1(forecast(*ROWS), SUR, facts(quarters=Q), AS_OF, CUTOFF)
    assert s.status == "ok"
    assert (s.eps, s.fiscal_year_end, s.estimates) == (Decimal("10.39"), "2028-09-30", 9)   # 不是当年(Sep 2027)
    assert s.period_evidence["source_label"] == "Sep 2028"
    assert s.period_evidence["current_fiscal_year_end_projected"] == "2027-09-26"


def test_fiscal_year_ended_but_not_yet_reported_is_not_treated_as_current():
    # 财年末 2026-10-31 已过、年报未申报：最近年报仍是 2025-10-31；含 D 的财年是 2027-10，FY1 是 2028-10
    cf = facts(fy_end="2025-10-31", fy_start="2024-11-01")
    s = select_fy1(forecast(("Oct 2026", 5, 9), ("Oct 2027", 6, 9), ("Oct 2028", 7, 5)), SUR, cf, AS_OF, CUTOFF)
    assert (s.status, s.fiscal_year_end, s.eps) == ("ok", "2028-10-31", Decimal(7))


def test_52_53_week_year_end_drifting_into_next_month_still_matches():
    cf = facts(fy_end="2026-01-31", fy_start="2025-02-02")      # 推算 FY1 末 2028-01-31；来源写 Jan 2028
    s = select_fy1(forecast(("Jan 2027", 1, 5), ("Jan 2028", 2, 5)), SUR, cf, AS_OF, CUTOFF)
    assert (s.status, s.fiscal_year_end) == ("ok", "2028-01-31")
    cf = facts(fy_end="2026-02-01", fy_start="2025-02-02")      # 期末落在 2 月 1 日，来源仍可能标 Jan
    s = select_fy1(forecast(("Jan 2027", 1, 5), ("Jan 2028", 2, 5)), SUR, cf, AS_OF, CUTOFF)
    assert (s.status, s.fiscal_year_end) == ("ok", "2028-01-31")


def test_d_next_to_a_fiscal_year_end_is_ambiguous():
    cf = facts(fy_end="2025-11-15", fy_start="2024-11-17")
    s = select_fy1(forecast(*ROWS), SUR, cf, AS_OF, CUTOFF)
    assert (s.status, s.reasons) == ("ambiguous", ["FISCAL_YEAR_BOUNDARY_AMBIGUOUS"])


def test_missing_next_year_row_or_zero_estimates_gives_no_row():
    s = select_fy1(forecast(("Sep 2027", 9.45, 13)), SUR, facts(quarters=Q), AS_OF, CUTOFF)
    assert (s.status, s.reasons) == ("no_forecast", ["NEXT_FISCAL_YEAR_NOT_IN_SOURCE"])
    s = select_fy1(forecast(("Sep 2027", 9.45, 13), ("Sep 2028", 10.39, 0)), SUR, facts(quarters=Q), AS_OF, CUTOFF)
    assert s.reasons == ["NO_ESTIMATES"]
    bad = forecast(*ROWS); bad["data"]["yearlyForecast"]["headers"]["consensusEPSForecast"] = "Forward EPS"
    assert select_fy1(bad, SUR, facts(quarters=Q), AS_OF, CUTOFF).reasons == ["UNEXPECTED_FORECAST_HEADER"]
    assert select_fy1({"data": None}, SUR, facts(quarters=Q), AS_OF, CUTOFF).status == "no_forecast"


def test_non_usd_reporter_is_not_assumed_usd():
    s = select_fy1(forecast(*ROWS), SUR, facts(currency="EUR"), AS_OF, CUTOFF)
    assert (s.status, s.reasons, s.eps) == ("currency_unverified", ["FORECAST_CURRENCY_UNVERIFIED"], None)


def test_basis_needs_the_source_reported_series():
    s = select_fy1(forecast(*ROWS), None, facts(quarters=Q), AS_OF, CUTOFF)
    assert (s.status, s.reasons) == ("basis_unverified", ["FORECAST_BASIS_UNVERIFIED"])
    b = basis_evidence(surprise(("Jun 2026", 2.10), ("Mar 2026", 2.02)), facts(quarters=Q), CUTOFF)
    assert b["quarters_differing_from_gaap"] == 1 and b["quarters_equal_to_gaap"] == 0
    assert b["quarters"][0] == {"fiscal_quarter_end": "Jun 2026", "source_eps": "2.1", "gaap_diluted_eps": "2.02"}
    assert b["quarters"][1]["gaap_diluted_eps"] is None       # 无同月 GAAP 单季值：只记录，不计入对照


def test_new_issuer_without_annual_report_uses_interim_ytd_start():
    cf = {"facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": [
        fact("2026-01-01", "2026-09-30", -4, "2026-10-22", "10-Q"), fact("2026-07-01", "2026-09-30", 4, "2026-10-22", "10-Q")]}}}}}
    ref = fiscal_year_reference(cf, AS_OF, CUTOFF)
    assert (ref["end"], ref["basis"]) == ("2025-12-31", "interim_ytd_start")
    s = select_fy1(forecast(("Dec 2026", 1, 5), ("Dec 2027", 2, 5)), SUR, cf, AS_OF, CUTOFF)
    assert (s.status, s.fiscal_year_end) == ("ok", "2027-12-31")


def test_facts_after_cutoff_are_ignored():
    cf = facts()
    cf["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"].append(fact("2026-09-27", "2027-09-25", 1, "2027-10-29", "10-K"))
    assert fiscal_year_reference(cf, AS_OF, CUTOFF)["end"] == "2026-09-26"


def test_usd_convenience_translation_next_to_home_currency_is_not_usd_reporting():
    cf = facts(currency="CNY")
    cf["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"] = [fact("2025-09-28", "2026-09-26", 14, "2026-10-30", "10-K")]
    assert select_fy1(forecast(*ROWS), SUR, cf, AS_OF, CUTOFF).status == "currency_unverified"
    cf["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["CNY"][0]["end"] = "2023-12-31"    # 早年本币、最近一期只有 USD
    cf["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["CNY"][0]["start"] = "2023-01-01"
    assert select_fy1(forecast(*ROWS), SUR, cf, AS_OF, CUTOFF).status == "ok"


def test_basket_date_maps_a_non_trading_effective_date_to_the_prior_trading_day():
    import pytest
    from nasdaq100_pe.calendar import TradingCalendar
    from nasdaq100_pe.normalize.holdings import BasketDateError, basket_date
    cal = TradingCalendar.load()
    assert basket_date({"effectiveDate": "2026-11-13"}, cal) == ("2026-11-13", "effectiveDate")
    assert basket_date({"effectiveDate": "2026-11-15", "effectiveBusinessDate": "2026-11-13"}, cal) == ("2026-11-13", "effectiveBusinessDate")
    assert basket_date({"effectiveDate": "2026-11-15", "effectiveBusinessDate": "2026-11-15"}, cal) == ("2026-11-13", "previous_trading_day_inferred")
    assert basket_date({"effectiveDate": "2026-11-27"}, cal)[0] == "2026-11-27"                    # 半日市仍是交易日
    assert basket_date({"effectiveDate": "2026-11-26"}, cal) == ("2026-11-25", "previous_trading_day_inferred")   # 感恩节
    with pytest.raises(BasketDateError):
        basket_date({"effectiveDate": "2026-11-15", "effectiveBusinessDate": "2026-11-12"}, cal)
