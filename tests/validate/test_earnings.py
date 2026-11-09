from datetime import date

import pytest

from nasdaq100_pe.identity.models import SecurityIdentity
from nasdaq100_pe.normalize.quarters import select_ttm
from nasdaq100_pe.research.gap_queue import build_gap_queue
from nasdaq100_pe.validate.earnings import EarningsBatch, validate_earnings, validate_fy1_rows
from nasdaq100_pe.method import MethodSpec
from nasdaq100_pe.validate.input import validate_research_input
from tests.research_fixtures import base_input, dump, sec
from tests.sec_fixtures import facts, four_quarters


def ident(sid, issuer, cls="common", **kw):
    return SecurityIdentity(sid, issuer, cls, sid.upper(), sid, "Tech", "p", **kw)


def batch(issuer="i1", currency="USD", split="2026-01-01", class_evidence=None, ttm=None, **kw):
    return EarningsBatch(issuer_id=issuer, cik="1", currency=currency, split_basis_date=split,
                         ttm=ttm or select_ttm(facts(four_quarters())), class_evidence=class_evidence or {}, **kw)


def rows(v):
    return {r["security_id"]: r for r in v.rows}


def test_valid_single_class_issuer():
    v = validate_earnings(batch(), [ident("a", "i1")])
    assert rows(v)["a"]["status"] == "ok" and rows(v)["a"]["eps"] == "5.00" or rows(v)["a"]["eps"].startswith("5")


def test_same_cik_share_classes_not_merged_without_evidence():
    ids = [ident("goog", "i1", "C"), ident("googl", "i1", "A")]
    v = validate_earnings(batch(), ids)
    assert {r["status"] for r in v.rows} == {"invalid"} and {r["reason"] for r in v.rows} == {"AMBIGUOUS_SHARE_SCOPE"}
    v = validate_earnings(batch(class_evidence={"A": "10-K note 11", "C": "10-K note 11"}), ids)
    assert {r["status"] for r in v.rows} == {"ok"}
    v = validate_earnings(batch(class_evidence={"A": "10-K note 11"}), ids)
    assert rows(v)["googl"]["status"] == "ok" and rows(v)["goog"]["reason"] == "AMBIGUOUS_SHARE_SCOPE"


def test_foreign_currency_eps_not_used_with_usd_price():
    v = validate_earnings(batch(currency="EUR"), [ident("asml", "i1")])
    assert rows(v)["asml"]["status"] == "invalid" and rows(v)["asml"]["reason"] == "CURRENCY_MISMATCH"


def test_adr_unit_unknown_invalid():
    v = validate_earnings(batch(), [ident("tsm", "i1", is_adr=True)])
    assert rows(v)["tsm"]["reason"] == "ADR_RATIO_UNKNOWN"
    v = validate_earnings(batch(), [ident("tsm", "i1", is_adr=True, adr_ratio="5")])
    assert rows(v)["tsm"]["status"] == "ok"


def test_split_basis_mismatch():
    v = validate_earnings(batch(split="2024-01-01"), [ident("a", "i1")], expected_split_basis="2026-01-01")
    assert rows(v)["a"]["reason"] == "SPLIT_BASIS_MISMATCH"


def test_negative_eps_valid():
    b = batch(ttm=select_ttm(facts(four_quarters(vals=(-2.1, -3.0, -1.5, -0.9)))))
    v = validate_earnings(b, [ident("mrna", "i1")])
    assert rows(v)["mrna"]["status"] == "ok" and rows(v)["mrna"]["eps"].startswith("-7.5")


def test_ineligible_ttm_never_enters_metric():
    es = four_quarters(); es.pop(1)
    v = validate_earnings(batch(ttm=select_ttm(facts(es))), [ident("a", "i1")])
    assert rows(v)["a"]["status"] == "invalid" and rows(v)["a"]["reason"] in ("MISSING_Q4", "MISSING_QUARTER")
    assert v.to_input_rows() == []


def test_to_input_rows_carries_period_and_hash_fields():
    v = validate_earnings(batch(), [ident("a", "i1")])
    r = v.to_input_rows()[0]
    assert r["kind"] == "ttm" and r["accounting_basis"] == "gaap" and r["latest_quarter_end"] and r["currency"] == "USD"


