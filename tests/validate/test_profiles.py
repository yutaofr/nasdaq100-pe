from datetime import date, datetime, timedelta, timezone

import pytest

from nasdaq100_pe.calendar import CalendarUnknown, TradingCalendar, strict_cutoff
from nasdaq100_pe.method import MethodSpec
from nasdaq100_pe.validate.eligibility import AnalysisContext, EligibilityError, assess_eligibility, input_identity, series_key
from nasdaq100_pe.validate.input import validate_research_input
from tests.research_fixtures import base_input, dump

CAL = TradingCalendar.load()
M = MethodSpec.load()
D0 = date(2026, 11, 6)                       # 周五
T_SUN = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)


def ctx(**kw):
    base = dict(W=D0, D=D0, T=T_SUN, analysis_profile="research", basket_policy="current", coverage_policy="subset",
                freshness_policy="weekly", method_version="1", data_mode="synthetic")
    base.update(kw)
    return AnalysisContext(**base)


def build(fetched=None, ttm_q=date(2026, 9, 30), fy_upd=date(2026, 10, 20), price_date=D0, **over):
    fetched = fetched or (T_SUN - timedelta(hours=2)).isoformat()
    d = base_input()
    d["prices"] = [{"security_id": s, "date": price_date.isoformat(), "close": "100", "currency": "USD", "price_type": "regular_close",
                    "split_basis_date": "2026-01-01", "source_id": "s1", "fetched_at": fetched} for s in "abc"]
    d["earnings"] = [
        {"security_id": "a", "kind": "ttm", "eps": "5", "accounting_basis": "gaap", "currency": "USD", "split_basis_date": "2026-01-01",
         "latest_quarter_end": ttm_q.isoformat(), "fetched_at": fetched},
        {"security_id": "a", "kind": "fy1", "eps": "6", "accounting_basis": "normalized", "currency": "USD", "split_basis_date": "2026-01-01",
         "forecast_period": "FY1", "source_updated_at": fy_upd.isoformat() if fy_upd else None, "fetched_at": fetched},
    ]
    d.update(over)
    return validate_research_input(dump(d), M)


def run(iv, c):
    return assess_eligibility(iv, c, CAL)


def sec(v, sid="a"):
    return next(s for s in v.securities if s.security.security_id == sid)


# ---- 模式组合 ----
@pytest.mark.parametrize("bad", [dict(basket_policy="fixed"), dict(coverage_policy="subset"), dict(freshness_policy="weekly")])
def test_strict_only_current_full_daily(bad):
    with pytest.raises(EligibilityError) as e:
        ctx(analysis_profile="strict", **{**dict(basket_policy="current", coverage_policy="full", freshness_policy="daily"), **bad})
    assert e.value.code == "INVALID_COMBINATION"


def test_sunday_research_reading_friday_price_ok_and_strict_rejects():
    iv = build()
    v = run(iv, ctx())                                    # 研究：T=周日，D=周五
    assert v.context["T"] == T_SUN.isoformat()
    with pytest.raises(EligibilityError) as e:
        run(iv, ctx(analysis_profile="strict", coverage_policy="full", freshness_policy="daily", basket_policy="current"))
    assert e.value.code == "STRICT_CUTOFF_EXCEEDED"


def test_strict_cutoff_boundary_and_dst():
    assert strict_cutoff(date(2026, 11, 6)) == datetime(2026, 11, 7, 17, 0, tzinfo=timezone.utc)     # EST
    assert strict_cutoff(date(2026, 3, 13)) == datetime(2026, 3, 14, 16, 0, tzinfo=timezone.utc)     # EDT
    cut = strict_cutoff(D0)
    f = (cut - timedelta(hours=1)).isoformat()
    iv = build(fetched=f)
    c = dict(analysis_profile="strict", coverage_policy="full", freshness_policy="daily", basket_policy="current")
    run(iv, ctx(T=cut, **c))
    with pytest.raises(EligibilityError):
        run(iv, ctx(T=cut + timedelta(seconds=1), **c))


# ---- 固定篮子 ----
def test_fixed_basket_lag_5_ok_6_rejected():
    run(build(), ctx(basket_policy="fixed", W=date(2026, 10, 30)))      # 5 个交易日
    with pytest.raises(EligibilityError) as e:
        run(build(), ctx(basket_policy="fixed", W=date(2026, 10, 29)))   # 6
    assert e.value.code == "FIXED_BASKET_TOO_OLD"


def test_fixed_basket_w_after_d_rejected_and_current_requires_same_day():
    with pytest.raises(EligibilityError):
        run(build(), ctx(basket_policy="fixed", W=date(2026, 11, 9)))
    with pytest.raises(EligibilityError) as e:
        run(build(), ctx(basket_policy="current", W=date(2026, 11, 5)))
    assert e.value.code == "WEIGHT_DATE_MISMATCH"


def test_calendar_unknown_cannot_guess():
    with pytest.raises(CalendarUnknown):
        CAL.trading_days_between(date(2026, 12, 30), date(2027, 1, 5))
    with pytest.raises(EligibilityError) as e:
        run(build(), ctx(basket_policy="fixed", W=date(2026, 12, 20), D=date(2027, 1, 5)))
    assert e.value.code == "CALENDAR_UNKNOWN"


