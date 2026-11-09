from datetime import date, datetime, timezone

import pytest

from nasdaq100_pe.adapters.base import AwaitingCredentials, PriceBatch
from nasdaq100_pe.adapters.price_contracts import build_request_params
from nasdaq100_pe.adapters.price_file import load_prices
from nasdaq100_pe.method import MethodSpec
from nasdaq100_pe.validate.eligibility import AnalysisContext
from nasdaq100_pe.validate.input import validate_research_input
from tests.research_fixtures import base_input, dump

D0 = date(2026, 11, 6)
T = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
HDR = "security_id,date,close,currency,price_type,session,adjustment,feed,split_basis_date,fetched_at,evidence_sha256,locator,status\n"
OKROW = "{sid},2026-11-06,{close},USD,regular_close,regular,raw,sip,2026-01-01,2026-11-08T10:00:00+00:00," + "e" * 64 + ",row{n},ok\n"


def ctx():
    return AnalysisContext(W=D0, D=D0, T=T, analysis_profile="research", basket_policy="current", coverage_policy="subset",
                           freshness_policy="weekly", method_version="1", data_mode="synthetic")


def uni(scope="full"):
    return validate_research_input(dump(base_input(scope=scope)), MethodSpec()).universe


def write(tmp_path, body, name="p.csv"):
    p = tmp_path / name; p.write_text(HDR + body, encoding="utf-8"); return p


def test_all_members_ok(tmp_path):
    p = write(tmp_path, "".join(OKROW.format(sid=s, close="100", n=i) for i, s in enumerate("abc")))
    b = load_prices(p, uni(), ctx())
    assert b.status == "ok" and {m["security_id"]: m["status"] for m in b.matrix} == {"a": "ok", "b": "ok", "c": "ok"}
    assert b.coverage == "1"


def test_matrix_covers_whole_universe_not_just_one_name(tmp_path):
    p = write(tmp_path, OKROW.format(sid="a", close="100", n=0))
    b = load_prices(p, uni(), ctx())
    st = {m["security_id"]: m["status"] for m in b.matrix}
    assert st == {"a": "ok", "b": "missing", "c": "missing"} and b.status == "partial"
    assert b.coverage == "0.3333333333333333333333333333333333" or b.coverage.startswith("0.33333")


@pytest.mark.parametrize("mut,reason", [
    (dict(close="0"), "NON_POSITIVE"),
    (dict(close="-5"), "NON_POSITIVE"),
    (dict(close="abc"), "BAD_NUMBER"),
])
def test_invalid_numbers(tmp_path, mut, reason):
    p = write(tmp_path, OKROW.format(sid="a", close=mut["close"], n=0))
    m = {x["security_id"]: x for x in load_prices(p, uni(), ctx()).matrix}["a"]
    assert m["status"] == "invalid" and m["reason"] == reason


@pytest.mark.parametrize("col,val,reason", [
    ("price_type", "after_hours", "NOT_REGULAR_CLOSE"),
    ("price_type", "close", "PRICE_TYPE_UNDEFINED"),
    ("price_type", "last", "NOT_REGULAR_CLOSE"),
    ("price_type", "holdings_implied", "DERIVED_PRICE"),
    ("session", "after_hours", "NOT_REGULAR_CLOSE"),
    ("currency", "EUR", "CURRENCY_NOT_USD"),
    ("date", "2026-11-05", "STALE_PRICE"),
    ("adjustment", "adjusted", "SPLIT_BASIS_UNKNOWN"),
    ("feed", "iex", "FEED_NOT_CONSOLIDATED"),
    ("split_basis_date", "", "SPLIT_BASIS_UNKNOWN"),
    ("evidence_sha256", "", "NO_EVIDENCE"),
])
def test_row_rules(tmp_path, col, val, reason):
    cols = HDR.strip().split(",")
    row = dict(zip(cols, OKROW.format(sid="a", close="100", n=0).strip().split(",")))
    row[col] = val
    p = tmp_path / "p.csv"; p.write_text(HDR + ",".join(row[c] for c in cols) + "\n", encoding="utf-8")
    m = {x["security_id"]: x for x in load_prices(p, uni(), ctx()).matrix}["a"]
    assert m["status"] != "ok" and m["reason"] == reason


def test_explicit_status_rows_suspended_identity_split(tmp_path):
    body = "".join(f"{s},2026-11-06,,USD,,,,,,,,,{st}\n" for s, st in (("a", "suspended"), ("b", "identity_changed"), ("c", "split_unclear")))
    b = load_prices(write(tmp_path, body), uni(), ctx())
    assert {m["security_id"]: m["status"] for m in b.matrix} == {"a": "suspended", "b": "identity_changed", "c": "split_unclear"}


def test_no_stale_fill(tmp_path):
    p = write(tmp_path, OKROW.format(sid="a", close="100", n=0).replace("2026-11-06", "2026-11-05", 1))
    b = load_prices(p, uni(), ctx())
    assert "a" not in b.prices and b.status != "ok"


def test_duplicate_conflicting_rows_invalid(tmp_path):
    p = write(tmp_path, OKROW.format(sid="a", close="100", n=0) + OKROW.format(sid="a", close="101", n=1))
    m = {x["security_id"]: x for x in load_prices(p, uni(), ctx()).matrix}["a"]
    assert m["status"] == "invalid" and m["reason"] == "PRICE_CONFLICT"


def test_coverage_none_when_universe_incomplete(tmp_path):
    p = write(tmp_path, OKROW.format(sid="a", close="100", n=0))
    b = load_prices(p, uni(scope="top_n"), ctx())
    assert b.coverage is None          # 不用未知分母算百分比


def test_missing_file_awaiting_user_import(tmp_path):
    b = load_prices(tmp_path / "nope.csv", uni(), ctx())
    assert b.status == "awaiting_user_import"
    assert set(b.missing_fields) >= {"security_id", "date", "close", "currency", "price_type", "evidence_sha256"}
    assert b.missing_security_ids == ["a", "b", "c"]


def test_awaiting_credentials_no_network(monkeypatch):
    import socket
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    b = AwaitingCredentials("alpaca").fetch_prices(D0, ["a", "b"])
    assert b.status == "awaiting_credentials" and b.missing_security_ids == ["a", "b"]


def test_vendor_contracts_offline():
    a = build_request_params("alpaca", D0, ["AAPL"])
    assert a["feed"] == "sip" and a["adjustment"] == "raw"
    with pytest.raises(ValueError):
        build_request_params("alpaca", D0, ["AAPL"], feed="iex")      # 不自动以 IEX 代替 SIP
    m = build_request_params("massive", D0, ["AAPL"])
    assert m["adjusted"] == "false"
    with pytest.raises(ValueError):
        build_request_params("massive", D0, ["AAPL"], adjusted=True)
    with pytest.raises(ValueError):
        build_request_params("yahoo", D0, ["AAPL"])
