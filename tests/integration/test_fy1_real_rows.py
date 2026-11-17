"""由已归档的 Nasdaq 预测响应生成的 FY1 行，须原样通过真实数据模式的资格评估并进入内核。"""
import importlib.util
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from nasdaq100_pe.calendar import TradingCalendar
from nasdaq100_pe.engine.core import calculate
from nasdaq100_pe.method import MethodSpec
from nasdaq100_pe.validate.eligibility import AnalysisContext, assess_eligibility
from nasdaq100_pe.validate.input import validate_research_input
from tests.research_fixtures import H, base_input, dump

spec = importlib.util.spec_from_file_location("build_research_v2", Path(__file__).resolve().parents[2] / "scripts" / "build_research_v2.py")
build = importlib.util.module_from_spec(spec); spec.loader.exec_module(build)

D0 = date(2026, 11, 6)
T = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
FETCHED = (T - timedelta(hours=2)).isoformat()
FORECAST = {"data": {"symbol": "A", "yearlyForecast": {
    "headers": {"fiscalEnd": "Fiscal Year End", "consensusEPSForecast": "Consensus EPS* Forecast"},
    "rows": [{"fiscalEnd": "Dec 2026", "consensusEPSForecast": 4.0, "noOfEstimates": 9},
             {"fiscalEnd": "Dec 2027", "consensusEPSForecast": 5.0, "noOfEstimates": 7}]}}}
SURPRISE = {"data": {"earningsSurpriseTable": {
    "headers": {"fiscalQtrEnd": "Fiscal Quarter End", "eps": "Earnings Per Share*", "consensusForecast": "Consensus EPS* Forecast"},
    "rows": [{"fiscalQtrEnd": "Sep 2026", "eps": 1.1}]}}}
CF = {"facts": {"us-gaap": {
    "NetIncomeLoss": {"units": {"USD": [{"start": "2025-01-01", "end": "2025-12-31", "val": 10, "filed": "2026-02-10", "form": "10-K", "accn": "k"}]}},
    "EarningsPerShareDiluted": {"units": {"USD/shares": [
        {"start": "2026-07-01", "end": "2026-09-30", "val": 0.9, "filed": "2026-10-25", "form": "10-Q", "accn": "q"}]}}}}}


def _entry(tmp_path, forecast=FORECAST):
    d = tmp_path / "nasdaq-forecast"; d.mkdir(exist_ok=True)
    (d / "A-forecast.json").write_text(json.dumps(forecast)); (d / "A-surprise.json").write_text(json.dumps(SURPRISE))
    return {"forecast": {"url": "https://api.nasdaq.com/api/analyst/A/earnings-forecast", "sha256": "a" * 64, "fetched_at": FETCHED, "file": "A-forecast.json"},
            "surprise": {"url": "https://api.nasdaq.com/api/company/A/earnings-surprise", "sha256": "b" * 64, "fetched_at": FETCHED, "file": "A-surprise.json"}}


def _assess(rows, sources):
    d = base_input(weights=("0.6", "0.4"))
    d.update(data_mode="real", method_version="2")
    d["universe"]["as_of"] = d["weights"]["date"] = D0.isoformat()
    d["sources"] += sources
    d["prices"] = [{"security_id": s, "date": D0.isoformat(), "close": "100", "currency": "USD", "price_type": "regular_close",
                    "feed": "exchange_official", "split_basis_date": D0.isoformat(), "source_id": "s1", "fetched_at": FETCHED,
                    "evidence_sha256": H, "locator": "nocp"} for s in "ab"]
    d["earnings"] = rows
    iv = validate_research_input(dump(d), MethodSpec.load())
    c = AnalysisContext(W=D0, D=D0, T=T, analysis_profile="research", basket_policy="current", coverage_policy="subset",
                        freshness_policy="weekly", method_version="2", data_mode="real")
    return assess_eligibility(iv, c, TradingCalendar.load())


def test_built_fy1_row_passes_real_mode_gates_and_reaches_the_engine(tmp_path):
    row, source, status, reason, fye, flags = build.fy1_row("a", "A", _entry(tmp_path), tmp_path, CF, D0.isoformat(), D0, T)
    assert (status, reason, fye) == ("ok", "", "2027-12-31")
    assert Decimal(row["eps"]) == 5 and row["forecast_period_evidence"]["source_label"] == "Dec 2027"     # 当年(Dec 2026)不是 FY1
    assert row["normalized_evidence"]["comparison"]["quarters_differing_from_gaap"] == 1
    v = _assess([row], [source])
    assert [d["code"] for d in v.diagnostics if d.get("security_id") == "a"] == ["FORECAST_FRESHNESS_UNVERIFIED"]
    m = calculate(v, MethodSpec.load()).metrics["fy1"]
    assert m.eligibility == "partial" and m.securities["a"].pe == Decimal(20) and m.missing_security_ids == ["b"]


