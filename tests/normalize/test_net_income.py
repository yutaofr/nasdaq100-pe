from datetime import date
from decimal import Decimal

import pytest

from nasdaq100_pe.normalize.net_income import (ComponentError, compute_from_components, select_ttm_net_income)

AS_OF, CUTOFF = date(2026, 11, 5), date(2026, 11, 9)


def f(start, end, val, filed, form="10-Q", accn=None):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form, "accn": accn or f"a-{end}-{filed}"}


def facts(ni, shares, cover=None):
    cf = {"facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": ni}},
                                "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": shares}}}}}
    if cover is not None:
        cf["facts"]["dei"] = {"EntityCommonStockSharesOutstanding": {"units": {"shares": cover}}}
    return cf


# 日历财年：FY2025=1000；2026 前九个月=900；2025 前九个月=700 → TTM=1200
NI = [f("2025-01-01", "2025-12-31", 1000, "2026-02-10", "10-K"),
      f("2025-01-01", "2025-09-30", 700, "2025-10-25"),
      f("2025-07-01", "2025-09-30", 250, "2025-10-25"),
      f("2026-01-01", "2026-09-30", 900, "2026-10-25"),
      f("2026-07-01", "2026-09-30", 320, "2026-10-25")]
SH = [f("2026-07-01", "2026-09-30", 100, "2026-10-25"), f("2026-01-01", "2026-09-30", 101, "2026-10-25")]
COVER = [{"end": "2026-10-20", "val": 99, "filed": "2026-10-25", "form": "10-Q", "accn": "a-cover"}]


def test_ttm_is_annual_plus_current_ytd_minus_prior_ytd():
    s = select_ttm_net_income(facts(NI, SH, COVER), AS_OF, CUTOFF)
    assert s.status == "ok"
    assert (s.profit, s.shares, s.latest_period_end) == (Decimal(1200), Decimal(100), "2026-09-30")
    assert s.components["shares"]["start"] == "2026-07-01"      # 取单季加权股数，不取累计
    assert compute_from_components(s.components) == (Decimal(1200), Decimal(100), "2026-09-30")


def test_loss_is_kept_negative():
    ni = [dict(x) for x in NI]
    ni[3]["val"] = -500
    s = select_ttm_net_income(facts(ni, SH, COVER), AS_OF, CUTOFF)
    assert s.profit == Decimal(-200)


def test_annual_only_when_no_later_period():
    ni = [f("2025-10-01", "2026-09-30", 1000, "2026-11-01", "10-K")]
    sh = [f("2025-10-01", "2026-09-30", 50, "2026-11-01", "10-K")]
    s = select_ttm_net_income(facts(ni, sh), AS_OF, CUTOFF)
    assert s.status == "ok" and s.profit == Decimal(1000) and s.shares == Decimal(50)
    assert "ytd_current" not in s.components and "COVER_SHARES_UNAVAILABLE" in s.flags


def test_facts_filed_after_cutoff_or_ending_after_price_date_are_ignored():
    ni = NI + [f("2026-01-01", "2026-12-31", 9999, "2027-02-10", "10-K")]
    assert select_ttm_net_income(facts(ni, SH, COVER), AS_OF, CUTOFF).profit == Decimal(1200)
    late = [dict(x, filed="2026-11-10") if x["end"] == "2026-09-30" and x["start"].startswith("2026") else x for x in NI]
    s = select_ttm_net_income(facts(late, SH, COVER), AS_OF, CUTOFF)
    assert s.status != "ok" or s.latest_period_end == "2025-12-31"


def test_restated_value_uses_latest_filing_and_same_day_conflict_needs_review():
    ni = NI + [f("2025-01-01", "2025-09-30", 720, "2026-10-25")]       # 上年同期在新 10-Q 中重述
    assert select_ttm_net_income(facts(ni, SH, COVER), AS_OF, CUTOFF).profit == Decimal(1180)
    clash = NI + [f("2026-01-01", "2026-09-30", 901, "2026-10-25")]
    assert select_ttm_net_income(facts(clash, SH, COVER), AS_OF, CUTOFF).status == "needs_manual_review"


def test_missing_prior_ytd_or_shares_or_label():
    assert select_ttm_net_income(facts([x for x in NI if x["val"] != 700], SH), AS_OF, CUTOFF).reasons == ["MISSING_PRIOR_YTD"]
    assert select_ttm_net_income(facts(NI, SH[1:]), AS_OF, CUTOFF).reasons == ["MISSING_DILUTED_SHARES"]
    assert select_ttm_net_income({"facts": {"us-gaap": {}}}, AS_OF, CUTOFF).status == "missing_label"


def test_cover_share_count_far_from_diluted_shares_needs_review():
    # 期后 1 拆 4：封面股数约为加权稀释股数的 4 倍，价格已是拆后口径 → 不可直接相乘
    cover = [dict(COVER[0], val=400)]
    s = select_ttm_net_income(facts(NI, SH, cover), AS_OF, CUTOFF)
    assert s.status == "needs_manual_review" and s.reasons == ["SHARE_COUNT_INCONSISTENT"]


