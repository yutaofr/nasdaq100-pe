import json
from datetime import date, datetime, timedelta, timezone

import pytest

from nasdaq100_pe.adapters.sec import SecAuthError, SecClient, SecRateLimited, fetch_earnings
from nasdaq100_pe.archive.store import ArchiveStore
from nasdaq100_pe.normalize.quarters import select_ttm
from tests.sec_fixtures import body, contiguous, facts, four_quarters, q

NOW = datetime(2026, 11, 9, 0, 0, tzinfo=timezone.utc)


# ---------- 季度选择 ----------
def test_ttm_is_sum_of_four_reported_consecutive_quarters():
    r = select_ttm(facts(four_quarters()))
    assert r.status == "ok" and str(r.ttm_eps) == "5.00" or float(r.ttm_eps) == 5.0
    assert r.calculation_path == "reported_quarter_eps_sum" and len(r.quarters) == 4
    assert all(x["accn"] and x["end"] for x in r.quarters)


def test_negative_eps_preserved_mrna_like():
    r = select_ttm(facts(four_quarters(vals=(-2.1, -3.0, -1.5, -0.9))))
    assert float(r.ttm_eps) == pytest.approx(-7.5) and r.status == "ok"


def test_legal_16_week_quarter_accepted():
    ps = [("2025-09-29", "2025-12-21"), ("2025-12-22", "2026-03-15"), ("2026-03-16", "2026-06-07"), ("2026-06-08", "2026-09-27")]
    # 最后一季 112 天(16周)
    assert (date(2026, 9, 27) - date(2026, 6, 8)).days + 1 == 112
    r = select_ttm(facts(contiguous(ps, [1.0, 1.0, 1.0, 2.0])))
    assert r.status == "ok" and float(r.ttm_eps) == 5.0


def test_missing_q4_not_derived_from_annual_minus_nine_months():
    es = four_quarters()
    gap = es.pop(1)                                 # 去掉中间一季
    annual = q("2025-10-01", "2026-09-30", 5.0, "k", "2026-11-01", form="10-K", fp="FY")
    ytd9 = q("2025-10-01", "2026-06-30", 3.5, "k9", "2026-08-01", fp="Q3")
    r = select_ttm(facts(es + [annual, ytd9]))
    assert r.status == "missing_quarter" and r.ttm_eps is None
    assert "MISSING_Q4" in r.reasons or "MISSING_QUARTER" in r.reasons


def test_auto_parse_uncertain_goes_manual_review():
    es = four_quarters()
    es.append(dict(es[-1], val=9.99, accn="other"))   # 同期间两个不同值，无法判断
    r = select_ttm(facts(es))
    assert r.status == "needs_manual_review" and r.ttm_eps is None


def test_restatement_keeps_both_versions_latest_wins_by_filed():
    es = four_quarters()
    rest = dict(es[-1], val=1.50, accn="restated", filed="2026-12-31")
    r = select_ttm(facts(es + [rest]))
    assert r.status == "ok" and any(v["accn"] == "restated" for v in r.versions) and len(r.versions) >= 5
    assert float(r.ttm_eps) == pytest.approx(1.1 + 1.2 + 1.3 + 1.5)


def test_annual_difference_recorded_not_forced():
    es = four_quarters(vals=(1.1, 1.2, 1.3, 1.4))
    annual = q("2025-10-01", "2026-09-30", 5.02, "k", "2026-11-01", form="10-K", fp="FY")
    r = select_ttm(facts(es + [annual]))
    assert float(r.ttm_eps) == pytest.approx(5.0) and float(r.annual_difference) == pytest.approx(0.02)


def test_missing_tag():
    r = select_ttm({"facts": {"us-gaap": {}}})
    assert r.status == "missing_label"


# ---------- 抓取、速率、checked_at ----------
class Fake:
    def __init__(self, replies):
        self.replies, self.calls, self.sleeps = list(replies), [], []

    def __call__(self, url, headers):
        self.calls.append((url, dict(headers)))
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def sleep(self, s):
        self.sleeps.append(s)


def client(fake, **kw):
    return SecClient(fake, user_agent="ndx-pe test (contact@example.test)", sleep=fake.sleep, min_interval=0.2, max_retries=2, **kw)


def test_user_agent_required():
    with pytest.raises(ValueError):
        SecClient(lambda u, h: b"{}", user_agent="")


def test_fetch_sets_ua_and_times(tmp_path):
    store = ArchiveStore(tmp_path)
    fk = Fake([body(facts(four_quarters()))])
    b = fetch_earnings("cik-0000001234", store, client(fk), now=NOW)
    assert fk.calls[0][1]["User-Agent"].startswith("ndx-pe")
    assert "CIK0000001234" in fk.calls[0][0]
    assert b.checked_at == NOW.isoformat() and b.content_fetched_at == NOW.isoformat() and b.ttm.status == "ok"