def test_row_without_its_archived_source_is_rejected(tmp_path):
    row, source, *_ = build.fy1_row("a", "A", _entry(tmp_path), tmp_path, CF, D0.isoformat(), D0, T)
    v = _assess([row], [])
    assert "EARNINGS_NO_EVIDENCE" in [d["code"] for d in v.diagnostics if d.get("security_id") == "a"]


def test_unfetched_or_unusable_forecast_produces_no_row(tmp_path):
    assert build.fy1_row("a", "A", {"forecast": {"reason": "HTTP_403"}}, tmp_path, CF, D0.isoformat(), D0, T)[:4] == (None, None, "missing", "HTTP_403")
    thin = json.loads(json.dumps(FORECAST)); thin["data"]["yearlyForecast"]["rows"].pop()
    assert build.fy1_row("a", "A", _entry(tmp_path, thin), tmp_path, CF, D0.isoformat(), D0, T)[2:4] == ("no_forecast", "NEXT_FISCAL_YEAR_NOT_IN_SOURCE")


def _currency_review(tmp_path, entry, *, ticker="A", currency="USD"):
    import hashlib
    entry["forecast"]["sha256"] = hashlib.sha256((tmp_path / "nasdaq-forecast" / entry["forecast"]["file"]).read_bytes()).hexdigest()
    d = tmp_path / "fy1-currency"; d.mkdir(exist_ok=True)
    body = b'Observed public page: current year $4.00; next year $5.00 per listed share.'
    (d / "excerpt.txt").write_bytes(body)
    review = {"ticker": ticker, "currency": currency, "unit": "per_listed_share",
              "forecast_sha256": entry["forecast"]["sha256"], "reviewed_at": FETCHED,
              "method": "two_year_forecast_currency_crosscheck", "fiscal_year_end": "2027-12-31",
              "eps": "5", "source_url": "https://example.org/A/earnings",
              "evidence_file": "excerpt.txt", "evidence_sha256": hashlib.sha256(body).hexdigest(),
              "share_basis_note": "EPS and price refer to the same listed security"}
    (d / "index.json").write_text(json.dumps({"A": review}))
    return d, review


def test_non_usd_reporter_with_bound_currency_review_reaches_engine(tmp_path):
    from copy import deepcopy
    cf = deepcopy(CF); cf["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["EUR"] = cf["facts"]["us-gaap"]["NetIncomeLoss"]["units"].pop("USD")
    entry = _entry(tmp_path); _currency_review(tmp_path, entry)
    row, source, status, *_ = build.fy1_row("a", "A", entry, tmp_path, cf, D0.isoformat(), D0, T)
    assert status == "ok"
    assert row["currency"] == "USD" and Decimal(row["eps"]) == Decimal("5")
    assert "FORECAST_CURRENCY_CROSSCHECKED" in row["quality_flags"]
    assert calculate(_assess([row], [source]), MethodSpec.load()).metrics["fy1"].securities["a"].pe == Decimal(20)


def test_currency_review_rejects_wrong_binding_or_damaged_evidence(tmp_path):
    from copy import deepcopy
    cf = deepcopy(CF); cf["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["EUR"] = cf["facts"]["us-gaap"]["NetIncomeLoss"]["units"].pop("USD")
    entry = _entry(tmp_path); d, review = _currency_review(tmp_path, entry)
    for field, value in [("ticker", "B"), ("currency", "EUR"), ("forecast_sha256", "f" * 64),
                         ("eps", "6"), ("fiscal_year_end", "2028-12-31"), ("reviewed_at", "2027-01-01T00:00:00+00:00"),
                         ("evidence_sha256", "f" * 64), ("unit", "per_ordinary_share"), ("evidence_file", "../outside.txt")]:
        (d / "index.json").write_text(json.dumps({"A": dict(review, **{field: value})}))
        assert build.fy1_row("a", "A", entry, tmp_path, cf, D0.isoformat(), D0, T)[2] == "currency_unverified", field


def test_verified_currency_does_not_bypass_missing_basis(tmp_path):
    from copy import deepcopy
    cf = deepcopy(CF); cf["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["EUR"] = cf["facts"]["us-gaap"]["NetIncomeLoss"]["units"].pop("USD")
    entry = _entry(tmp_path); _currency_review(tmp_path, entry)
    (tmp_path / "nasdaq-forecast/A-surprise.json").write_text('{"data": null}')
    assert build.fy1_row("a", "A", entry, tmp_path, cf, D0.isoformat(), D0, T)[2:4] == ("basis_unverified", "FORECAST_BASIS_UNVERIFIED")