@pytest.mark.parametrize("mutate,code", [
    (lambda c: c["ytd_current"].update(start="2026-02-01"), "TTM_PERIOD_MISALIGNED"),
    (lambda c: c["ytd_prior"].update(end="2025-06-30"), "TTM_PERIOD_MISALIGNED"),
    (lambda c: c["shares"].update(end="2026-06-30"), "TTM_PERIOD_MISALIGNED"),
    (lambda c: c["shares"].update(start="2026-01-01"), "TTM_PERIOD_MISALIGNED"),
    (lambda c: c["fy"].update(val=1.5e3), "BAD_NUMBER"),
    (lambda c: c["shares"].update(val=0), "BAD_SHARE_COUNT"),
    (lambda c: c["fy"].pop("accn"), "TTM_EVIDENCE_INSUFFICIENT"),
    (lambda c: c.pop("ytd_prior"), "TTM_EVIDENCE_INSUFFICIENT"),
    (lambda c: c["fy"].update(form="DEF 14A"), "TTM_EVIDENCE_INSUFFICIENT"),
    (lambda c: c.update(net_income_tag="ProfitLoss"), "COMMON_EARNINGS_UNVERIFIED"),
    (lambda c: c.update(net_income_tag="IncomeLossFromContinuingOperations"), "TTM_EVIDENCE_INSUFFICIENT"),
])
def test_components_are_rechecked(mutate, code):
    c = select_ttm_net_income(facts(NI, SH, COVER), AS_OF, CUTOFF).components
    mutate(c)
    with pytest.raises(ComponentError) as e:
        compute_from_components(c)
    assert e.value.code == code


def test_proxy_statement_values_are_not_components():
    ni = NI + [f("2025-01-01", "2025-12-31", 1111, "2026-04-20", "DEF 14A")]
    assert select_ttm_net_income(facts(ni, SH, COVER), AS_OF, CUTOFF).profit == Decimal(1200)


def test_falls_back_to_common_stockholder_tag_when_primary_tag_is_stale_and_never_mixes_tags():
    cf = facts([f("2012-01-01", "2012-12-31", 5, "2013-02-01", "10-K")], SH, COVER)
    cf["facts"]["us-gaap"]["NetIncomeLossAvailableToCommonStockholdersBasic"] = {"units": {"USD": NI}}
    cf["facts"]["us-gaap"]["ProfitLoss"] = {"units": {"USD": [dict(x, val=x["val"] + 50) for x in NI]}}
    s = select_ttm_net_income(cf, AS_OF, CUTOFF)
    assert s.profit == Decimal(1200) and s.components["net_income_tag"] == "NetIncomeLossAvailableToCommonStockholdersBasic"


def _with_eps(val):
    cf = facts(NI, SH, COVER)
    cf["facts"]["us-gaap"]["EarningsPerShareDiluted"] = {"units": {"USD/shares": [f("2026-07-01", "2026-09-30", val, "2026-10-25")]}}
    return cf


def test_reported_eps_must_agree_with_net_income_over_diluted_shares():
    ok = select_ttm_net_income(_with_eps(3.2), AS_OF, CUTOFF)          # 320 / 100
    assert ok.status == "ok" and ok.components["eps_check"]["eps"]["val"] == 3.2 and ok.flags == []
    # 优先股股息使普通股 EPS 明显低于 净利润÷股数 → 该标签的净利润不能直接当普通股盈利
    bad = select_ttm_net_income(_with_eps(2.9), AS_OF, CUTOFF)
    assert bad.status == "needs_manual_review" and bad.reasons == ["COMMON_EARNINGS_MISMATCH"]
    assert "EPS_CROSSCHECK_UNAVAILABLE" in select_ttm_net_income(facts(NI, SH, COVER), AS_OF, CUTOFF).flags


def test_profit_loss_tag_is_usable_only_when_reported_eps_confirms_it_belongs_to_common_shares():
    def cf(eps):
        c = {"facts": {"us-gaap": {"ProfitLoss": {"units": {"USD": NI}},
                                   "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": SH}}}}}
        if eps is not None:
            c["facts"]["us-gaap"]["EarningsPerShareDiluted"] = {"units": {"USD/shares": [f("2026-07-01", "2026-09-30", eps, "2026-10-25")]}}
        return c
    ok = select_ttm_net_income(cf(3.2), AS_OF, CUTOFF)
    assert ok.status == "ok" and ok.profit == Decimal(1200) and ok.components["net_income_tag"] == "ProfitLoss"
    assert select_ttm_net_income(cf(None), AS_OF, CUTOFF).reasons == ["COMMON_EARNINGS_UNVERIFIED"]
    assert select_ttm_net_income(cf(2.5), AS_OF, CUTOFF).reasons == ["COMMON_EARNINGS_MISMATCH"]     # 少数股东拿走一部分