def test_unchanged_content_updates_checked_at_only(tmp_path):
    store = ArchiveStore(tmp_path)
    raw = body(facts(four_quarters()))
    b1 = fetch_earnings("cik-0000001234", store, client(Fake([raw])), now=NOW)
    later = NOW + timedelta(days=1)
    b2 = fetch_earnings("cik-0000001234", store, client(Fake([raw])), now=later)
    assert b2.checked_at == later.isoformat()
    assert b2.content_fetched_at == b1.content_fetched_at and b2.content_sha256 == b1.content_sha256


def test_offline_reread_does_not_refresh(tmp_path):
    from nasdaq100_pe.adapters.sec import read_cached
    store = ArchiveStore(tmp_path)
    fetch_earnings("cik-0000001234", store, client(Fake([body(facts(four_quarters()))])), now=NOW)
    b = read_cached("cik-0000001234", store)
    assert b.checked_at == NOW.isoformat() and b.content_fetched_at == NOW.isoformat()


def test_failed_check_does_not_masquerade_as_latest(tmp_path):
    store = ArchiveStore(tmp_path)
    fetch_earnings("cik-0000001234", store, client(Fake([body(facts(four_quarters()))])), now=NOW)
    later = NOW + timedelta(days=3)
    fk = Fake([SecAuthError("401")])
    b = fetch_earnings("cik-0000001234", store, client(fk), now=later)
    assert b.checked_at == NOW.isoformat() and b.freshness == "unverified" and "CHECK_FAILED" in b.flags


def test_new_disclosure_new_version_and_gap_task(tmp_path):
    store = ArchiveStore(tmp_path)
    fetch_earnings("cik-0000001234", store, client(Fake([body(facts(four_quarters()))])), now=NOW)
    newer = four_quarters(last_end="2026-12-31")
    b = fetch_earnings("cik-0000001234", store, client(Fake([body(facts(newer))])), now=NOW + timedelta(days=90))
    assert len(b.versions) == 2 and "NEW_DISCLOSURE" in b.flags


def test_429_limited_retries_with_backoff():
    fk = Fake([SecRateLimited("429")] * 5)
    c = client(fk)
    with pytest.raises(SecRateLimited):
        c.get("https://data.sec.gov/x")
    assert len(fk.calls) == 3 and fk.sleeps == sorted(fk.sleeps) and fk.sleeps[0] > 0 and len(set(fk.sleeps)) == len(fk.sleeps)


def test_401_not_retried():
    fk = Fake([SecAuthError("401")] * 5)
    with pytest.raises(SecAuthError):
        client(fk).get("https://data.sec.gov/x")
    assert len(fk.calls) == 1


def test_min_interval_between_requests():
    fk = Fake([b"{}", b"{}"])
    c = client(fk)
    c.get("https://data.sec.gov/a"); c.get("https://data.sec.gov/b")
    assert any(s >= 0.19 for s in fk.sleeps)


def test_logs_never_contain_response_or_secret():
    fk = Fake([b'{"secret":"TOPSECRET"}'])
    c = client(fk)
    c.get("https://data.sec.gov/a?token=ABC")
    dump = json.dumps(c.log)
    assert "TOPSECRET" not in dump and "ABC" not in dump


def test_non_sec_host_refused():
    with pytest.raises(ValueError):
        client(Fake([b""])).get("https://evil.test/x")


def test_per_share_unit_preferred_over_pure_unit():
    """真实核验发现：COST 同标签含 'pure'(2010年旧值)与 'USD/shares'，必须选每股单位。"""
    good = four_quarters()
    old = [q("2009-08-31", "2009-11-22", 0.6, "old1", "2010-01-01"), q("2009-11-23", "2010-02-14", 0.67, "old2", "2010-03-01"),
           q("2010-02-15", "2010-05-09", 0.68, "old3", "2010-06-01"), q("2010-05-10", "2010-08-29", 0.97, "old4", "2010-10-01")]
    cf = {"facts": {"us-gaap": {"EarningsPerShareDiluted": {"units": {"pure": old, "USD/shares": good}}}}}
    r = select_ttm(cf)
    assert r.currency == "USD" and r.latest_quarter_end == "2026-09-30" and float(r.ttm_eps) == pytest.approx(5.0)


def test_non_per_share_only_unit_is_missing_label():
    cf = {"facts": {"us-gaap": {"EarningsPerShareDiluted": {"units": {"pure": four_quarters()}}}}}
    assert select_ttm(cf).status == "missing_label"