# ---------- FY1 ----------
def fy1(**kw):
    r = {"security_id": "a", "forecast_period": "FY1", "fiscal_year_end": "2027-09-30", "statistic": "mean",
         "accounting_basis": "normalized", "eps": "6", "currency": "USD", "normalized_evidence": "provider doc p3",
         "unit": "per_share", "source_updated_at": "2026-10-20", "share_scope": "common"}
    r.update(kw); return r


def test_fy1_accepts_full_evidence():
    ok, bad = validate_fy1_rows([fy1()])
    assert len(ok) == 1 and not bad


@pytest.mark.parametrize("mut,reason", [
    (dict(forecast_period="NTM"), "WRONG_FORECAST_PERIOD"),
    (dict(fiscal_year_end=None), "FY1_EVIDENCE_INSUFFICIENT"),
    (dict(statistic="median"), "FY1_EVIDENCE_INSUFFICIENT"),
    (dict(accounting_basis="unknown"), "UNKNOWN_ACCOUNTING_BASIS"),
    (dict(normalized_evidence=None), "FY1_EVIDENCE_INSUFFICIENT"),
    (dict(currency=None), "FY1_EVIDENCE_INSUFFICIENT"),
])
def test_fy1_rejections(mut, reason):
    ok, bad = validate_fy1_rows([fy1(**mut)])
    assert not ok and bad[0]["reason"] == reason


def test_forward_pe_only_rejected_ttm_unaffected():
    ok, bad = validate_fy1_rows([{"security_id": "a", "forwardPE": "25"}])
    assert not ok and bad[0]["reason"] == "FY1_EVIDENCE_INSUFFICIENT"
    v = validate_earnings(batch(), [ident("a", "i1")])
    assert rows(v)["a"]["status"] == "ok"


def test_fy1_unknown_revision_time_flagged_not_rejected():
    ok, bad = validate_fy1_rows([fy1(source_updated_at=None)])
    assert len(ok) == 1 and "FORECAST_FRESHNESS_UNVERIFIED" in ok[0]["quality_flags"]


def test_fy1_zero_and_negative_eps_valid():
    ok, bad = validate_fy1_rows([fy1(eps="0"), fy1(security_id="b", eps="-1.5")])
    assert len(ok) == 2


# ---------- 缺口队列 ----------
def test_gap_queue_classified_then_weight_ordered_low_weight_kept():
    d = base_input(weights=("0.5", "0.3", "0.2"))
    d["earnings_gaps"] = [{"security_id": "a", "reason": "MISSING_Q4"}, {"security_id": "b", "reason": "CURRENCY_ADR"},
                          {"security_id": "c", "reason": "MISSING_Q4"}]
    iv = validate_research_input(dump(d), MethodSpec())
    q = build_gap_queue(iv)
    assert [(g["category"], g["security_id"]) for g in q] == [("MISSING_Q4", "a"), ("MISSING_Q4", "c"), ("CURRENCY_ADR", "b")]
    assert all(g["needed_evidence"] and g["issuer_id"] for g in q)


def test_gap_queue_excludes_securities_with_valid_ttm():
    d = base_input()
    d["earnings"] = [{"security_id": "a", "kind": "ttm", "eps": "5", "accounting_basis": "gaap", "currency": "USD", "latest_quarter_end": "2026-09-30"}]
    iv = validate_research_input(dump(d), MethodSpec())
    ids = [g["security_id"] for g in build_gap_queue(iv)]
    assert "a" not in ids and set(ids) == {"b", "c"}


def test_gap_queue_stale_with_as_of():
    d = base_input()
    d["earnings"] = [{"security_id": "a", "kind": "ttm", "eps": "5", "accounting_basis": "gaap", "currency": "USD", "latest_quarter_end": "2025-01-31"}]
    iv = validate_research_input(dump(d), MethodSpec())
    q = build_gap_queue(iv, as_of=date(2026, 11, 6))
    assert ("STALE", "a") in [(g["category"], g["security_id"]) for g in q]