def test_calendar_holiday_half_day_dst_fixtures():
    assert CAL.trading_days_between(date(2026, 11, 20), date(2026, 11, 30)) == 5    # 23,24,25,27(半日),30；26日感恩节休市
    assert not CAL.is_trading_day(date(2026, 11, 26)) and CAL.is_trading_day(date(2026, 11, 27))
    assert not CAL.is_trading_day(date(2026, 7, 3))


def test_fixed_basket_keeps_old_weights_and_unverified_comparability():
    v = run(build(), ctx(basket_policy="fixed", W=date(2026, 11, 2)))
    assert v.index_comparability == "unverified"
    assert sec(v).weight == sec(v, "a").weight == __import__("decimal").Decimal("0.5")


def test_member_without_price_kept_not_renormalized():
    d = build()
    d.prices = [p for p in d.prices if p["security_id"] != "c"]
    v = run(d, ctx())
    assert len(v.securities) == 3 and sec(v, "c").ttm is None


# ---- 新鲜度边界 ----
def test_weekly_age_7_ok_8_invalid():
    ok = build(fetched=(T_SUN - timedelta(days=7)).isoformat())
    assert sec(run(ok, ctx())).ttm is not None
    old = build(fetched=(T_SUN - timedelta(days=8)).isoformat())
    v = run(old, ctx())
    assert sec(v).ttm is None and any(x["code"] == "STALE_FETCH" for x in v.diagnostics)


def test_weekly_span_exactly_7_days_ok_and_future_source_excluded():
    iv = build()
    iv.prices[0]["fetched_at"] = (T_SUN - timedelta(days=7)).isoformat()
    iv.earnings[0]["fetched_at"] = T_SUN.isoformat()
    v = run(iv, ctx())                                    # 跨度恰7日
    assert sec(v).ttm is not None
    iv = build(); iv.earnings[0]["fetched_at"] = (T_SUN + timedelta(seconds=1)).isoformat()
    v = run(iv, ctx())                                    # 晚于观察时点T的来源不得进入
    assert sec(v).ttm is None and any(x["code"] == "SOURCE_AFTER_CUTOFF" for x in v.diagnostics)


def test_daily_under_24h_ok_exactly_24h_needs_recheck():
    c = dict(freshness_policy="daily")
    ok = build(fetched=(T_SUN - timedelta(hours=23, minutes=59)).isoformat())
    assert sec(run(ok, ctx(**c))).ttm is not None
    at24 = build(fetched=(T_SUN - timedelta(hours=24)).isoformat())
    v = run(at24, ctx(**c))
    assert sec(v).ttm is None and any(x["code"] == "STALE_FETCH" for x in v.diagnostics)


def test_ttm_180_ok_181_stale():
    assert sec(run(build(ttm_q=D0 - timedelta(days=180)), ctx())).ttm is not None
    v = run(build(ttm_q=D0 - timedelta(days=181)), ctx())
    assert sec(v).ttm is None and any(x["code"] == "STALE_EARNINGS" for x in v.diagnostics)


def test_fy1_30_ok_31_stale_unknown_flagged():
    assert sec(run(build(fy_upd=D0 - timedelta(days=30)), ctx())).fy1 is not None
    v = run(build(fy_upd=D0 - timedelta(days=31)), ctx())
    assert sec(v).fy1 is None and any(x["code"] == "STALE_FORECAST" for x in v.diagnostics)
    v = run(build(fy_upd=None), ctx())
    assert sec(v).fy1 is not None and any(x["code"] == "FORECAST_FRESHNESS_UNVERIFIED" for x in v.diagnostics)


def test_price_date_mismatch_excludes_price():
    v = run(build(price_date=date(2026, 11, 5)), ctx())
    assert sec(v).ttm is None and any(x["code"] == "PRICE_DATE_MISMATCH" for x in v.diagnostics)


def test_currency_and_split_mismatch_and_wrong_period():
    iv = build()
    iv.earnings[0]["currency"] = "EUR"
    v = run(iv, ctx()); assert sec(v).ttm is None and any(x["code"] == "CURRENCY_MISMATCH" for x in v.diagnostics)
    iv = build(); iv.earnings[0]["split_basis_date"] = "2025-01-01"
    v = run(iv, ctx()); assert any(x["code"] == "SPLIT_BASIS_MISMATCH" for x in v.diagnostics)
    iv = build(); iv.earnings[1]["forecast_period"] = "NTM"
    v = run(iv, ctx()); assert sec(v).fy1 is None and any(x["code"] == "WRONG_FORECAST_PERIOD" for x in v.diagnostics)


def test_weekly_never_allows_growth_comparison():
    v = run(build(), ctx())
    assert v.accounting_comparable is False


# ---- 序列隔离 ----
def test_modes_wd_t_and_set_hash_enter_identity_and_series_key():
    iv = build()
    base = ctx()
    keys = {series_key(base)}
    for kw in (dict(coverage_policy="full"), dict(freshness_policy="daily"), dict(data_mode="real"), dict(basket_policy="fixed", W=date(2026, 11, 2))):
        keys.add(series_key(ctx(**kw)))
    assert len(keys) == 5
    i1 = input_identity(base, iv)
    i2 = input_identity(ctx(T=T_SUN + timedelta(days=1)), iv)
    i3 = input_identity(ctx(W=date(2026, 11, 5)), iv)
    assert len({i1, i2, i3}) == 3
    iv2 = build(); iv2.universe.securities.pop(); iv2.basket.weights.final.pop("c")
    assert input_identity(base, iv2) != i1
